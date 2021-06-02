#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

import pytest

from openstack import exceptions
from novaclient import exceptions as ncExceptions
from pprint import pprint
from tests.fv_rbac import debug
from tests.fv_rbac import OpenStackRouterInterface
from tests.test_nova.rbac_nova import OpenStackComputeTesting


@pytest.fixture(scope='class', autouse=True)
def networking_setup(request, network_admin_setup):
    cfg = network_admin_setup
    request.cls.os_sdk_admin_conn = cfg.os_sdk_admin_conn
    request.cls.users = cfg.users
    request.cls.user02 = cfg.user02
    request.cls.user11 = cfg.user11
    request.cls.user12 = cfg.user12
    request.cls.user13 = cfg.user13
    request.cls.user21 = cfg.user21
    request.cls.user22 = cfg.user22
    request.cls.user23 = cfg.user23
    request.cls.env = cfg.env


class TestVM(OpenStackComputeTesting):
    # TC-1
    # Description:
    # - The following user and roles are defined: user11, admin of project1; user12, member of project1; user13, read only of project1.
    # - Users 11/12 can lunch server from image or volume, with either predefined network, or predefined port; while user13 can NOT;
    # - Users 11/12 can access server logs, while user13 can NOT;
    # - Users 11/12 can access server console, while user13 can NOT.
    def test_uc_nova_1(self, tc_teardown):
        """
        # 1. user11 can create an instance
        # 2. user11 can get the console log of the instance
        # 3. user11 can access the VNC console of the instance
        # 4. user13 can NOT get the console log or access the VNC console
        # 5. user12 create an instance
        # 6. user12 can get the console log of the instance
        # 7. user12 can access the VNC console of the instance
        # 8. user13 can NOT get the console log or access the VNC console
        """

        # 1.1. user11 can create an instance

        print ("\nTC-1.1")

        self.set_connections_for_user(self.user11)
        vm11 = self._create_server("vm11-project1", "cirros", "m1.tiny")

        if debug: print(vm11.name)
        if debug: print(vm11.status)

        assert vm11.name == "vm11-project1"
        assert vm11.status == "ACTIVE"
        assert "vm11-project1" in [s.name for s in self._list_servers()]

        # 1.2. user11 can get the console log of the instance

        print ("TC-1.2")

        self.set_connections_for_user(self.user11)

        data = self._get_server_console_output("vm11-project1")

        if debug: pprint(data, indent=4)
        assert data is not None

        # 1.3. user11 can access the VNC console of the instance

        print ("TC-1.3")

        self.set_connections_for_user(self.user11)

        data = self._get_vnc_console("vm11-project1", 'novnc')

        if debug: pprint(data, indent=4)
        assert data is not None

        # 1.4. user13 can NOT get the console log or access the VNC console

        print ("TC-1.4")

        self.set_connections_for_user(self.user13)

        #Note: openstack.exceptions
        with pytest.raises(exceptions.HttpException) as err:
            assert self._get_server_console_output("vm11-project1")
        assert err.match("Policy doesn't allow os_compute_api:os-console-output to be performed")

        #Note: novaclient.exceptions
        with pytest.raises(ncExceptions.Forbidden) as err:
            assert self._get_vnc_console("vm11-project1", 'novnc')
        assert err.match("Policy doesn't allow os_compute_api:os-remote-consoles to be performed")

        # 1.5. user12 can create an instance

        print ("TC-1.5")

        self.set_connections_for_user(self.user12)

        vm12 = self._create_server("vm12-project1", "cirros", "m1.tiny")

        if debug: print(vm12.name)
        if debug: print(vm12.status)

        assert vm12.name == "vm12-project1"
        assert vm12.status == "ACTIVE"
        assert "vm12-project1" in [s.name for s in self._list_servers()]

        # 1.6. user12 can get the console log of the instance

        print ("TC-1.6")

        self.set_connections_for_user(self.user12)

        data = self._get_server_console_output("vm12-project1")

        if debug: pprint(data, indent=4)
        assert data is not None

        # 1.7.user12 can access the VNC console of the instance

        print ("TC-1.7")

        self.set_connections_for_user(self.user12)

        data = self._get_vnc_console("vm12-project1", 'novnc')

        if debug: pprint(data, indent=4)
        assert data is not None

        # 1.8. user13 can NOT get the console log or access the VNC console

        print ("TC-1.8")

        self.set_connections_for_user(self.user13)

        #Note: openstack.exceptions
        with pytest.raises(exceptions.HttpException) as err:
            assert self._get_server_console_output("vm12-project1")
        assert err.match("Policy doesn't allow os_compute_api:os-console-output to be performed")

        #Note: novaclient.exceptions
        with pytest.raises(ncExceptions.Forbidden) as err:
            assert self._get_vnc_console("vm12-project1", 'novnc')
        assert err.match("Policy doesn't allow os_compute_api:os-remote-consoles to be performed")

    # TC-2
    # Description:
    # user11 can manage server: associate floatingip/de-associate floatingip/edit instance/
    # attach volume/detach volume/update metadata/edit security group/pause instance/resume instance /
    # suspend instance/resize instance/lock instance/unlock instance/shelve instance/unshelve instance/
    # soft reboot instance/hard reboot instance/shut off instance/rebuild instance/delete instance,
    # while user12/13 can NOT
    def test_uc_nova_2(self, create_external_network, create_router_vr11, tc_teardown):
        """
        01. user11 can create a floating IP
        02. user11 can start a instance
        03. user11 can associate/disassociate the floating IP to the instance
        04. users 12/13 can NOT  associate/disassociate the floating IP to the instance
        05. user11 can update the name of the instance
        06. users 12/13 can NOT update the instance
        07. user11 can attache/detach a volume to the instance
        08. user12 can attach/detach a volume to the instance, but user13 CAN NOT
        09. user11 can update the metadata of the instance
        10. users 12/13 can NOT update the metadata of the instance
        11. user11 can add a security group the the instance
        12. users 12/13 can NOT add a security group to the instance
        13. user11 can pause/unpause the instance
        14. users 12/13 can NOT pause/unpause the instance
        15. user11 can resize the instance
        16. users 12/13 can NOT resize the instance
        17. user11 can lock/unlock the instance.
        18. users 12/13 can NOT lock/unlock the instance.
        19. user11 can stop the instance
        20. users 12/13 can NOT stop the instance
        21. user11 can soft reboot the instance
        22. users 12/13 can NOT soft reboot the instance
        23. user11 can hard reboot the instance
        24. users 12/13 can NOT hard reboot the instance
        25. user11 can rebuild the instance
        26. users 12/13 can NOT rebuild the instance
        27. user11 can shelve/unshelve the instance
        28. users 12/13 can NOT shelve the instance
        29. users 12/13 can NOT delete the instance
        30. user11 can delete the instance
        """

        # 2.1. user11 can create a floating IP

        print ("\nTC-2.1")

        #Test setup
        extnet, extsubnet = create_external_network

        self.set_connections_for_user(self.user11)
        network11 = self._create_network("network11")
        assert network11 is not None

        subnet11 = self._create_subnet("subnet11", "network11", cidr="10.10.20.0/24", gateway_ip="10.10.20.1")
        assert subnet11 is not None

        vr11 = create_router_vr11

        self.set_connections_for_user(self.user11)
        vr11 = self._add_interface_to_router(OpenStackRouterInterface("vr11", "subnet11"))
        assert subnet11.id in vr11.get("subnet_ids")

        vm11 = self._create_server("vm11", "cirros", "m1.tiny", network_name="network11")
        vm11 = self._get_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"

        network = self._get_network("network11")
        vm11_port = [p for p in self._list_ports(device_id=vm11.id)][0]
        assert vm11_port.network_id == network.id

        #Create action succeeds for the project admin
        fip11 = self._create_floatingip(subnet_id=extsubnet.id, floating_network_id=extnet.id, port_id=vm11_port.id)

        if debug: print(fip11.floating_ip_address)
        assert fip11.floating_ip_address is not None

        # 2.2. user11 can stop/start a instance

        print ("TC-2.2")

        self.set_connections_for_user(self.user11)

        #Test setup
        vm11 = self._get_server("vm11")
        assert vm11.status == "ACTIVE"

        #Stop action succeeds for the project admin
        vm11 = self._stop_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "SHUTOFF"

        #Start action succeeds for the project admin
        vm11 = self._start_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"

        # 2.3. user11 can associate/disassociate the floating IP to the instance

        print ("TC-2.3")

        self.set_connections_for_user(self.user11)

        #Test setup
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"
        if debug: print(fip11.floating_ip_address)
        assert fip11.floating_ip_address is not None

        #Associate action succeeds for the project admin
        self._add_floating_ip_to_server("vm11", fip11)
        vm11 = self._get_server("vm11")
        if debug: print([ip['addr'] for ip in vm11.addresses['network11'] if ip['OS-EXT-IPS:type'] == 'floating'][0])
        assert fip11.floating_ip_address == [ip['addr'] for ip in vm11.addresses['network11'] if ip['OS-EXT-IPS:type'] == 'floating'][0]

        #Disassociate action succeeds for the project admin
        self._remove_floating_ip_from_server("vm11", fip11)
        vm11 = self._get_server("vm11")
        if debug: print([ip['addr'] for ip in vm11.addresses['network11'] if ip['OS-EXT-IPS:type'] == 'floating'][0])
        assert fip11.floating_ip_address not in [ip['addr'] for ip in vm11.addresses['network11'] if ip['OS-EXT-IPS:type'] == 'floating']

        # 2.4. users 12/13 can NOT associate/disassociate the floating IP to the instance

        print ("TC-2.4")

        #Test setup
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"
        if debug: print(fip11.floating_ip_address)
        assert fip11.floating_ip_address is not None

        #Associate attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            #Exception occurs
            with pytest.raises(exceptions.HttpException) as err:
                assert self._add_floating_ip_to_server("vm11", fip11)
            assert err.match("rule:update_floatingip is disallowed by policy")

            vm11 = self._get_server("vm11")
            if debug: print([ip['addr'] for ip in vm11.addresses['network11'] if ip['OS-EXT-IPS:type'] == 'floating'])
            assert fip11.floating_ip_address not in [ip['addr'] for ip in vm11.addresses['network11'] if ip['OS-EXT-IPS:type'] == 'floating']

        #Test setup
        self.set_connections_for_user(self.user11)
        self._add_floating_ip_to_server("vm11", fip11)
        vm11 = self._get_server("vm11")
        if debug: print([ip['addr'] for ip in vm11.addresses['network11'] if ip['OS-EXT-IPS:type'] == 'floating'])
        assert fip11.floating_ip_address in [ip['addr'] for ip in vm11.addresses['network11'] if ip['OS-EXT-IPS:type'] == 'floating']

        #Disassociate attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            #Exception occurs
            with pytest.raises(exceptions.HttpException) as err:
                assert self._remove_floating_ip_from_server("vm11", fip11)
            assert err.match("Access was denied to this resource")

            vm11 = self._get_server("vm11")
            if debug: print([ip['addr'] for ip in vm11.addresses['network11'] if ip['OS-EXT-IPS:type'] == 'floating'])
            assert fip11.floating_ip_address in [ip['addr'] for ip in vm11.addresses['network11'] if ip['OS-EXT-IPS:type'] == 'floating']

        # 2.5. user11 can update the name of the instance

        print ("TC-2.5")

        self.set_connections_for_user(self.user11)

        #Test setup
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"

        #Update action succeeds for the project admin
        vm11 = self._update_server("vm11", name="vm11-project1")
        if debug: print([s.name for s in self._list_servers()])
        assert "vm11-project1" in [s.name for s in self._list_servers()]

        #Test restore
        vm11 = self._update_server("vm11-project1", name="vm11")
        if debug: print([s.name for s in self._list_servers()])
        assert "vm11" in [s.name for s in self._list_servers()]

        # 2.6. users 12/13 can NOT update the instance

        print ("TC-2.6")

        #Update attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)

            #Test setup
            if debug: print([s.name for s in self._list_servers()])
            assert "vm11" in [s.name for s in self._list_servers()]

            #Exception occurs
            with pytest.raises(exceptions.HttpException) as err:
                assert self._update_server("vm11", name="Instance11-Project1")
            assert err.match("Policy doesn't allow os_compute_api:servers:update to be performed")

            assert "Instance11-Project1" not in [s.name for s in self._list_servers()]
            assert "vm11" in [s.name for s in self._list_servers()]

        # 2.7. user11 can attach/detach a volume to the instance

        print ("TC-2.7")

        self.set_connections_for_user(self.user11)

        #Test setup
        vm11 = self._get_server("vm11")
        assert vm11.attached_volumes == []

        volume11 = self._create_volume("volume11")
        volumes = self._list_volumes()
        assert "volume11" in [v.name for v in volumes]

        #Attach action succeeds for the project admin
        self._add_volume_to_server("vm11", "volume11")
        vm11 = self._get_server("vm11")
        assert volume11.id in [v.get("id") for v in vm11.attached_volumes]

        #Detach action succeeds for the project admin
        self._remove_volume_from_server("vm11", "volume11")
        vm11 = self._get_server("vm11")
        assert vm11.attached_volumes == []

        # 2.8. user12 can attach/detach a volume to the instance, but user13 CAN NOT

        print ("TC-2.8")

        self.set_connections_for_user(self.user12)

        #Test setup for user 12
        vm11 = self._get_server("vm11")
        assert vm11.attached_volumes == []

        #Attach action succeeds for user12 (project member)
        self._add_volume_to_server("vm11", "volume11")
        vm11 = self._get_server("vm11")
        assert volume11.id in [v.get("id") for v in vm11.attached_volumes]

        #Detach action succeeds for user12 (project member)
        self._remove_volume_from_server("vm11", "volume11")
        vm11 = self._get_server("vm11")
        assert vm11.attached_volumes == []

        self.set_connections_for_user(self.user13)

        #Test setup for user 13
        vm11 = self._get_server("vm11")
        assert vm11.attached_volumes == []

        #Attach attempt fails for user13 (read only)
        with pytest.raises(exceptions.HttpException) as err:
            assert self._add_volume_to_server("vm11", "volume11")
        assert err.match("Policy doesn't allow os_compute_api:os-volumes-attachments:create to be performed")
        vm11 = self._get_server("vm11")
        assert vm11.attached_volumes == []

        #Test setup for user 13
        self.set_connections_for_user(self.user11)
        self._add_volume_to_server("vm11", "volume11")
        vm11 = self._get_server("vm11")
        assert volume11.id in [v.get("id") for v in vm11.attached_volumes]

        #Detach attempt fails for user13 (read only)
        self.set_connections_for_user(self.user13)
        with pytest.raises(exceptions.HttpException) as err:
            assert self._remove_volume_from_server("vm11", "volume11")
        assert err.match("Policy doesn't allow os_compute_api:os-volumes-attachments:delete to be performed")
        vm11 = self._get_server("vm11")
        assert volume11.id in [v.get("id") for v in vm11.attached_volumes]

        # 2.9. user11 can update (set/modify/delete) the metadata of the instance

        print ("TC-2.9")

        self.set_connections_for_user(self.user11)

        #Test setup
        vm11 = self._get_server("vm11")
        if debug: print(vm11.metadata)
        assert "mykey" not in vm11.metadata

        #Set metadata
        vm11 = self._set_server_metadata("vm11", mykey="myvalue")
        if debug: print(vm11.metadata)
        assert "mykey" in vm11.metadata
        assert vm11.metadata.get("mykey") == "myvalue"

        #Modify metadata
        vm11 = self._set_server_metadata("vm11", mykey="updated-value")
        if debug: print(vm11.metadata)
        assert "mykey" in vm11.metadata
        assert vm11.metadata.get("mykey") == "updated-value"

        #Get metadata
        vm11 = self._get_server_metadata("vm11")
        if debug: print(vm11.metadata)
        assert "mykey" in vm11.metadata
        assert vm11.metadata.get("mykey") == "updated-value"

        #Delete metadata
        self._delete_server_metadata("vm11", ['mykey'])

        vm11 = self._get_server_metadata("vm11")
        if debug: print(vm11.metadata)
        assert "mykey" not in vm11.metadata

        vm11 = self._get_server("vm11")
        if debug: print(vm11.metadata)
        assert "mykey" not in vm11.metadata

        # 2.10. users 12/13 can NOT update the metadata of the instance

        print ("TC-2.10")

        #Test setup
        self.set_connections_for_user(self.user11)
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"
        assert vm11.status == "ACTIVE"
        if debug: print(vm11.metadata)
        assert "mykey" not in vm11.metadata

        #Metadata update (set) attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)

            #Test setup
            vm11 = self._get_server("vm11")
            if debug: print(vm11.metadata)
            assert "mykey" not in vm11.metadata

            #Exception occurs
            with pytest.raises(exceptions.HttpException) as err:
                assert self._set_server_metadata("vm11", mykey="myvalue")
            assert err.match("Policy doesn't allow os_compute_api:server-metadata:create to be performed")
            assert "mykey" not in vm11.metadata

        #Test setup
        self.set_connections_for_user(self.user11)
        vm11 = self._set_server_metadata("vm11", mykey="myvalue")
        if debug: print(vm11.metadata)
        assert "mykey" in vm11.metadata
        assert vm11.metadata.get("mykey") == "myvalue"

        #Metadata update (modify) attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)

            #Test setup
            vm11 = self._get_server("vm11")
            if debug: print(vm11.metadata)
            assert vm11.metadata.get("mykey") == "myvalue"

            #Exception occurs
            with pytest.raises(exceptions.HttpException) as err:
                assert self._set_server_metadata("vm11", mykey="modified-value")
            assert err.match("Policy doesn't allow os_compute_api:server-metadata:create to be performed")
            assert vm11.metadata.get("mykey") == "myvalue"

        #Metadata update (delete) attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)

            #Test setup
            vm11 = self._get_server("vm11")
            if debug: print(vm11.metadata)
            assert vm11.metadata.get("mykey") == "myvalue"

            #Exception occurs
            with pytest.raises(exceptions.HttpException) as err:
                assert self._delete_server_metadata("vm11", ['mykey'])
            assert err.match("Policy doesn't allow os_compute_api:server-metadata:delete to be performed")
            assert vm11.metadata.get("mykey") == "myvalue"

        # 2.11. user11 can add/remove a security group to/from the instance

        print ("TC-2.11")

        self.set_connections_for_user(self.user11)

        #Test setup
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"
        assert vm11.status == "ACTIVE"

        assert "sg11" not in [sg.name for sg in self._list_security_groups()]
        sg11 = self._create_security_group("sg11")
        if debug: print(sg11.name)
        assert sg11.name is not None
        assert self._get_security_group("sg11") is not None
        assert "sg11" in [sg.name for sg in self._list_security_groups()]

        vm11 = self._fetch_server_security_groups("vm11")
        assert "sg11" not in [sg['name'] for sg in vm11.security_groups]

        #Add security group action succeeds for the project admin
        self._add_security_group_to_server("vm11", "sg11")
        vm11 = self._fetch_server_security_groups("vm11")
        if debug: print([sg['name'] for sg in vm11.security_groups])
        assert "sg11" in [sg['name'] for sg in vm11.security_groups]

        #Remove security group action succeeds for the project admin
        self.set_connections_for_user(self.user11)
        self._remove_security_group_from_server("vm11", "sg11")
        vm11 = self._fetch_server_security_groups("vm11")
        if debug: print([sg['name'] for sg in vm11.security_groups])
        assert "sg11" not in [sg['name'] for sg in vm11.security_groups]

        # 2.12. users 12/13 can NOT add/remove a security group to the instance

        print ("TC-2.12")

        self.set_connections_for_user(self.user11)

        #Test setup
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"
        assert vm11.status == "ACTIVE"
        self._add_security_group_to_server("vm11", "sg11")

        assert "sg12" not in [sg.name for sg in self._list_security_groups()]
        sg12 = self._create_security_group("sg12")
        if debug: print(sg12.name)
        assert sg12.name is not None
        assert self._get_security_group("sg12") is not None

        vm11 = self._fetch_server_security_groups("vm11")
        assert "sg11" in [sg['name'] for sg in vm11.security_groups]
        assert "sg12" not in [sg['name'] for sg in vm11.security_groups]

        #Add/remove security group attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)

            with pytest.raises(exceptions.HttpException) as err:
                assert self._fetch_server_security_groups("vm11")
            assert err.match("Policy doesn't allow os_compute_api:os-security-groups:list to be performed")

            with pytest.raises(exceptions.HttpException) as err:
                assert self._add_security_group_to_server("vm11", "sg12")
            assert err.match("Policy doesn't allow os_compute_api:os-security-groups:add to be performed")

            with pytest.raises(exceptions.HttpException) as err:
                assert self._remove_security_group_from_server("vm11", "sg11")
            assert err.match("Policy doesn't allow os_compute_api:os-security-groups:remove to be performed")

        self.set_connections_for_user(self.user11)
        vm11 = self._fetch_server_security_groups("vm11")
        assert "sg11" in [sg['name'] for sg in vm11.security_groups]
        assert "sg12" not in [sg['name'] for sg in vm11.security_groups]

        # 2.13. user11 can pause/unpause the instance 

        print ("TC-2.13")

        self.set_connections_for_user(self.user11)

        #Test setup
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"
        assert vm11.status == "ACTIVE"

        #Pause action succeeds for the project admin
        self._pause_server("vm11")
        vm11 = self._get_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "PAUSED"

        #Unause action succeeds for the project admin
        self._unpause_server("vm11")
        vm11 = self._get_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"

        # 2.14. users 12/13 can NOT pause/unpause the instance

        print ("TC-2.14")

        #Test setup
        self.set_connections_for_user(self.user11)
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"
        assert vm11.status == "ACTIVE"

        #Pause attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            #Exception occurs
            with pytest.raises(exceptions.HttpException) as err:
                assert self._pause_server("vm11")
            assert err.match("Policy doesn't allow os_compute_api:os-pause-server:pause to be performed")

            vm11 = self._get_server("vm11")
            if debug: print(vm11.status)
            assert vm11.status == "ACTIVE"

        # Test setup
        self.set_connections_for_user(self.user11)
        self._pause_server("vm11")
        vm11 = self._get_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "PAUSED"

        #Unause attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            #Exception occurs
            with pytest.raises(exceptions.HttpException) as err:
                assert self._unpause_server("vm11")
            assert err.match("Policy doesn't allow os_compute_api:os-pause-server:unpause to be performed")
            vm11 = self._get_server("vm11")
            if debug: print(vm11.status)
            assert vm11.status == "PAUSED"

        # Test restore
        self.set_connections_for_user(self.user11)
        self._unpause_server("vm11")
        vm11 = self._get_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"

        # 2.15 user11 can resize the instance and revert or confirm resize

        print ("TC-2.15")

        self.set_connections_for_user(self.user11)

        #Test setup
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"
        assert vm11.status == "ACTIVE"
        assert vm11.flavor['original_name'] == 'm1.tiny'

        #Resize and revert resize
        vm11 = self._resize_server("vm11", "m1.small")
        if debug: print(vm11.status)
        assert vm11.status == "VERIFY_RESIZE"
        if debug: print(vm11.flavor['original_name'])
        assert vm11.flavor['original_name'] == 'm1.small'

        vm11 = self._revert_server_resize("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"
        if debug: print(vm11.flavor['original_name'])
        assert vm11.flavor['original_name'] == 'm1.tiny'

        #Resize and confim resize
        vm11 = self._resize_server("vm11", "m1.small")
        if debug: print(vm11.status)
        assert vm11.status == "VERIFY_RESIZE"
        if debug: print(vm11.flavor['original_name'])
        assert vm11.flavor['original_name'] == 'm1.small'

        vm11 = self._confirm_server_resize("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"
        if debug: print(vm11.flavor['original_name'])
        assert vm11.flavor['original_name'] == 'm1.small'

        # 2.16. users 12/13 can NOT resize the instance

        print ("TC-2.16")

        #Test setup
        self.set_connections_for_user(self.user11)
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"
        assert vm11.status == "ACTIVE"
        assert vm11.flavor['original_name'] == 'm1.small'

        #Resize attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)

            #Exception occurs
            with pytest.raises(exceptions.HttpException) as err:
                assert self._resize_server("vm11", "m1.tiny")
            assert err.match("Policy doesn't allow os_compute_api:servers:resize to be performed")

            vm11 = self._get_server("vm11")
            if debug: print(vm11.flavor['original_name'])
            assert vm11.flavor['original_name'] == 'm1.small'

        # 2.17. user11 can lock/unlock the instance.

        print ("TC-2.17")

        self.set_connections_for_user(self.user11)

        #Test setup
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"
        assert vm11.status == "ACTIVE"
        if debug: print(vm11)

        vm11 = self._lock_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"
        if debug: print(vm11)

        vm11 = self._unlock_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"
        if debug: print(vm11)

        # 2.18. users 12/13 can NOT lock/unlock the instance.

        print ("TC-2.18")

        #Test setup
        self.set_connections_for_user(self.user11)
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"
        assert vm11.status == "ACTIVE"
        if debug: print(vm11)

        #Lock attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            #Exception occurs
            with pytest.raises(exceptions.HttpException) as err:
                assert self._lock_server("vm11")
            assert err.match("Policy doesn't allow os_compute_api:os-lock-server:lock to be performed")

            vm11 = self._get_server("vm11")
            if debug: print(vm11.status)
            assert vm11.status == "ACTIVE"
            if debug: print(vm11)

        #Test setup
        self.set_connections_for_user(self.user11)
        vm11 = self._lock_server("vm11")
        assert vm11.status == "ACTIVE"
        if debug: print(vm11)

        #Unlock attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            #Exception occurs
            with pytest.raises(exceptions.HttpException) as err:
                assert self._unlock_server("vm11")
            assert err.match("Policy doesn't allow os_compute_api:os-lock-server:unlock to be performed")

            vm11 = self._get_server("vm11")
            if debug: print(vm11.status)
            assert vm11.status == "ACTIVE"
            if debug: print(vm11)

        #Test restore
        self.set_connections_for_user(self.user11)
        vm11 = self._unlock_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"
        if debug: print(vm11)

        # 2.19. user11 can stop the instance

        print ("TC-2.19")

        self.set_connections_for_user(self.user11)

        #Test setup
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"
        assert vm11.status == "ACTIVE"

        #Stop action succeeds for the project admin
        vm11 = self._stop_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "SHUTOFF"

        #Test restore
        vm11 = self._start_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"

        # 2.20. users 12/13 can NOT stop the instance

        print ("TC-2.20")

        #Test setup
        self.set_connections_for_user(self.user11)
        vm11 = self._get_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"

        #Stop attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            #Exception occurs
            with pytest.raises(exceptions.HttpException) as err:
                assert self._stop_server("vm11")
            assert err.match("Policy doesn't allow os_compute_api:servers:stop to be performed")

            vm11 = self._get_server("vm11")
            if debug: print(vm11.status)
            assert vm11.status == "ACTIVE"

        # 2.21. user11 can soft reboot the instance

        print ("TC-2.21")

        self.set_connections_for_user(self.user11)

        #Test setup
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"
        assert vm11.status == "ACTIVE"

        #Soft reboot action succeeds for the project admin
        vm11 = self._reboot_server("vm11", 'soft')

        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"

        # 2.22. users 12/13 can NOT soft reboot the instance

        print ("TC-2.22")

        #Test setup
        self.set_connections_for_user(self.user11)
        vm11 = self._get_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"

        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)

            #Soft reboot attempt fails for project members
            with pytest.raises(exceptions.HttpException) as err:
                assert self._reboot_server("vm11", 'soft')
            assert err.match("Policy doesn't allow os_compute_api:servers:reboot to be performed")

            vm11 = self._get_server("vm11")
            if debug: print(vm11.status)
            assert vm11.status == "ACTIVE"

        # 2.23.user11 can hard reboot the instance

        print ("TC-2.23")
        self.set_connections_for_user(self.user11)

        #Hard reboot action succeeds for the project admin
        vm11 = self._reboot_server("vm11", 'hard')

        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"

        # 2.24. users 12/13 can NOT hard reboot the instance

        print ("TC-2.24")

        #Test setup
        self.set_connections_for_user(self.user11)
        vm11 = self._get_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"

        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)

            #Hard reboot attempt fails for project members
            with pytest.raises(exceptions.HttpException) as err:
                assert self._reboot_server("vm11", 'hard')
            assert err.match("Policy doesn't allow os_compute_api:servers:reboot to be performed")

            vm11 = self._get_server("vm11")
            if debug: print(vm11.status)
            assert vm11.status == "ACTIVE"

        # 2.25. user11 can rebuild the instance

        print ("TC-2.25")

        self.set_connections_for_user(self.user11)

        #Rebuild action succeeds for the project admin
        vm11 = self._rebuild_server("vm11", "vm11", self.user11.get("password"), "cirros")

        assert vm11.status == "ACTIVE"

        # 2.26. users 12/13 can NOT rebuild the instance

        print ("TC-2.26")

        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)

            #Rebuild attempt fails for project members
            with pytest.raises(exceptions.HttpException) as err:
                assert self._rebuild_server("vm11", "vm11", user.get("password"), "cirros")
            assert err.match("Policy doesn't allow os_compute_api:servers:rebuild to be performed")

            vm11 = self._get_server("vm11")
            if debug: print(vm11.status)
            assert vm11.status == "ACTIVE"

        # 2.27. user11 can shelve/unshelve the instance

        print ("TC-2.27")

        self.set_connections_for_user(self.user11)

        #Test setup
        vm11 = self._get_server("vm11")
        assert vm11.name == "vm11"
        assert vm11.status == "ACTIVE"

        #Shelve action succeeds for the project admin
        vm11 = self._shelve_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "SHELVED_OFFLOADED"

        #Test restore
        vm11 = self._unshelve_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"

        # 2.28. users 12/13 can NOT shelve the instance

        print ("TC-2.28")

        #Shelve attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            with pytest.raises(exceptions.HttpException) as err:
                assert self._shelve_server("vm11")
            assert err.match("Policy doesn't allow os_compute_api:os-shelve:shelve to be performed")

            vm11 = self._get_server("vm11")
            if debug: print(vm11.status)
            assert vm11.status == "ACTIVE"

        #Test setup
        self.set_connections_for_user(self.user11)
        vm11 = self._shelve_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "SHELVED_OFFLOADED"

        #Unshelve attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            with pytest.raises(exceptions.HttpException) as err:
                assert self._unshelve_server("vm11")
            assert err.match("Policy doesn't allow os_compute_api:os-shelve:unshelve to be performed")

            vm11 = self._get_server("vm11")
            if debug: print(vm11.status)
            assert vm11.status == "SHELVED_OFFLOADED"

        #Test restore
        self.set_connections_for_user(self.user11)
        vm11 = self._unshelve_server("vm11")
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"

        # 2.29. users 12/13 can NOT delete the instance

        print ("TC-2.29")

        #Delete attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            assert "vm11" in [s.name for s in self._list_servers()]

            with pytest.raises(exceptions.HttpException) as err:
                assert self._delete_server("vm11")
            assert err.match("Policy doesn't allow os_compute_api:servers:delete to be performed")

            assert "vm11" in [s.name for s in self._list_servers()]

        # 2.30. user11 can delete the instance

        print ("TC-2.30")

        self.set_connections_for_user(self.user11)

        #Delete action succeeds for the project admin
        self._delete_server("vm11")
        assert "vm11" not in [s.name for s in self._list_servers()]

    # TC-3
    # Description:
    # users 11/12/13 can retrieve list and detail server of project1
    def test_uc_nova_3(self, create_external_network, create_router_vr11, tc_teardown):
        """
        1. user11 can create an instance of project1
        2. users 11/12/13 can list/detail the server of project1
        """

        # 3.1. user11 can create an instance of project1

        print ("\nTC-3.1")

        #Test Setup
        extnet, extsubnet = create_external_network
        self.set_connections_for_user(self.user11)
        network11 = self._create_network("network11")
        assert network11 is not None

        subnet11 = self._create_subnet("subnet11", "network11", cidr="10.10.20.0/24", gateway_ip="10.10.20.1")
        assert subnet11 is not None
        vr11 = create_router_vr11

        #Create
        self.set_connections_for_user(self.user11)
        vm11 = self._create_server("vm-instance-11", "cirros", "m1.tiny", network_name="network11")
        if debug: print(vm11.name)
        assert vm11.name == "vm-instance-11"
        if debug: print(vm11.status)
        assert vm11.status == "ACTIVE"

        vm11 = self._get_server("vm-instance-11")
        assert vm11.name == "vm-instance-11"
        assert "vm-instance-11" in [s.name for s in self._list_servers()]

        # 3.2. users 11/12/13 can list/detail the server of project1

        print ("TC-3.2")

        for user in (self.user11, self.user12, self.user13):
            self.set_connections_for_user(user)

            #List
            assert "vm-instance-11" in [s.name for s in self._list_servers()]
            vm11 = self._get_server("vm-instance-11")
            assert vm11.name == "vm-instance-11"

            #Detail
            vm11 = self._get_server("vm-instance-11")
            if debug: print(vm11.name)
            assert vm11.name == "vm-instance-11"
