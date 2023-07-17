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


def change_file_group_ownership(
    file: str,
    group: str,
    recursive: bool = False
) -> None:
    """Change file's group ownership.

    :param file: The file path.
    :param group: The group name.
    :param recursive: bool -- The flag that indicates whether permissions
                              should be changed recursively or not.
    """

    cmd = ["chgrp", group, file]

    if recursive:
        cmd.insert(1, "-R")

    _, stderr = cutils.trycmd(*cmd, run_as_root=True)

    if stderr:
        LOG.warning(
            f"Failed to change group ownership of `{file}` "
            f"to `{group}`: {stderr}"
        )


def change_file_owner(
    file: str,
    user: str = "",
    group: str = "",
    recursive: bool = False
) -> None:
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
        return

    cmd = ["chown", ownership, file]

    if recursive:
        cmd.insert(1, "-R")

    _, stderr = cutils.trycmd(*cmd, run_as_root=True)

    if stderr:
        LOG.warning(
            f"Failed to change ownership of `{file}` "
            f"to `{ownership}`: {stderr}"
        )


def change_file_mode(
    file: str,
    mode: str,
    recursive: bool = False
) -> None:
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


def create_openstack_volume_mount() -> None:
    """Create OpenStack volume mount directory."""

    p = Path(app_constants.OPENSTACK_VOLUME_MOUNT_DIR)
    p.mkdir(exist_ok=True)

    # Change modes of the volume mount directory.
    change_file_mode(
        str(p),
        mode="770",
        recursive=True
    )

    # Change ownership of the volume mount directory.
    change_file_owner(
        str(p),
        user="sysadmin",
        group=app_constants.HELM_NS_OPENSTACK,
        recursive=True
    )


def delete_openstack_volume_mount() -> bool:
    """Delete OpenStack volume mount.

    :returns: bool -- True, if volume mount directory was successfully deleted.
                      False, if otherwise.
    """

    # Search for additional files that might have been created by users.
    directories = [app_constants.OPENSTACK_VOLUME_MOUNT_DIR]
    while directories:
        p = Path(directories.pop(0))
        for pathname in p.glob("*"):
            if pathname.is_dir():
                directories.append(str(pathname))
                continue
            else:
                # Ignore files in the root directory.
                if str(p) == app_constants.OPENSTACK_VOLUME_MOUNT_DIR:
                    continue

                # If there is at least one file created by users outside the
                # root directory, that is, in a user subdirectory, it means
                # that we can't remove the volume mount directory.
                LOG.warning(
                    f"Unable to delete OpenStack volume mount directory "
                    f"`{app_constants.OPENSTACK_VOLUME_MOUNT_DIR}`. "
                    f"There are one or more user files in subdirectories."
                )
                return False

    shutil.rmtree(
        app_constants.OPENSTACK_VOLUME_MOUNT_DIR, ignore_errors=True
    )

    return True
