#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

from pytest import fixture

from tests.fv_rbac import debug1
from tests.fv_rbac import OpenStackNetworkingSetup
from tests.fv_rbac import OpenStackTestingSetup


@fixture(scope='session')
def rbac_setup(request):

    if debug1:
        print("\nSession Initialization")

    cfg = OpenStackTestingSetup()

    # Create projects
    cfg._create_project("project1", description="project1 for rbac test1")
    cfg._create_project("project2", description="project2 for rbac test1")

    # NOTE(tbrito): assume roles are already created
    # Create roles
    # for role in ["project_readonly", "project_admin"]:
    #     cfg._create_role(role)

    # Create users
    for user in cfg.users:
        cfg._create_user(user)

    # Assign Roles to Users
    cfg._grant_role("project_admin", "user11", "project1")
    cfg._grant_role("member", "user12", "project1")
    cfg._grant_role("project_readonly", "user13", "project1")
    cfg._grant_role("admin", "user02", "project2")
    cfg._grant_role("project_admin", "user21", "project2")
    cfg._grant_role("member", "user22", "project2")
    cfg._grant_role("project_readonly", "user23", "project2")

    image = cfg._create_admin_image()

    def teardown():

        if debug1:
            print("\nSession Teardown")

        cfg._delete_admin_image(image)

        cfg._revoke_role("project_admin", "user11", "project1")
        cfg._revoke_role("member", "user12", "project1")
        cfg._revoke_role("project_readonly", "user13", "project1")
        cfg._revoke_role("admin", "user02", "project2")
        cfg._revoke_role("project_admin", "user21", "project2")
        cfg._revoke_role("member", "user22", "project2")
        cfg._revoke_role("project_readonly", "user23", "project2")

        for user in cfg.users:
            cfg._delete_user(user)

        # NOTE(tbrito): Roles should NOT be removed on a live deployment
        # for role in ["project_readonly", "project_admin"]:
        #     cfg._delete_role(role)

        for project in ["project1", "project2"]:
            cfg._delete_project(project)

    request.addfinalizer(teardown)

    return cfg


@fixture(scope='session')
def network_admin_setup(request, rbac_setup):

    cfg = OpenStackNetworkingSetup()

    # Create segment ranges based on projects
    cfg._create_network_segment_range(
        "group0-ext-r0",
        shared=True,
        network_type="vlan",
        physical_network="group0-data0",
        minimum=10, maximum=10
    )
    cfg._create_network_segment_range(
        "group0-data0-r0",
        project_name="project1",
        shared=False,
        network_type="vlan",
        physical_network="group0-data0",
        minimum=400, maximum=499
    )
    cfg._create_network_segment_range(
        "group0-data0b-r0",
        shared=True,
        network_type="vlan",
        physical_network="group0-data0",
        minimum=500, maximum=599
    )
    cfg._create_network_segment_range(
        "group0-data1-r0",
        project="project2",
        shared=False,
        network_type="vlan",
        physical_network="group0-data1",
        minimum=600, maximum=699
    )

    def network_admin_teardown():
        cfg._delete_network_segment_range("group0-data1-r0")
        cfg._delete_network_segment_range("group0-data0b-r0")
        cfg._delete_network_segment_range("group0-data0-r0")
        cfg._delete_network_segment_range("group0-ext-r0")

    request.addfinalizer(network_admin_teardown)
    return cfg
