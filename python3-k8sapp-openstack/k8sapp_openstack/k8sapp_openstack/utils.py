#
# Copyright (c) 2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from grp import getgrnam
import os
from pathlib import Path
from pwd import getpwnam
import shutil
from typing import Generator

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
