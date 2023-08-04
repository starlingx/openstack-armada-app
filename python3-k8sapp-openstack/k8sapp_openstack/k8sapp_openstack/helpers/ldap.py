#
# Copyright (c) 2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

import re
from typing import List

from oslo_log import log as logging
from sysinv.common import utils as cutils

LOG = logging.getLogger(__name__)


def check_group(group: str) -> bool:
    """Check if group exists.

    :returns: bool -- Returns `True` if group exists.
                      Otherwise, returns `False`.
    """

    stdout = search_group(group=group)

    # If the `ldapsearch` output contains the word "numEntries",
    # the group exists. Otherwise, it does not.
    return "numEntries" in stdout


def search_group(group: str) -> str:
    """Search group.

    :param group: The group name.
    :returns: str -- The `ldapsearch` output.
    """

    cmd = [
        "ldapsearch",
        "-x",
        "-b",
        "ou=Group,dc=cgcs,dc=local",
        f"(cn={group})"
    ]
    stdout, _ = cutils.trycmd(*cmd)
    return stdout


def add_group(group: str) -> bool:
    """Add group.

    :param group: The group name.
    :returns: bool -- `True`, if group has been added.
                      `False`, if otherwise.
    """

    cmd = ["ldapaddgroup", group]
    _, stderr = cutils.trycmd(*cmd, run_as_root=True)

    if stderr:
        LOG.warning(f"Failed to add group `{group}`: {stderr}")
        return False
    return True


def delete_group(group: str) -> bool:
    """Delete group.

    :param group: The group name.
    :returns: bool -- `True`, if group has been deleted.
                      `False`, if otherwise.
    """

    members = list_group_members(group)
    for member in members:
        delete_group_member(member, group)

    cmd = ["ldapdeletegroup", group]
    _, stderr = cutils.trycmd(*cmd, run_as_root=True)

    if stderr:
        LOG.warning(f"Failed to delete group `{group}`: {stderr}")
        return False
    return True


def check_group_member(member: str, group: str) -> bool:
    """Check if group member exists.

    :param member: The member name.
    :param group: The group name.
    :returns: bool -- `True`, if group member exists.
                      `False`, if otherwise.
    """

    stdout = search_group(group=group)

    # If the `ldapsearch` output contains the word "memberUid: {member}",
    # the group member exists. Otherwise, it does not.
    return f"memberUid: {member}" in stdout


def add_group_member(member: str, group: str) -> bool:
    """Add group member.

    :param member: The member name.
    :param group: The group name.
    :returns: bool -- `True`, if member has been added.
                      `False`, if otherwise.
    """

    cmd = ["ldapaddusertogroup", member, group]
    _, stderr = cutils.trycmd(*cmd, run_as_root=True)

    if stderr:
        LOG.warning(
            f"Failed to add user `{member}` to group `{group}`: {stderr}"
        )
        return False
    return True


def delete_group_member(member: str, group: str) -> bool:
    """Delete group member.

    :param member: The member name.
    :param group: The group name.
    :returns: bool -- `True`, if member has been deleted.
                      `False`, if otherwise.
    """

    cmd = ["ldapdeleteuserfromgroup", member, group]
    _, stderr = cutils.trycmd(*cmd, run_as_root=True)

    if stderr:
        LOG.warning(
            f"Failed to delete user `{member}` from group `{group}`: {stderr}"
        )
        return False
    return True


def list_group_members(group: str) -> List[str]:
    """List group members.

    :param group: The group name.
    :returns: List[str] -- The list of members belonging to
                           the specified group.
    """

    # First, run `ldapsearch`.
    stdout = search_group(group=group)

    # Second, verify if the `ldapsearch` output contains the word `memberUid`.
    # If it does, it means that the group contains members.
    return re.findall("(?<=memberUid: )(.*)(?=\n)", stdout)
