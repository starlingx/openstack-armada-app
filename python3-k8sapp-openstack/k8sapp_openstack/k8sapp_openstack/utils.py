#
# Copyright (c) 2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from pathlib import Path
import shutil

from oslo_log import log as logging
from sysinv.common import constants
from sysinv.common import utils as cutils
from sysinv.db import api as dbapi
import yaml

from k8sapp_openstack.common import constants as app_constants

LOG = logging.getLogger(__name__)


def https_enabled():
    db = dbapi.get_instance()
    if db is None:
        return False

    isystem = db.isystem_get_one()
    return isystem.capabilities.get("https_enabled", False)


def is_openstack_https_certificates_ready():
    """Return whether the openstack certificates are ready or not.

    Returns True if the openstack, openstack_ca and ssl_ca
    certificates are installed in the system.
    """
    db = dbapi.get_instance()
    if db is None:
        return False

    cert_openstack, cert_openstack_ca, cert_ssl_ca = False, False, False
    certificates = db.certificate_get_list()
    for certificate in certificates:
        if certificate.certtype == constants.CERT_MODE_OPENSTACK:
            cert_openstack = True
        elif certificate.certtype == constants.CERT_MODE_OPENSTACK_CA:
            cert_openstack_ca = True
        elif certificate.certtype == constants.CERT_MODE_SSL_CA:
            cert_ssl_ca = True

    return cert_openstack and cert_openstack_ca and cert_ssl_ca


def is_openstack_https_ready():
    """Check if OpenStack is ready for HTTPS.

    Returns true if https is enabled and https certificates are
    installed in the system.
    """
    return https_enabled() and is_openstack_https_certificates_ready()


def change_file_owner(
    file: str,
    user: str = "",
    group: str = "",
    recursive: bool = False
) -> bool:
    """Change file's owner (chown).

    :param file: The file path.
    :param user: The desired user.
    :param group: The desired group.
    :param recursive: bool -- The flag that indicates whether ownerships
                              should be changed recursively or not.
    """

    ownership = ""

    if user:
        ownership += user

    if group:
        ownership += f":{group}"

    if not ownership:
        return False

    cmd = ["chown", ownership, file]

    if recursive:
        cmd.insert(1, "-R")

    _, stderr = cutils.trycmd(*cmd, run_as_root=True)

    if stderr:
        LOG.warning(
            f"Failed to change ownership of `{file}` "
            f"to `{ownership}`: {stderr}"
        )
        return False
    return True


def change_file_mode(
    file: str,
    mode: str,
    recursive: bool = False
) -> bool:
    """Change file's mode (chmod).


    :param file: The file path.
    :param mode: The desired mode.
    :param recursive: bool -- The flag that indicates whether modes should be
                              changed recursively or not.
    """

    cmd = ["chmod", mode, file]

    if recursive:
        cmd.insert(1, "-R")

    _, stderr = cutils.trycmd(*cmd, run_as_root=True)

    if stderr:
        LOG.warning(
            f"Failed to change mode of `{file}` to `{mode}`: {stderr}"
        )
        return False
    return True


def get_clients_working_directory() -> str:
    """Get OpenStack clients' working directory path.

    :returns: str -- The clients' working directory path.
    """

    # By default, the working directory path is
    # `app_constants.CLIENTS_WORKING_DIR`.
    working_directory = app_constants.CLIENTS_WORKING_DIR

    db = dbapi.get_instance()
    if db is None:
        return working_directory

    # However, the user might have overriden the default
    # working directory path. If that is the case, fetch
    # and return the user-defined path.
    app = cutils.find_openstack_app(db)

    override = db.helm_override_get(
        app_id=app.id,
        name=app_constants.HELM_CHART_CLIENTS,
        namespace=app_constants.HELM_NS_OPENSTACK,
    )

    if override.user_overrides:
        user_overrides = yaml.load(
            override.user_overrides, Loader=yaml.FullLoader
        )
        working_directory = user_overrides.get(
            "workingDirectoryPath", app_constants.CLIENTS_WORKING_DIR
        )
    return working_directory


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

    if path:
        working_directory = path
    else:
        working_directory = get_clients_working_directory()

    # Create clients' working directory.
    # (Ignore if it already exists)
    p = Path(working_directory)
    p.mkdir(exist_ok=True)

    # Change modes of the clients' working directory.
    # If the operation fails, return failure status.
    status = change_file_mode(
        str(p),
        mode="770",
        recursive=True
    )
    if not status:
        return False

    # Change ownership of the clients' working directory.
    # If the operation fails, return failure status.
    status = change_file_owner(
        str(p),
        user="sysadmin",
        group=app_constants.HELM_NS_OPENSTACK,
        recursive=True
    )
    if not status:
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
    directories = [working_directory]
    while directories:
        p = Path(directories.pop(0))
        for pathname in p.glob("*"):
            if pathname.is_dir():
                directories.append(str(pathname))
                continue
            else:
                # Ignore files in the root directory.
                if str(p) == working_directory:
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
