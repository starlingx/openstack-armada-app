#
# Copyright (c) 2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from grp import getgrnam
import os
from pathlib import Path
from pwd import getpwnam
import re
import shutil
from typing import Generator

from oslo_log import log as logging
from sysinv.common import constants
from sysinv.common import utils as cutils
from sysinv.db import api as dbapi
import yaml

from k8sapp_openstack.common import constants as app_constants

LOG = logging.getLogger(__name__)


def _get_value_from_application(
    default_value: str,
    chart_name: str,
    override_name: str
) -> str:
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


def is_openstack_https_ready():
    """Return whether the openstack certificates are ready or not.

    Returns true if the HTTPs certificates are present in the
    defined directory.
    """
    certificates = get_openstack_certificate_files()
    for cert_name in certificates:
        # The CA certificate (Certificate Authority) is not
        # required for HTTPs to be enabled, so we skip it.
        if cert_name == app_constants.OPENSTACK_CERT_CA:
            continue

        # Check if the file exist
        if not os.path.isfile(certificates[cert_name]):
            return False
    return True


def get_openstack_certificate_files() -> dict[str, str]:
    """Get Openstack certificate files

    :returns: dict[str, str] -- a dictionary of the files
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
        app_constants.OPENSTACK_CERT: openstack_cert_file_path,
        app_constants.OPENSTACK_CERT_KEY: openstack_cert_key_file_path,
        app_constants.OPENSTACK_CERT_CA: openstack_cert_ca_file_path
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
