#
# Copyright (c) 2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

import subprocess
from typing import List

from oslo_log import log as logging
from sysinv.common import utils as cutils

LOG = logging.getLogger(__name__)


def check_group(group: str) -> bool:
    """Check if group exists.

    :returns: bool -- Returns `True` if group exists.
                      Otherwise, returns `False`.
    """

    # First, run `ldapsearch`.
    cmd_p1 = [
        "ldapsearch",
        "-x",
        "-b",
        "ou=Group,dc=cgcs,dc=local",
        f"(cn={group})",
    ]
    p1 = subprocess.Popen(
        cmd_p1, stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )

    # Second, verify if the `ldapsearch` output contains the word `numEntries`.
    # If it does, it means that the group exists.
    cmd_p2 = ["grep", "numEntries"]
    p2 = subprocess.Popen(cmd_p2, stdin=p1.stdout, stdout=subprocess.PIPE)

    p1.stdout.close()
    p2.communicate()

    if p2.returncode == 0:
        return True

    return False


def add_group(group: str) -> None:
    """Add group.

    :param group: The group name.
    """

    cmd = ["ldapaddgroup", group]
    _, stderr = cutils.trycmd(*cmd, run_as_root=True)

    if stderr:
        LOG.warning(f"Failed to add group `{group}`: {stderr}")


def delete_group(group: str) -> None:
    """Delete group.

    :param group: The group name.
    """

    members = list_group_members(group)
    for member in members:
        delete_group_member(member, group)

    cmd = ["ldapdeletegroup", group]
    _, stderr = cutils.trycmd(*cmd, run_as_root=True)

    if stderr:
        LOG.warning(f"Failed to delete group `{group}`: {stderr}")


def check_group_member(member: str, group: str) -> bool:
    """Check if group member exists.

    :param member: The member name.
    :param group: The group name.
    :returns: bool -- Returns `True` if group member exists.
                      Otherwise, returns `False`.
    """

    # First, run `ldapsearch`.
    cmd_p1 = [
        "ldapsearch",
        "-x",
        "-b",
        "ou=Group,dc=cgcs,dc=local",
        f"(cn={group})",
    ]
    p1 = subprocess.Popen(
        cmd_p1, stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )

    # Second, verify if the `ldapsearch` output contains the word `memberUid`.
    # If it does, it means that the group not only exists, but also contains
    # members.
    cmd_p2 = ["grep", f"memberUid: {member}"]
    p2 = subprocess.Popen(cmd_p2, stdin=p1.stdout, stdout=subprocess.PIPE)

    p1.stdout.close()
    p2.communicate()

    if p2.returncode == 0:
        return True

    return False


def add_group_member(member: str, group: str) -> None:
    """Add group member.

    :param member: The member name.
    :param group: The group name.
    """

    cmd = ["ldapaddusertogroup", member, group]
    _, stderr = cutils.trycmd(*cmd, run_as_root=True)

    if stderr:
        LOG.warning(
            f"Failed to add user `{member}` to group `{group}`: {stderr}"
        )


def delete_group_member(member: str, group: str) -> None:
    """Delete group member.

    :param member: The member name.
    :param group: The group name.
    """

    cmd = ["ldapdeleteuserfromgroup", member, group]
    _, stderr = cutils.trycmd(*cmd, run_as_root=True)

    if stderr:
        LOG.warning(
            f"Failed to delete user `{member}` from group `{group}`: {stderr}"
        )


def list_group_members(group: str) -> List[str]:
    """List group members.

    :param group: The group name.
    :returns: List[str] -- The list of members belonging to
                           the specified group.
    """

    members = []

    # First, run `ldapsearch`.
    cmd_p1 = [
        "ldapsearch",
        "-x",
        "-b",
        "ou=Group,dc=cgcs,dc=local",
        f"(cn={group})",
    ]
    p1 = subprocess.Popen(
        cmd_p1, stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )

    # Second, verify if the `ldapsearch` output contains the word `memberUid`.
    # If it does, it means that the group not only exists, but also contains
    # members.
    cmd_p2 = ["grep", "-Poh", "(?<=memberUid: )(.*)"]
    p2 = subprocess.Popen(cmd_p2, stdin=p1.stdout, stdout=subprocess.PIPE)

    p1.stdout.close()
    stdout, _ = p2.communicate()

    if p2.returncode == 0:
        for user in stdout.decode().split():
            if user:
                members.append(user)

    return members
