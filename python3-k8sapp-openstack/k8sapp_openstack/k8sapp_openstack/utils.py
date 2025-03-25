#
# Copyright (c) 2023-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from grp import getgrnam
import json
import os
from pathlib import Path
from pwd import getpwnam
import re
import shutil
from typing import Generator

from eventlet.green import subprocess
from kubernetes.client.rest import ApiException as KubeApiException
from oslo_log import log as logging
from oslo_serialization import base64
from sysinv.common import constants
from sysinv.common import kubernetes
from sysinv.common import utils as cutils
from sysinv.db import api as dbapi
from sysinv.helm import common as helm_common
import yaml

from k8sapp_openstack.common import constants as app_constants

LOG = logging.getLogger(__name__)


def _get_value_from_application(default_value, chart_name, override_name):
    """
    Gets a value from the app constants or from the
    Helm overrides

    :param default_value: The value to return if there are no overrides
    :param chart_name: The name of the chart to look for the overrides
    :param override_name: The name of the field in values.yaml
    """
    # If the database in unavailable, return the default value
    value = default_value
    db = dbapi.get_instance()
    if db is None:
        return value

    # However, the user might have overriden the default
    # pattern. If that is the case, fetch and return the
    # user-defined one.
    # If the database is available, get the Helm overrides
    # for it. Return the default value if no overrides are
    # present, and return the override if it exists.
    app = cutils.find_openstack_app(db)

    override = db.helm_override_get(
        app_id=app.id,
        name=chart_name,
        namespace=app_constants.HELM_NS_OPENSTACK,
    )

    if override.user_overrides:
        user_overrides = yaml.load(
            override.user_overrides, Loader=yaml.FullLoader
        )
        value = user_overrides.get(override_name, default_value)
    return value


def get_services_fqdn_pattern() -> str:
    """Get services FQDN configuration pattern

    :returns: str -- The services FQDN endpoint pattern
    """
    return _get_value_from_application(
            default_value=app_constants.SERVICES_FQDN_PATTERN,
            chart_name=app_constants.HELM_CHART_CLIENTS,
            override_name="serviceEndpointPattern")


def is_openstack_https_ready(service_name: str = app_constants.HELM_CHART_CLIENTS):
    """Check if OpenStack is ready for HTTPS.

    This function returns True if the necessary HTTPS certificates are either
    present as file content in the specified directory or defined in the system
    overrides. Specifically, it checks for the presence of the primary
    certificate and key files, while skipping the optional CA certificate.

    Args:
        service_name (str): The name of the Helm chart, used to check certificates.
                            Defaults to `app_constants.HELM_CHART_CLIENTS`.

    Returns:
        bool: True if all required HTTPS certificates are present;
              False otherwise.
    """
    # If the service name was not defined, check for the actual certificate files
    certificates = get_openstack_certificate_values(service_name)
    for cert_name in certificates:
        # The CA certificate (Certificate Authority) is not
        # required for HTTPs to be enabled, so we skip it.
        if cert_name == app_constants.OPENSTACK_CERT_CA:
            continue

        # Check if the value is defined
        if not certificates[cert_name]:
            return False
    return True


def get_openstack_certificate_values(service_name: str = app_constants.HELM_CHART_CLIENTS) -> dict:
    """Retrieve the OpenStack certificate values for HTTPS readiness.

    This function retrieves the certificate, key, and CA values required for HTTPS
    connections for the OpenStack charts. It first attempts to load these values from
    a Kubernetes secret named `<service_name>-tls-public` in the `openstack`
    namespace. If the secret does not exist or is unavailable, it defaults to
    reading the values from Helm overrides. If neither the secret nor the overrides
    are defined, it defaults to reading certificate files directly from the filesystem.

    Args:
        service_name (str): The name of the Helm chart, used to construct the secret name.
                            Defaults to `app_constants.HELM_CHART_CLIENTS`.

    Returns:
        dict[str, str]: A dictionary containing the following keys:
            - app_constants.OPENSTACK_CERT: The primary HTTPS certificate.
            - app_constants.OPENSTACK_CERT_KEY: The corresponding private key.
            - app_constants.OPENSTACK_CERT_CA: The CA certificate, if defined.

            If any of these values are unavailable, their dictionary entries are set to `None`.
    """
    # If the forceReadCertificateFiles value is set to true, then always
    # try to get the overrides from the files.
    force_read = _get_value_from_application(
            default_value=app_constants.FORCE_READ_CERT_FILES,
            chart_name=app_constants.HELM_CHART_CLIENTS,
            override_name="forceReadCertificateFiles")
    if force_read:
        LOG.debug("forceReadCertificateFiles is True. Reading certificates values from files")
        return _get_openstack_certificate_files()

    # Search for the <service_name>-tls-public secret
    try:
        # Get secret
        secret_name = f"{service_name}-tls-public"
        kube = kubernetes.KubeOperator()
        secret = kube.kube_get_secret(name=secret_name, namespace=app_constants.HELM_NS_OPENSTACK)

        # Make sure secret has 'data' attribute
        if not hasattr(secret, 'data'):
            # Simply raise an Exception here to use certificate files instead
            LOG.debug(f"Secret {secret_name} has no data attribute")
            raise Exception

        data = secret.data

        # Check for the cert and key files in the secret's data.
        # No need to check for the CA file, as it's not mandatory to have it.
        if "tls.crt" not in data or "tls.key" not in data:
            LOG.warning(f"Secret {secret_name} does not contain 'tls.crt' or 'tls.key'")
            raise Exception

        tls_crt = base64.decode_as_text(data['tls.crt'])
        tls_key = base64.decode_as_text(data['tls.key'])

        # Check and decode CA certificate, if present
        ca_crt = base64.decode_as_text(data['ca.crt']) if "ca.crt" in data else None

        # Prepare and return certificate dictionary
        certs_dict = {
            app_constants.OPENSTACK_CERT: tls_crt,
            app_constants.OPENSTACK_CERT_KEY: tls_key,
            app_constants.OPENSTACK_CERT_CA: ca_crt
        }
    except Exception:
        # Something went wrong, read certificate files.
        # This could mean that this is an upload and there are no overrides,
        # or that the host_fqdn_override is empty
        LOG.debug(f"Secret {secret_name} not found for chart {service_name}. "
                  "Attempting to retrieve OpenStack certificates from files.")
        certs_dict = _get_openstack_certificate_files()

    return certs_dict


def _get_openstack_certificate_files():
    """Retrieve OpenStack certificate files for HTTPS connections.

    This function gathers the file paths for the OpenStack certificate, key, and CA
    certificate, using default values or application-specific overrides as defined
    in Helm configurations. It reads and returns the content of each file path.

    Returns:
        dict[str, str]: A dictionary containing:
            - app_constants.OPENSTACK_CERT: Contents of the primary certificate file.
            - app_constants.OPENSTACK_CERT_KEY: Contents of the private key file.
            - app_constants.OPENSTACK_CERT_CA: Contents of the CA certificate file.

            If any of the files are unavailable or empty, their corresponding entries
            in the dictionary will be `None`.
    """
    openstack_cert_file_path = _get_value_from_application(
            default_value=constants.OPENSTACK_CERT_FILE,
            chart_name=app_constants.HELM_CHART_CLIENTS,
            override_name="openstackCertificateFile")

    openstack_cert_key_file_path = _get_value_from_application(
            default_value=constants.OPENSTACK_CERT_KEY_FILE,
            chart_name=app_constants.HELM_CHART_CLIENTS,
            override_name="openstackCertificateKeyFile")

    openstack_cert_ca_file_path = _get_value_from_application(
            default_value=constants.OPENSTACK_CERT_CA_FILE,
            chart_name=app_constants.HELM_CHART_CLIENTS,
            override_name="openstackCertificateCAFile")

    return {
        app_constants.OPENSTACK_CERT: _get_file_content(openstack_cert_file_path),
        app_constants.OPENSTACK_CERT_KEY: _get_file_content(openstack_cert_key_file_path),
        app_constants.OPENSTACK_CERT_CA: _get_file_content(openstack_cert_ca_file_path)
    }


def directory_files(path: str) -> Generator:
    """Simple generator to iterate over files from a directory.

    For each `next()` call (or iteration), returns a file path
    string, e.g., `/path/to/file`.

    :param path: The directory path.
    :returns: Generator -- The file generator.
    """

    directories = [path]
    while directories:
        directory = Path(directories.pop(0))
        for pathname in directory.glob("*"):
            if pathname.is_dir():
                directories.append(str(pathname))
                continue
            else:
                yield str(pathname)


def get_clients_working_directory() -> str:
    """Get OpenStack clients' working directory path.

    :returns: str -- The clients' working directory path.
    """
    return _get_value_from_application(
            default_value=app_constants.CLIENTS_WORKING_DIR,
            chart_name=app_constants.HELM_CHART_CLIENTS,
            override_name="workingDirectoryPath")


def reset_clients_working_directory_permissions(path: str) -> bool:
    """Reset OpenStack clients' working directory permissions.

    :param path: The clients' working directory path.
    :returns: bool -- `True`, if the permissions have been reset.
                      `False`, if otherwise.
    """

    # Get the ideal UID and GID for the clients' working directory.
    try:
        WORKING_DIR_UID = getpwnam(
            app_constants.CLIENTS_WORKING_DIR_USER
        ).pw_uid
        WORKING_DIR_GID = getgrnam(
            app_constants.CLIENTS_WORKING_DIR_GROUP
        ).gr_gid
    except KeyError:
        LOG.error(
            "Unable to get UID of user "
            f"`{app_constants.CLIENTS_WORKING_DIR_USER}` and/or "
            f"GID of group `{app_constants.CLIENTS_WORKING_DIR_GROUP}."
        )
        return False

    try:
        # Reset clients' working directory permissions.
        os.chmod(path, mode=0o770)
        os.chown(path, uid=WORKING_DIR_UID, gid=WORKING_DIR_GID)

        for filepath in directory_files(path=path):
            # For files in the root directory,
            # reset both UID and GID to the ideal values.
            if Path(filepath).parent == Path(path):
                os.chown(filepath, uid=WORKING_DIR_UID, gid=WORKING_DIR_GID)
            else:
                # For files in user subdirectories,
                # only reset the GID to the ideal value.
                os.chown(filepath, uid=-1, gid=WORKING_DIR_GID)
    except Exception as e:
        LOG.error(
            "Unable to reset clients' working directory "
            f"`{path}` permissions: {e}"
        )
        return False
    return True


def create_clients_working_directory(
    path: str = ""
) -> bool:
    """Create OpenStack clients' working directory.

    :param path: The working directory path (optional).
                 If not specified, it will assume either the default or the
                 user-defined working directory path. The latter has priority
                 over the former.
    :returns: bool -- `True`, if clients' working directory has been created.
                      `False`, if otherwise.
    """

    # Get the ideal UID and GID for the clients' working directory.
    try:
        WORKING_DIR_UID = getpwnam(
            app_constants.CLIENTS_WORKING_DIR_USER
        ).pw_uid
        WORKING_DIR_GID = getgrnam(
            app_constants.CLIENTS_WORKING_DIR_GROUP
        ).gr_gid
    except KeyError:
        LOG.error(
            "Unable to get UID of user "
            f"`{app_constants.CLIENTS_WORKING_DIR_USER}` and/or "
            f"GID of group `{app_constants.CLIENTS_WORKING_DIR_GROUP}."
        )
        return False

    # Create clients' working directory.
    # (Ignore if it already exists)
    if not path:
        path = get_clients_working_directory()

    working_directory = Path(path)
    working_directory.mkdir(exist_ok=True)

    # Change clients' working directory permissions.
    try:
        os.chmod(str(working_directory), mode=0o770)
        os.chown(
            str(working_directory),
            uid=WORKING_DIR_UID,
            gid=WORKING_DIR_GID,
        )
    except Exception as e:
        LOG.error(
            "Unable to change clients' working directory "
            f"`{str(working_directory)}` permissions: {e}"
        )
        return False
    return True


def delete_clients_working_directory(
        path: str = ""
) -> bool:
    """Delete OpenStack clients' working directory.

    :param path: The working directory path (optional).
                 If not specified, it will assume either the default or the
                 user-defined working directory path. The latter has priority
                 over the former.
    :returns: bool -- `True`, if clients' working directory has been deleted.
                      `False`, if otherwise.
    """

    if path:
        working_directory = path
    else:
        working_directory = get_clients_working_directory()

    # If it is a user-defined working directory, do not delete it.
    # It may contain files that are used by other users and/or programs.
    if working_directory != app_constants.CLIENTS_WORKING_DIR:
        LOG.warning(
            f"Unable to delete OpenStack clients' working directory "
            f"`{working_directory}`. "
            f"Directory is user-defined and cannot be deleted."
        )
        return False

    # If it is the default working directory, search for additional
    # files that might have been created by users.
    for filepath in directory_files(path=working_directory):
        # Ignore files in the root directory.
        if Path(filepath).parent == Path(working_directory):
            continue

        # If there is at least one file created by users outside the
        # root directory, that is, in a user subdirectory, it means
        # that we cannot delete the clients' working directory.
        LOG.warning(
            f"Unable to delete OpenStack clients' working directory "
            f"`{working_directory}`. "
            f"There are one or more user files in subdirectories."
        )
        return False

    shutil.rmtree(working_directory, ignore_errors=True)
    return True


def get_ceph_uuid():
    """Get Ceph secret UUID for Cinder backend configuration

    :returns: str -- The Ceph's secret UUID
    """
    ceph_config_file = os.path.join(constants.CEPH_CONF_PATH,
                                    constants.SB_TYPE_CEPH_CONF_FILENAME)

    # If the file doesn't exist, return nothing, as not to change
    # the default value.
    if not os.path.isfile(ceph_config_file):
        LOG.warning(f"`{ceph_config_file}` does not exist. Using "
                    "default configuration.")
        return None

    # Search for the line that contains the `fsid` parameter, which is
    # the Ceph UUID required for Cinder's backend configuration.
    with open(ceph_config_file) as file:
        line = next((line for line in file if "fsid" in line), None)
        if not line:
            LOG.warning(f"`{ceph_config_file}` does not contain the "
                        "'fsid' value. Using default configuration")
            return None

        # This Regex pattern searches for an UUID
        pattern = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]"
                             r"{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}",
                             re.IGNORECASE)
        return pattern.findall(line)[0]


def is_subcloud():
    db = dbapi.get_instance()
    system = db.isystem_get_one()

    try:
        if system.distributed_cloud_role == "subcloud":
            return True
        else:
            return False
    except AttributeError:
        return False


def _get_file_content(filename):
    """Read and return the content of a specified file.

    This function checks if a file exists at the specified path. If the file exists,
    it reads and returns the file's content. If the file is missing, it returns `None`.

    Args:
        filename (str): The path to the file to be read.

    Returns:
        str or None: The content of the file as a string, or `None` if the file does
        not exist.
    """
    if not os.path.isfile(filename):
        return None
    with open(filename) as f:
        return f.read()


def check_netapp_backends() -> dict:
    """
    Check for the presence of NetApp backends (NFS and iSCSI) using `tridentctl`.

    Calling the 'tridentctl' directly does not work with the STX-Openstack plugins,
    so we have to run the command inside of the 'trident-main' container.

    Returns:
        dict: A dictionary indicating the availability of `nfs` and `iscsi` backends.
              Example: {"nfs": True, "iscsi": False}
    """
    namespace = _get_value_from_application(
        default_value=app_constants.OPENSTACK_NETAPP_NAMESPACE,
        chart_name=app_constants.HELM_CHART_CLIENTS,
        override_name="netAppNamespace")

    backends_map = {"nfs": False, "iscsi": False}

    try:
        kube = kubernetes.KubeOperator()

        # Get the controller pod for NetApp
        pods = kube.kube_get_pods_by_selector(namespace, f"app={app_constants.NETAPP_CONTROLLER_LABEL}", "")
        if not pods:
            return {"nfs": False, "iscsi": False}
        pod_name = pods[0].metadata.name

        # Not using the `kube_exec_container_stream` function from the KubeOperator
        # here, as it is prone to error
        cmd = [
            "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
            "-n", namespace,
            "exec", "-it", pod_name,
            "-c", app_constants.NETAPP_MAIN_CONTAINER_NAME,
            "--", "tridentctl", "get", "backends"
        ]
        backend_info = subprocess.run(
                args=cmd,
                capture_output=True,
                text=True,
                check=True,
                shell=False)

        if not backend_info.stdout:
            return backends_map

        backends_map["nfs"] = bool(re.search(r"ontap-nas", backend_info.stdout))
        backends_map["iscsi"] = bool(re.search(r"ontap-san", backend_info.stdout))
        return backends_map
    except KubeApiException as e:
        LOG.error(f"Failed to get trident controller pod name: {e}")
        return backends_map
    except subprocess.CalledProcessError as e:
        LOG.error(
            "Tridentctl command did not return successful return code: "
            f"{e.returncode}. Error message was: {e.output}"
        )
        return backends_map
    except subprocess.TimeoutExpired as e:
        LOG.error(f"Tridentctl command timed out: {e}")
        return backends_map
    except Exception as e:
        LOG.error(f"Unexpected error while fetching NetApp backends: {e}")
        return backends_map


def is_netapp_available() -> bool:
    """Returns true or false if NetApp backend is available

    Returns:
        bool: True if Netapp backend is available or False if it is not
    """
    netapp_backends = check_netapp_backends()
    return netapp_backends["nfs"] or netapp_backends["iscsi"]


def is_openvswitch_enabled(hosts, labels_by_hostid) -> bool:
    """
    Check if openvswitch is enabled.

    Args:
        hosts (list): A list of hosts registered in the database.
        labels_by_hostid (dict): A dictionary of labels associated
        with a specific host ID.

    Returns:
        bool: True if openvswitch is enabled or False if it is not.
    """
    for host in hosts:
        host_labels = labels_by_hostid.get(host.id, [])
        if not host_labels:
            LOG.debug(f"No labels found for host ID {host.id}")
        labels = dict((label.label_key, label.label_value) for label in host_labels)
        if (host.invprovision in [constants.PROVISIONED,
                                  constants.PROVISIONING] or
                host.ihost_action in [constants.UNLOCK_ACTION,
                                      constants.FORCE_UNLOCK_ACTION]):
            if (constants.WORKER in cutils.get_personalities(host) and
                    cutils.has_openstack_compute(host_labels)):
                if (helm_common.LABEL_OPENVSWITCH in labels):
                    vswitch_label_value = labels.get(helm_common.LABEL_OPENVSWITCH)
                    LOG.debug(f"Open vSwitch label value for host {host.id}: {vswitch_label_value}")
                    return helm_common.LABEL_VALUE_ENABLED == vswitch_label_value.lower()
                else:
                    LOG.debug(f"Openvswitch label not found for host {host.id}")
    LOG.info("Openvswitch is not enabled on any of the hosts.")
    return False


def send_cmd_read_response(cmd: list[str], log: bool = True) -> str:
    """
    Send command and reads its response as a string

    Args:
        cmd (list[str]): List containing each entry of the command
        log (bool): if True, print the logs (default)

    Returns:
        str: Command response, if successful
    """
    process = subprocess.run(
        args=cmd,
        capture_output=True,
        text=True,
        shell=False
    )
    if log:
        if process.stdout.rstrip():
            LOG.info(f"Stdout: {process.stdout.rstrip()}")
        if process.stderr.rstrip():
            LOG.info(f"Stderr: {process.stderr.rstrip()}")
    process.check_returncode()

    return process.stdout.rstrip()


def update_helmrelease(release, patch):
    """
    Update the Helmrelease of a Helm chart.

    Args:
        release (str): The name of the Helmrelease to update.
        patch (dict): Patch to apply to the Helmrelease.
    """

    cmd = [
        "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
        "patch", "helmrelease", release,
        "-n", app_constants.HELM_NS_OPENSTACK,
        "--type", "merge",
        "-p", json.dumps(patch)
    ]

    try:
        send_cmd_read_response(cmd)

    except KubeApiException as e:
        LOG.error(f"Failed to update helmrelease: {release}, with error: {e}")
    except Exception as e:
        LOG.error(f"Unexpected error while updating helmrelease: {e}")


def get_number_of_controllers() -> int:
    """Get the number of controllers in the system

    Returns:
        int: Number of controllers
    """

    number_of_controllers = 0

    try:
        cmd = [
            "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
            "get", "hosts", "-o", "NAME", "--all-namespaces"
        ]
        controllers_str = send_cmd_read_response(cmd)
        number_of_controllers = controllers_str.count('controller')
    except Exception as e:
        LOG.error(f"Unexpected error while getting number of controllers: {e}")

    return number_of_controllers


def check_and_create_snapshot_class(snapshot_class: str, path: str):
    """
    Check if a PVC Snapshot Class exists. If not, create the class.

    Params:
        snapshot_class (str): Name of the snapshot class
        path (str): Path to temporary files
    """

    try:
        cmd = [
            "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
            "-n", app_constants.HELM_NS_OPENSTACK,
            "get", "volumesnapshotclasses.snapshot.storage.k8s.io", snapshot_class
        ]
        send_cmd_read_response(cmd)

    except Exception:
        # Create class
        LOG.info(f"Trying to create snapshot class {snapshot_class}")
        try:
            snapclass_dict = {
                "apiVersion": "snapshot.storage.k8s.io/v1",
                "kind": "VolumeSnapshotClass",
                "deletionPolicy": "Delete",
                "driver": "rbd.csi.ceph.com",
                "metadata": {
                    "name": snapshot_class,
                },
                "parameters": {
                    "clusterID": get_ceph_uuid(),
                    "csi.storage.k8s.io/snapshotter-secret-name": "ceph-pool-kube-rbd",
                    "csi.storage.k8s.io/snapshotter-secret-namespace": "kube-system",
                    "snapshotNamePrefix": "rbd-snap-",
                },
            }

            # Dumping config to json file
            filename = f"{path}/{snapshot_class}-class.json"
            with open(filename, "w") as fp:
                json.dump(snapclass_dict, fp)

            cmd = [
                "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
                "create", "-f", filename
            ]
            send_cmd_read_response(cmd)

            os.remove(filename)

            LOG.info(f"Created new snapshot class '{snapshot_class}'")

        except Exception as e:
            LOG.error(f"Unexpected error while checking/creating snapshot class {snapshot_class}: {e}")


def create_pvc_snapshot(snapshot_name: str, pvc_name: str, snapshot_class: str, path: str = "/tmp"):
    """
    Create a PVC snapshot

    Params:
        snapshot_name (str): Name of the snapshot
        pvc_name (str): PVC whose snapshot will be taken
        snapshot_class (str): Name of the snapshot class to be used
        path (str): Path to temporary files
    """

    try:
        # Check if snapshot class exists. If not, create it
        LOG.info(f"Checking if snapshot class {snapshot_class} already exists.")
        check_and_create_snapshot_class(snapshot_class, path)

        # Snapshot config
        snapshot_dict = {
            "apiVersion": "snapshot.storage.k8s.io/v1",
            "kind": "VolumeSnapshot",
            "metadata": {
                "name": snapshot_name,
                "namespace": app_constants.HELM_NS_OPENSTACK,
            },
            "spec": {
                "volumeSnapshotClassName": snapshot_class,
                "source": {
                    "persistentVolumeClaimName": pvc_name,
                },
            },
        }

        # Dumping config to json file
        filename = f"{path}/{pvc_name}-snapshot.json"
        with open(filename, "w") as fp:
            json.dump(snapshot_dict, fp)

        # Creating snapshot
        LOG.info(f"Creating new PVC snapshot '{snapshot_name}'")
        cmd = [
            "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
            "create", "-f", filename
        ]
        send_cmd_read_response(cmd)

        os.remove(filename)

    except Exception as e:
        LOG.error(f"Unexpected error while creating PVC snapshot: {e}")


def restore_pvc_snapshot(snapshot_name: str,
                         pvc_name: str,
                         statefulset_name: str,
                         number_of_controllers: int = 1,
                         path: str = "/tmp"):
    """
    Restore a PVC snapshot, if possible

    Params:
        snapshot_name (str): Name of the snapshot
        pvc_name (str): PVC whose snapshot was taken of
        statefulset_name (str): Name of the statefulset using the PVC
        number_of_controllers (int): Number of controllers in the system
        path (str): Path to temporary files
    """
    try:
        # Check if snapshot exists
        cmd = [
            "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
            "-n", app_constants.HELM_NS_OPENSTACK,
            "get", "volumesnapshots.snapshot.storage.k8s.io", snapshot_name
        ]
        send_cmd_read_response(cmd)

        # Set sts replicas to zero
        cmd = [
            "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
            "-n", app_constants.HELM_NS_OPENSTACK,
            "scale", "sts", statefulset_name, "--replicas=0"
        ]
        send_cmd_read_response(cmd)

        # Get PVC capacity and storage class name
        cmd = [
            "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
            "-n", app_constants.HELM_NS_OPENSTACK,
            "get", "pvc", pvc_name,
            "-o=custom-columns=C1:.spec.resources.requests.storage,C2:.spec.storageClassName",
            "--no-headers"
        ]
        output = send_cmd_read_response(cmd)
        capacity, storageclass_name = " ".join(output.split()).split(" ")

        # Delete old PVC
        cmd = [
            "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
            "-n", app_constants.HELM_NS_OPENSTACK,
            "delete", "pvc", pvc_name
        ]
        send_cmd_read_response(cmd)

        # Apply snapshot
        pvc_snapshot_dict = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": pvc_name,
                "namespace": app_constants.HELM_NS_OPENSTACK,
            },
            "spec": {
                "storageClassName": storageclass_name,
                "dataSource": {
                    "name": snapshot_name,
                    "kind": "VolumeSnapshot",
                    "apiGroup": "snapshot.storage.k8s.io",
                },
                "accessModes": [
                    "ReadWriteOnce"
                ],
                "resources": {
                    "requests": {
                        "storage": capacity
                    },
                },
            },
        }

        filename = f"{path}/{pvc_name}-snapshot-to-apply.json"
        with open(filename, "w") as fp:
            json.dump(pvc_snapshot_dict, fp)

        LOG.info(f"Restoring PVC snapshot '{snapshot_name}'")
        cmd = [
            "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
            "create", "-f", filename
        ]
        send_cmd_read_response(cmd)

        os.remove(filename)

        # Set sts replicas to number of controllers
        cmd = [
            "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
            "-n", app_constants.HELM_NS_OPENSTACK,
            "scale", "sts", statefulset_name, f"--replicas={number_of_controllers}"
        ]
        send_cmd_read_response(cmd)

    except Exception as e:
        LOG.error(f"Unexpected error while restoring PVC snapshot: {e}")


def delete_snapshot(snapshot_name: str):
    """
    Restore a PVC snapshot, if possible

    Params:
        snapshot_name (str): Name of the snapshot to be removed
    """
    try:
        cmd = [
            "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
            "-n", app_constants.HELM_NS_OPENSTACK,
            "delete", "volumesnapshots.snapshot.storage.k8s.io", snapshot_name
        ]
        send_cmd_read_response(cmd)
    except Exception as e:
        LOG.error(f"Unexpected error while deleting PVC snapshot: {e}")


def delete_kubernetes_resource(resource_type, resource_name):
    """
    Delete a Kubernetes resource.

    Args:
        resource_type (str): The type of the Kubernetes resource.
        resource_name (str): The name of the Kubernetes resource.
    """
    try:
        cmd = [
            "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
            "delete", resource_type, resource_name,
            "-n", app_constants.HELM_NS_OPENSTACK
        ]
        send_cmd_read_response(cmd)
    except KubeApiException as e:
        LOG.error(f"Failed to delete {resource_type}: {resource_name}, with error: {e}")
    except Exception as e:
        LOG.error(f"Unexpected error while deleting {resource_type}: {e}")
