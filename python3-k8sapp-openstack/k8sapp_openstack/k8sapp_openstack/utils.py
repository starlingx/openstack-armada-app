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

from cephclient import wrapper as ceph
from eventlet.green import subprocess
from kubernetes.client.rest import ApiException as KubeApiException
from oslo_log import log as logging
from oslo_serialization import base64
import requests
from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import kubernetes
from sysinv.common import utils as cutils
from sysinv.conductor import kube_app
from sysinv.db import api as dbapi
from sysinv.helm import common as helm_common
from sysinv.helm import utils as helm_utils
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

        # Deep lookup (supports nested keys)
        keys = override_name.split(".")
        current = user_overrides
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                current = None
                break

        # If found, use it; otherwise, keep default
        value = current if current is not None else default_value

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


def get_ceph_fsid():
    """Get Ceph fsid for storage backend configuration

    Returns:
        str: Ceph's fsid if the request succeeds, None otherwise
    """
    fsid = None
    try:
        fsid = send_cmd_read_response(["ceph", "fsid"])
        # Check if the response includes a UUID pattern
        pattern = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]"
                            r"{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}",
                            re.IGNORECASE)
        if len(pattern.findall(fsid)) > 0:
            fsid = fsid.strip()
            LOG.info(f'Ceph fsid {fsid} successfully recovered')
        else:
            fsid = None
            LOG.error("Ceph fsid not available through ceph fsid CLI")
    except Exception as e:
        LOG.error(f"Ceph fsid CLI failed: {str(e)}")
    return fsid


def is_central_cloud():
    db = dbapi.get_instance()
    if not db:
        LOG.error("Error checking Central Cloud. Database API isn't available")
        return False

    system = db.isystem_get_one()
    try:
        if (system.distributed_cloud_role ==
           constants.DISTRIBUTED_CLOUD_ROLE_SYSTEMCONTROLLER):
            return True
        else:
            LOG.info("System role isn't DC Central Cloud")
    except AttributeError:
        return False


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


def is_ceph_backend_available(ceph_type: str =
                              constants.SB_TYPE_CEPH) -> bool:
    """Checks if the given Ceph storage backend type is available

    Args:
        backend (str): Ceph backend type (e.g., "ceph" or "ceph-rook").

    Returns:
        tuple[bool, str]:
            bool: True if the given Ceph backend type is available, False otherwise
            message: Message complementing the return when bool is false
    """
    db = dbapi.get_instance()
    if db is None:
        message = app_constants.DB_API_NOT_AVAILABLE
        LOG.error(message)
        return False, message

    ceph_backends = db.storage_backend_get_list_by_type(
        backend_type=ceph_type)
    if (not ceph_backends) or (len(ceph_backends) == 0):
        message = f"No {ceph_type} backend available"
        LOG.warning(message)
        return False, message

    state = ceph_backends[0].state
    task = ceph_backends[0].task

    if ceph_type == constants.SB_TYPE_CEPH:
        # Based on tests, for host ceph the task value cannot be verified as
        # 'applied'. Sometimes we can see the task=None even for healthy ceph
        available = (state == constants.SB_STATE_CONFIGURED)
    else:
        available = (state == constants.SB_STATE_CONFIGURED) \
                    and (task == constants.APP_APPLY_SUCCESS)

    if not available and ceph_type == constants.SB_TYPE_CEPH_ROOK:
        LOG.error(f"{ceph_type} backend is not available - "
                    f"state={state}, task={task}")
        return False, app_constants.CEPH_BACKEND_NOT_CONFIGURED
    return available, ""


def is_rook_ceph_api_available() -> bool:
    """Check if Rook Ceph manager API is available (running and responding)

    Returns:
        bool: True if Rook Ceph manager API is available, False otherwise
    """
    # Check if Rook Ceph manager pods are running
    try:
        label = f"app={app_constants.CEPH_ROOK_MANAGER_APP}"
        field_selector = app_constants.POD_SELECTOR_RUNNING
        kube = kubernetes.KubeOperator()
        pods = kube.kube_get_pods_by_selector(app_constants.HELM_NS_ROOK_CEPH,
                                              label,
                                              field_selector)
        if len(pods) == 0:
            LOG.error("Rook Ceph manager API is not running")
            return False
    except Exception as e:
        LOG.warning(f"Cannot check Rook Ceph API pods: {str(e)}")

    # Check if Rook Ceph manager API is responding
    ceph_api = ceph.CephWrapper()
    try:
        ceph_api.fsid(body='text', timeout=10)
    except Exception as e:
        LOG.error(f"Rook Ceph manager API is not responding: {str(e)}")
        return False
    LOG.info("Rook Ceph manager API is available")
    return True


def is_openstack_enabled_compute_node(host, host_labels) -> bool:
    """
    Check if a given host follows a set of rules to be considered 'openstack enabled'.
    The host must be a unlocked/provisioned Compute/Worker node.

    Args:
        host (ihost object): Host to be checked.
        host_labels (dict):  A dictionary of labels associated with the host.

    Returns:
        bool: True if conditions are met; False otherwise.
    """
    if constants.COMPUTE_NODE_LABEL not in host_labels:
        return False
    if constants.WORKER not in cutils.get_personalities(host):
        return False
    if host.invprovision in [constants.PROVISIONED, constants.PROVISIONING]:
        return True
    if host.ihost_action in [constants.UNLOCK_ACTION, constants.FORCE_UNLOCK_ACTION]:
        return True
    return False


def get_openstack_enabled_compute_nodes(hosts, labels_by_host) -> list:
    """
    Given a list of hosts, selects the ones that are 'openstack enabled'.

    Args:
        host (list): List of ihosts objects in the system.
        labels_by_host (dict): Dict that associate labels with each host by its ID.

    Returns:
        list: Subset of hosts that are 'openstack enabled'.
    """
    enabled_hosts = []
    for host in hosts:
        if is_openstack_enabled_compute_node(host, labels_by_host.get(host.id, set())):
            enabled_hosts.append(host)
    return enabled_hosts


def squash_collection_elements(collection) -> set:
    """
    Given a collection of iterable objects (sets, lists, tuples), squash all
    the unique elements into one single set

    Args:
        collection (collection of iterables): The collecton of iterables that will be
         squashed

    Returns:
        set: A set containing the unique elements found in the collection items.
    """
    squashed = set()
    for item in collection:
        squashed.update(i for i in item)
    return squashed


def is_a_valid_vswitch_label_combination(vswitch_labels, label_combinations=None) -> bool:
    """
    Check if a given set of vswitch labels is a valid combination of labels.

    Args:
        vswitch_labels (set): Set of vswitch labels to be validated.
        label_combinations (list, optional): If given, use this list of label
         combinations to build the set of vswitch labels. If not given, it will
         use the VSWITCH_ALLOWED_COMBINATIONS constant instead.

    Returns:
        bool: True if combination is valid, False otherwise
    """
    if not label_combinations:
        label_combinations = app_constants.VSWITCH_ALLOWED_COMBINATIONS
    return vswitch_labels in label_combinations


def get_interface_datanets(db=None) -> dict:
    """
    Retrieves all interface data network objects from the given database

    Args:
        db: The database instance. If not given, the default instance is used.

    Returns:
        list: A list with the interface data network objects.
    """
    if db is None:
        db = dbapi.get_instance()
    return db.interface_datanetwork_get_all()


def get_labels_by_host(labels) -> dict:
    """
    Given a set of labels, build a dict in the format 'host_id':'label=value' for
    each label

    Args:
        labels (iterable): An iterable object containing a set os labels.

    Returns:
        dict: A dict in the format 'host_id':'label=value'
    """
    labels_by_host = dict()
    for label in labels:
        labels_by_host.setdefault(label.host_id, set()).add(
            label.label_key + "=" + label.label_value.lower())
    return labels_by_host


def get_system_vswitch_labels(db, label_combinations=None) -> tuple[set, set]:
    """
    Check for the vswitch labels in the system and returns them as a set.

    Args:
        db (dbapi instance): Instance of the API's database.
        label_combinations (list, optional): If given, use this list of label
         combinations to build the set of vswitch labels. If not given, it will
         use the VSWITCH_ALLOWED_COMBINATIONS constant instead.

    Returns:
        tuple: A tuple of 2 sets: (system_labels, conflicts). The first element
        contains the set of valid system labels found and the second one is the
        set of conflicting labels.
    """

    system_vswitch_labels = set()
    conflicts = set()

    valid_combinations = set()
    invalid_combinations = set()

    if not label_combinations:
        label_combinations = app_constants.VSWITCH_ALLOWED_COMBINATIONS
    allowed_labels = squash_collection_elements(label_combinations)

    hosts = db.ihost_get_list()
    labels = db.label_get_all()

    labels_by_host = get_labels_by_host(labels)
    enabled_hosts = get_openstack_enabled_compute_nodes(hosts, labels_by_host)

    if not enabled_hosts:
        # If no hosts were found, both sets must be empty
        return set(), set()

    # Here we loop through all enabled hosts, getting the vswitch labels combninations for
    #  each one. Then we group the combinations as tuples into 'valid' and 'invalid' sets.
    #  At the end we check if there are invalid combinations or there are more than one
    #  valid combination to add them to the 'conflicts' set.
    for host in enabled_hosts:
        # Get the labels that match the 'allowed_labels' set.
        host_vswitch_labels = allowed_labels.intersection(labels_by_host.get(host.id))
        if is_a_valid_vswitch_label_combination(host_vswitch_labels, label_combinations):
            # Add the valid combination on this host to the 'valid' set
            valid_combinations.add(tuple(host_vswitch_labels))
        else:
            # Invalid combination found on the host: add to the 'invalid' set
            if len(host_vswitch_labels) == 0:
                invalid_combinations.add((app_constants.VSWITCH_LABEL_NONE,))
            else:
                invalid_combinations.add(tuple(host_vswitch_labels))

    # Checking if different combinations were found on different hosts. If true, add
    #  to the invalid set.
    if len(valid_combinations) > 1:
        invalid_combinations.update(valid_combinations)
        valid_combinations = set()

    # Squashing the valid vswitch label combinations into a set of labels
    system_vswitch_labels = squash_collection_elements(valid_combinations)

    # Squashing the invalid vswitch label combinations into a set of labels
    conflicts = squash_collection_elements(invalid_combinations)

    return system_vswitch_labels, conflicts


def get_current_vswitch_label(label_combinations=None) -> set:
    """
    Returns the current vswitch label on the system.

    Args:
        label_combinations (list, optional): If given, use this list of label
         combinations to build the set of vswitch labels. If not given, it will
         use the VSWITCH_ALLOWED_COMBINATIONS constant instead.

    Returns:
        set: the current valid vswitch label combination of the system;
        returns empty if invalid/not found
    """

    if not label_combinations:
        label_combinations = app_constants.VSWITCH_ALLOWED_COMBINATIONS

    current_vswitch_labels = get_vswitch_label_from_override_file()
    if is_a_valid_vswitch_label_combination(current_vswitch_labels, label_combinations):
        LOG.debug("Vswitch label was found in override file.")
        return current_vswitch_labels

    LOG.debug("Vswitch label was not found in override file. Searching compute labels.")

    # If vswitch label not found in file or invalid, try to search in the nodes' labels
    db = dbapi.get_instance()
    if not db:
        LOG.error("Database API is not available.")
        return set()

    vswitch_labels, conflicts = get_system_vswitch_labels(db, label_combinations)

    current_vswitch_labels = set()
    if len(conflicts) == 0:
        if len(vswitch_labels) > 0:
            LOG.info(f"Vswitch labels found: {','.join(map(str, vswitch_labels))}.")
            current_vswitch_labels = vswitch_labels
        else:
            LOG.error("There are no openstack-enabled compute nodes.")
    else:
        if len(conflicts) == 1:
            if app_constants.VSWITCH_LABEL_NONE in conflicts:
                if len(vswitch_labels) == 0:
                    LOG.error("No vswitch labels found on any openstack host in the system.")
                else:
                    LOG.error("There are openstack hosts without vswitch labels.")
        else:
            if app_constants.VSWITCH_LABEL_NONE in conflicts:
                LOG.error("There are openstack hosts with divergent vswitch labels in the system"
                      " and/or there are openstack hosts without vswitch labels.")
            else:
                LOG.error("There are openstack hosts with divergent vswitch labels in the system.")

    return current_vswitch_labels


def get_vswitch_label_from_override_file() -> set:
    """
    Searches for the vswitch type label on the Neutron chart override file.

    Returns:
        set: Vswitch type labels if found; {VSWITCH_LABEL_NONE} if not found.
    """
    labels = _get_value_from_application(
        default_value=[app_constants.VSWITCH_LABEL_NONE],
        chart_name=app_constants.HELM_CHART_NEUTRON,
        override_name="vswitch_labels"
    )
    return set(labels)


def is_vswitch_combination_enabled(vswitch_combination, label_combinations=None) -> bool:
    """
    Check if the given vswitch label combination is enabled.

    Args:
        vswitch_combination (set): The vswitch label combination to be checked.
        label_combinations (list, optional): Collection of possible vswitch label combinations

    Returns:
        bool: True if vswitch label is found and enabled.
    """
    vswitch_labels = get_current_vswitch_label(label_combinations)
    return vswitch_labels == vswitch_combination


def is_openvswitch_enabled(label_combinations=None) -> bool:
    """
    Check if openvswitch is enabled.

    Returns:
        bool: True if openvswitch is enabled.
        label_combinations (list, optional): Collection of possible vswitch label combinations
    """
    return is_vswitch_combination_enabled({app_constants.OPENVSWITCH_LABEL}, label_combinations)


def is_openvswitch_dpdk_enabled(label_combinations=None) -> bool:
    """
    Check if openvswitch-dpdk is enabled.

    Returns:
        bool: True if openvswitch-dpdk is enabled.
        label_combinations (list, optional): Collection of possible vswitch label combinations
    """
    return is_vswitch_combination_enabled(
        {app_constants.OPENVSWITCH_LABEL, app_constants.DPDK_LABEL}, label_combinations
    )


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
            LOG.error(f"Stderr: {process.stderr.rstrip()}")
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


def get_app_version_list(base_dir: str, app_name: str) -> list:
    """
    Retrieve a list of versions for a given application from YAML files.

    Args:
        base_dir (str): The base directory where application data is stored.
        app_name (str): The name of the application.

    Returns:
        list: A list of versions for the specified application.
    """
    return os.listdir(os.path.join(base_dir, app_name))


def get_image_list(image_dir: str) -> list:
    """
    Retrieve a list of images for a given application from YAML files.

    Args:
        image_dir (str): The base directory where application data is stored.

    Returns:
        list: A list of images for the specified application.
    """
    with open(image_dir, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)["download_images"]


def get_residual_images(image_file_dir: str, app_version: str, app_version_list: list) -> list:
    """
    Retrieve a list of residual images for a given application.

    Args:
        image_file_dir (str): The directory containing the image files.
        app_version (str): The specific version of the application.
        app_version_list (list): A list of all available application versions.

    Returns:
        list: A list of residual images that are present in older versions
              but not in the current version.
    """

    new_images_list = get_image_list(image_file_dir)
    app_version_list.remove(app_version)

    old_images_list = []
    last_version = app_version
    for version in app_version_list:
        file_name = image_file_dir.replace(last_version, version)
        old_images_list.extend(get_image_list(file_name))
        last_version = version

    return list(set(old_images_list) - set(new_images_list))


def delete_residual_images(image_list: list):
    """Remove a list of images from the system registry.
    Args:
        image (list): A list of image names to be removed.
    """

    image_json = list_crictl_images()

    for image in image_list:
        image_id = get_image_id(image, image_json)
        if not image_id:
            LOG.error(f"Image {image} not found in the system registry.")
            continue
        LOG.info(f"Removing residual image: {image}")
        cmd = [
            "crictl", "rmi", image_id
        ]
        try:
            process = subprocess.run(
                    args=["bash", "-c", f"source /etc/platform/openrc && {' '.join(cmd)}"],
                    capture_output=True,
                    text=True,
                    shell=False)

            LOG.info(f"Stdout: {process.stdout}")
            LOG.info(f"Stderr: {process.stderr}")
            process.check_returncode()
        except Exception as e:
            LOG.error(f"Unexpected error while removing image {image}: {e}")


def list_crictl_images() -> json:
    """List all images in the system registry.
    Returns: A dict of images in the system registry.
    """
    cmd = [
        "crictl", "images", "--output", "json"
    ]
    try:
        process = subprocess.run(
                args=["bash", "-c", f"source /etc/platform/openrc && {' '.join(cmd)}"],
                capture_output=True,
                text=True,
                shell=False)

        LOG.info(f"Stderr: {process.stderr}")
        process.check_returncode()
        return json.loads(process.stdout)
    except Exception as e:
        LOG.error(f"Unexpected error while listing images: {e}")
        return None


def get_image_id(image_name: str, image_json: json) -> str:
    """Get the image ID from the system registry.
    Args:
        image_name (str): The name of the image.
        image_json (json): The dict of images in the system registry.
    Returns:
        str: The image ID.
    """
    for image in image_json["images"]:
        if image_name in image["repoTags"]:
            return image["id"]
    return None


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
            "get", "volumesnapshotclasses.snapshot.storage.k8s.io",
            snapshot_class
        ]
        send_cmd_read_response(cmd)

    except Exception:
        # Create class
        LOG.info(f"Trying to create snapshot class {snapshot_class}")

        rook_ceph, _ = is_ceph_backend_available(
                ceph_type=constants.SB_TYPE_CEPH_ROOK)
        try:
            if rook_ceph:
                secret_name = app_constants.CEPH_ROOK_RBD_SECRET_NAME
                secret_ns = app_constants.HELM_NS_ROOK_CEPH
                driver = app_constants.CEPH_ROOK_RBD_DRIVER
                cluster_id = app_constants.HELM_APP_ROOK_CEPH
            else:
                secret_name = app_constants.CEPH_RBD_SECRET_NAME
                secret_ns = helm_common.HELM_NS_RBD_PROVISIONER
                driver = app_constants.CEPH_RBD_DRIVER
                cluster_id = get_ceph_fsid()
            snapclass_dict = {
                "apiVersion": 'snapshot.storage.k8s.io/v1',
                "kind": "VolumeSnapshotClass",
                "deletionPolicy": "Delete",
                "driver": driver,
                "metadata": {
                    "name": snapshot_class,
                },
                "parameters": {
                    "clusterID": cluster_id,
                    "csi.storage.k8s.io/snapshotter-secret-name": secret_name,
                    "csi.storage.k8s.io/snapshotter-secret-namespace": secret_ns,
                    "snapshotNamePrefix": app_constants.CEPH_RBD_SNAPSHOT_PREFIX,
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
            LOG.error("Unexpected error while checking/creating snapshot"
                      f"class {snapshot_class}: {e}")


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


def get_image_rook_ceph():
    """Get client image to be used for rook ceph deployments

    :returns: str -- The image in the formart <repository>:tag
    """
    return _get_value_from_application(
        default_value=f'{app_constants.CEPH_ROOK_IMAGE_DEFAULT_REPO}:'
                      f'{app_constants.CEPH_ROOK_IMAGE_DEFAULT_TAG}',
        chart_name=app_constants.HELM_CHART_CLIENTS,
        override_name=f'images.tags.{app_constants.CEPH_ROOK_IMAGE_OVERRIDE}'
    )


def force_app_reconciliation(app_op: kube_app.AppOperator,
                             app: kube_app.AppOperator.Application):
    """Force FluxCD reconciliation for all the app helmreleases

    Args:
        app_op (AppOperator): System Inventory AppOperator object
        app (AppOperator.Application): Application we are recovering from
    """
    charts = {
        c.metadata_name: {
            "namespace": c.namespace,
            "chart_label": c.chart_label,
            "helm_repo_name": c.helm_repo_name
        }
        for c in app_op._get_list_of_charts(app)
    }
    for release_name, chart_obj in list(charts.items()):
        LOG.info(f"Forcing FluxCD reconciliation for helmrelease {release_name}"
                 f" of application {app.name} {app.version}")
        try:
            helm_utils.call_fluxcd_reconciliation(release_name,
                                                  chart_obj["namespace"])
        except Exception as e:
            LOG.error(f"Error while forcing FluxCD reconciliation for "
                      f"helmrelease {release_name} of application {app.name} "
                      f"{app.version}: {e}")


def get_hosts_uuids() -> list[dict]:
    """
    Retrieve a list containing dicts relating each compute node
    hostname in the system with its respective UUID

    Returns:
        list[dicts]: list of dicts containing the keys "name" and "uuid"
        for each compute node found.
    """
    db = dbapi.get_instance()
    hosts = db.ihost_get_list()
    labels = db.label_get_all()

    hosts_uuids_list = []

    labels_by_host = get_labels_by_host(labels)
    enabled_hosts = get_openstack_enabled_compute_nodes(hosts, labels_by_host)

    for host in enabled_hosts:
        hostname = str(host.hostname)
        uuid = str(host.uuid)
        hosts_uuids_list.append(
            {
                'name': hostname,
                'uuid': uuid,
            }
        )
    return hosts_uuids_list


def get_ip_families() -> set:
    """
    Checks the current ip families supported by the cluster service network.

    Returns:
        set of int: ip families supported (4 or 6). The sysninv contants
        IPV4_FAMILY and IPV6_FAMILY can be used to check the ip families.
        returns an empty set if ip families are invalid or cannot be checked.
    """
    db = dbapi.get_instance()
    try:
        network = db.network_get_by_type(constants.NETWORK_TYPE_CLUSTER_SERVICE)
    except exception.NetworkTypeNotFound:
        LOG.error("Error checking ip families deployed. Invalid network type "
                  f"{constants.NETWORK_TYPE_CLUSTER_SERVICE}")
        return set()

    ip_families = set()
    net_addr_pools = db.network_addrpool_get_by_network_id(network.id)
    for net_pool in net_addr_pools:
        pool = db.address_pool_get(net_pool.address_pool_uuid)
        ip_families.add(pool.family)

    if len(ip_families) == 0:
        LOG.error("Error checking ip families deployed. Couldn't recover "
                  "address pools associated to the cluster service network.")
    LOG.info(f"IP Families supported: {ip_families}")
    return ip_families


def is_ipv4() -> bool:
    """
    Check if the cluster service network is deployed on IPv4 only mode.

    Returns:
        bool: True if the cluster service network is deployed on IPv4 only mode,
        False otherwise.
    """
    ip_families = get_ip_families()
    return (constants.IPV4_FAMILY in ip_families) and \
           (constants.IPV6_FAMILY not in ip_families)


def get_server_list() -> str:
    """
    Retrieve a list of servers for all projects

    Returns:
        str: The output to the command to list servers.
    """
    cmd = [
        "openstack", "server", "list", "--all-projects"
    ]
    try:
        process = subprocess.run(
                args=["bash", "-c", f"source /var/opt/openstack/admin-openrc && {' '.join(cmd)}"],
                capture_output=True,
                text=True,
                shell=False)

        LOG.info(f"Stdout: {process.stdout}")
        LOG.info(f"Stderr: {process.stderr}")
        process.check_returncode()
        servers = str(process.stdout)
        return servers.strip()
    except Exception as e:
        LOG.error(f"Unexpected error while retrieving servers list: {e}")
        # If the app fails to apply or is aborted before the clients pod is up
        # it will fall in this exception. This will return an empty string
        # to ensure that the return is not None
        return ""


def is_dex_enabled() -> bool:
    """
    Determine whether DEX integration is enabled in Keystone overrides.

    Returns:
        bool: True if DEX integration is enabled, False otherwise.
    """
    enabled = _get_value_from_application(
        default_value=False,
        chart_name=app_constants.HELM_CHART_KEYSTONE,
        override_name="conf.federation.dex_idp.enabled")

    return enabled


def get_dex_issuer_url(db, dex_enabled) -> str:
    """
    Retrieve the OIDC issuer URL from system parameters.

    Args:
        db: The system database instance.
        dex_enabled (bool): Indicates if Dex is enabled via user overrides.

    Returns:
        str: The OIDC issuer URL if it exists. Returns an empty string if Dex is disabled
            and the parameter is not found.

    Raises:
        NotFound: If Dex is enabled but the OIDC issuer URL cannot be retrieved.
    """
    try:
        oidc_issuer_url = db.service_parameter_get_one(
            service=constants.SERVICE_TYPE_KUBERNETES,
            section=constants.SERVICE_PARAM_SECTION_KUBERNETES_APISERVER,
            name=constants.SERVICE_PARAM_NAME_OIDC_ISSUER_URL)
        return oidc_issuer_url.value
    except Exception as e:
        if dex_enabled:
            LOG.error(f"Failed to retrieve OIDC issuer URL: {e}")
            raise exception.NotFound("Failed to retrieve OIDC issuer URL")
        else:
            return ""


def get_dex_health_check_config() -> dict:
    """
    Return Dex health check settings drawn from Helm overrides.

    Returns:
        dict: A dictionary containing timeout, retries, verify and endpoint entries
              that define how the Dex health endpoint should be probed.
    """

    defaults = {
        "timeout": app_constants.DEX_HEALTH_CHECK_DEFAULT_TIMEOUT,
        "retries": app_constants.DEX_HEALTH_CHECK_DEFAULT_RETRIES,
        "verify": app_constants.DEX_HEALTH_CHECK_DEFAULT_VERIFY,
        "endpoint": app_constants.DEX_HEALTH_CHECK_DEFAULT_ENDPOINT,
    }

    timeout = _get_value_from_application(
        default_value=defaults["timeout"],
        chart_name=app_constants.HELM_CHART_KEYSTONE,
        override_name="conf.federation.dex_conf.timeout",
    )
    retries = _get_value_from_application(
        default_value=defaults["retries"],
        chart_name=app_constants.HELM_CHART_KEYSTONE,
        override_name="conf.federation.dex_conf.retries",
    )
    verify = _get_value_from_application(
        default_value=defaults["verify"],
        chart_name=app_constants.HELM_CHART_KEYSTONE,
        override_name="conf.federation.dex_conf.verify",
    )
    endpoint = _get_value_from_application(
        default_value=defaults["endpoint"],
        chart_name=app_constants.HELM_CHART_KEYSTONE,
        override_name="conf.federation.dex_conf.probe_endpoint",
    )

    config = {
        "timeout": timeout,
        "retries": retries,
        "verify": verify,
        "endpoint": endpoint,
    }

    return config


def oidc_parameters_exist(db) -> bool:
    """
    Check if all required OIDC parameters are present in the system.

    Args:
        db: Sysinv DB connection used to query service parameters.

    Returns:
        bool: True when every required OIDC parameter exists, False otherwise.
    """

    required_params = [
        constants.SERVICE_PARAM_NAME_OIDC_ISSUER_URL,
        constants.SERVICE_PARAM_NAME_OIDC_CLIENT_ID,
        constants.SERVICE_PARAM_NAME_OIDC_USERNAME_CLAIM,
        constants.SERVICE_PARAM_NAME_OIDC_GROUPS_CLAIM,
    ]

    for param in required_params:
        try:
            db.service_parameter_get_one(
                service=constants.SERVICE_TYPE_KUBERNETES,
                section=constants.SERVICE_PARAM_SECTION_KUBERNETES_APISERVER,
                name=param,
            )
        except Exception as e:
            LOG.warning(f"OIDC parameter missing: {param} ({e})")
            return False

    return True


def check_dex_healthy(db, dex_enabled) -> bool:
    """
    Check Dex health using the OIDC issuer URL (/healthz endpoint).

    Args:
        db: Sysinv DB connection used to obtain service parameters.
        dex_enabled (bool): Flag indicating whether Dex should be considered enabled.

    Returns:
        bool: True when the health endpoint responds successfully, False otherwise.
    """

    issuer_url = get_dex_issuer_url(db, dex_enabled)
    if not issuer_url:
        LOG.warning("Dex issuer URL is empty.")
        return False

    health_cfg = get_dex_health_check_config()

    verify_option = health_cfg.get("verify", app_constants.DEX_HEALTH_CHECK_DEFAULT_VERIFY)
    retries = health_cfg.get("retries", app_constants.DEX_HEALTH_CHECK_DEFAULT_RETRIES)
    timeout = health_cfg.get("timeout", app_constants.DEX_HEALTH_CHECK_DEFAULT_TIMEOUT)
    endpoint = health_cfg.get("endpoint", app_constants.DEX_HEALTH_CHECK_DEFAULT_ENDPOINT)
    health_url = issuer_url.rstrip("/") + endpoint

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(health_url, timeout=timeout, verify=verify_option)

            if not response.ok:
                LOG.warning(
                    f"Dex health check attempt {attempt}/{retries} failed "
                    f"(HTTP {response.status_code})."
                )
            else:
                LOG.info("Dex health check passed.")
                return True
        except requests.exceptions.RequestException as exc:
            LOG.error(
                "Error during Dex health check on attempt "
                f"{attempt}/{retries}: {exc}"
            )

    return False
