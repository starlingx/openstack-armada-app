#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

import pytest
import netaddr

from openstack import exceptions
from tests.fv_rbac import OpenStackRouterInterface
from tests.test_neutron.rbac_neutron import OpenStackNetworkingTesting


@pytest.fixture(scope='class', autouse=True)
def networking_setup(request, network_admin_setup):

    cfg = network_admin_setup
    request.cls.os_sdk_admin_conn = cfg.os_sdk_admin_conn
    request.cls.users = cfg.users
    request.cls.user02 = cfg.user02
    request.cls.user11 = cfg.user11
    request.cls.user12 = cfg.user12
    request.cls.user13 = cfg.user13


class TestNetworking(OpenStackNetworkingTesting):
    def test_uc_network_1(self, tc_teardown):
        """
        1. user11 tries to create dedicated network 'network11', and tries to
            create shared network 'network12', should succeed;
        2. user11 tries to create external network 'extnet11', should fail;
        3. user11/12/13 tries to get list and detail of networks created in
            step 1. should succeed;
        4. user11 tries to update networks created in step1,should succeed;
        5. user12/13 tries to update/delete networks created in step1,should
            fail;
        6. user11 tries to delete networks created in step1,should succeed;
        7. user12/13 tries to create networks mentioned in step1,should fail;
        """

        print ("\nTC-1")

        self.set_connections_for_user(self.user11)

        network11 = self._create_network("network11")
        assert network11 is not None
        network12 = self._create_network("network12", shared=True)
        assert network12 is not None

        args = {'router:external': True}
        with pytest.raises(exceptions.HttpException) as err:
            assert self._create_network("extnet11", **args)
        assert err.match("HttpException: 403")

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            networks = self._list_networks()

            for name in ["network11", "network12"]:
                assert name in [n.name for n in networks]
                network = self._get_network(name)
                assert network is not None

        self.set_connections_for_user(self.user11)
        for name in ["network11", "network12"]:
            network = self._get_network(name)
            port_security_enabled = not network.is_port_security_enabled
            args = {'port_security_enabled': port_security_enabled}
            self._update_network(name, **args)
            network = self._get_network(name)
            assert network.is_port_security_enabled == port_security_enabled

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)
            for name in ["network11", "network12"]:
                network = self._get_network(name)
                port_security_enabled = not network.is_port_security_enabled

                with pytest.raises(exceptions.HttpException) as err:
                    args = {'port_security_enabled': port_security_enabled}
                    assert self._update_network(name, **args)
                assert err.match("HttpException: 403")

                network = self._get_network(name)
                assert network.is_port_security_enabled != port_security_enabled

                with pytest.raises(exceptions.HttpException) as err:
                    assert self._delete_network(name)
                assert err.match("HttpException: 403")

        self.set_connections_for_user(self.user11)
        for name in ["network11", "network12"]:
            self._delete_network(name)
            assert name not in [n.name for n in self._list_networks()]

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)

            with pytest.raises(exceptions.HttpException) as err:
                assert self._create_network("network11")
            assert err.match("HttpException: 403")

            with pytest.raises(exceptions.HttpException) as err:
                assert self._create_network("network12", shared=True)
            assert err.match("HttpException: 403")

    def test_uc_network_3(self, tc_teardown):
        """
        1. user02 create dedicated network 'network21' and shared network
            'network22', external network 'extnet21'
        2. user11/12/13 tries to get list and detail of networks, should
            succeed to get 'network22' and extnet21, should fail to get
            'network21';
        3. user11/12/13 tries to update/delete 'network22', 'extnet21', should
            fail;
        """

        print ("\nTC-3")

        self.set_connections_for_user(self.user02)

        network21 = self._create_network("network21")
        assert network21 is not None
        network22 = self._create_network("network22", shared=True)
        assert network22 is not None
        args = {'router:external': True}
        extnet21 = self._create_network("extnet21", shared=True, **args)
        assert extnet21 is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)
            for name in ["network21", "network22", "extnet21"]:
                if name == "network21":
                    assert (name not in [n.name for n in self._list_networks()])
                    assert (self._find_network(name) is None)
                else:
                    assert name in [n.name for n in self._list_networks()]
                    network = self._get_network(name)
                    assert network is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)
            for name in ["network22", "extnet21"]:
                network = self._get_network(name)
                port_security_enabled = not network.is_port_security_enabled
                with pytest.raises(exceptions.HttpException) as err:
                    args = {'port_security_enabled': port_security_enabled}
                    assert self._update_network(name, **args)
                assert err.match("HttpException: 403")

                network = self._get_network(name)
                assert network.is_port_security_enabled != port_security_enabled

                with pytest.raises(exceptions.HttpException) as err:
                    assert self._delete_network(name)
                assert err.match("HttpException: 403")

    def test_uc_subnet_1(self, tc_teardown):
        """
        1. user11 tries to create dedicated network 'network11' and subnet
            'subnet11' for it, tries to create shared network and subnet:
            'network12' and 'subnet12', should succeed;
        2. user11/12/13 tries to get list and detail of subnets: 'subnet11'
            and 'subnet12', should succeed;
        3. user11 tries to update subnets 'subnet11' and 'subnet12', should
            succeed;
        4. user12/13 tries to update/delete subnets 'subnet11' and 'subnet12',
            should fail;
        5. user11 tries to delete subnets 'subnet11' and 'subnet12',should
            succeed;
        6. user12/13 tries to create subnet 'subnet13' for network 'network21',
            should fail;
        """

        print ("\nTC-4")

        self.set_connections_for_user(self.user11)

        network11 = self._create_network("network11")
        assert network11 is not None

        subnet = self._create_subnet("subnet11", "network11",
                                     cidr="192.168.195.0/24",
                                     gateway_ip="192.168.195.1")
        assert "subnet11" in [s.name for s in self._list_subnets()]

        network12 = self._create_network("network12", shared=True)
        assert network12 is not None

        subnet = self._create_subnet("subnet12", "network12",
                                     cidr="192.168.196.0/24",
                                     gateway_ip="192.168.196.1")
        assert "subnet12" in [s.name for s in self._list_subnets()]

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)
            for name in ["subnet11", "subnet12"]:
                assert name in [s.name for s in self._list_subnets()]
                subnet = self._get_subnet(name)
                assert subnet is not None

        self.set_connections_for_user(self.user11)
        for name in ["subnet11", "subnet12"]:
            subnet = self._get_subnet(name)
            new_dhcp_enabled = not subnet.is_dhcp_enabled
            args = {'enable_dhcp': new_dhcp_enabled}
            self._update_subnet(name, **args)
            subnet = self._get_subnet(name)
            assert subnet.is_dhcp_enabled == new_dhcp_enabled

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)
            for name in ["subnet11", "subnet12"]:
                subnet = self._get_subnet(name)
                new_dhcp_enabled = not subnet.is_dhcp_enabled

                with pytest.raises(exceptions.HttpException) as err:
                    assert self._update_subnet(name, **args)
                assert err.match("HttpException: 403")

                subnet = self._get_subnet(name)
                assert subnet.is_dhcp_enabled != new_dhcp_enabled

                with pytest.raises(exceptions.HttpException) as err:
                    assert self._delete_subnet(name)
                assert err.match("HttpException: 403")

        self.set_connections_for_user(self.user11)
        for name in ["subnet11", "subnet12"]:
            self._delete_subnet(name)
            assert self._find_subnet(name) is None

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)

            with pytest.raises(exceptions.HttpException) as err:
                self._create_subnet("subnet13", "network12",
                                    cidr="192.168.197.0/24", gateway_ip="192.168.197.1")
            assert err.match("HttpException: 403")

            subnets = self._list_subnets()
            assert "subnet13" not in [s.name for s in subnets]

    def test_uc_subnet_2(self, tc_teardown):
        """
        1. user02 creates network21 and subnet21 for project2, and creates
            shared network22 and subnet22 for project2,
        2. user11/12/13 tries to get list and detail of subnets, should succeed
            to get 'subnet22,', should fail to get 'subnet21';
        3. user11/12/13 tries to update/delete subnets: subnet21 and subnet22,
            should fail
        """

        print ("\nTC-5")

        self.set_connections_for_user(self.user02)

        network = self._create_network("network21")
        assert network is not None

        subnet21 = self._create_subnet("subnet21", "network21",
                                       enable_dhcp=False,
                                       cidr="192.168.195.0/24",
                                       gateway_ip="192.168.195.1")
        subnet21 = self._get_subnet("subnet21")
        assert subnet21 is not None

        network = self._create_network("network22", shared=True)
        assert network is not None

        subnet22 = self._create_subnet("subnet22", "network22",
                                       enable_dhcp=False,
                                       cidr="192.168.196.0/24",
                                       gateway_ip="192.168.196.1")
        subnet22 = self._get_subnet("subnet22")
        assert subnet22 is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            subnets = self._list_subnets()
            assert ("subnet21" not in [s.name for s in subnets])
            assert self._find_subnet("subnet21") is None

            subnets = self._list_subnets()
            assert ("subnet22" in [s.name for s in subnets])
            subnet = self._get_subnet("subnet22")
            assert subnet is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            args = {'enable_dhcp': True}
            with pytest.raises(exceptions.ResourceNotFound):
                assert self._update_subnet(subnet21.id, **args)

            with pytest.raises(exceptions.ResourceNotFound):
                self._delete_subnet(subnet21.id)

            with pytest.raises(exceptions.HttpException) as err:
                assert self._update_subnet(subnet22.id, **args)
            assert err.match("HttpException: 403")

            with pytest.raises(exceptions.HttpException) as err:
                self._delete_subnet(subnet22.id)
            assert err.match("HttpException: 403")

    def test_uc_ip_availabilities(self, tc_teardown):
        """
        1. user02 creates network21 and subnet21 for project2, and creates
            shared 'network22' and 'subnet22' for project2,
        2. user11 create network and subnet: 'network11', 'subnet11' for
            project1.
        3. user12/13 tries to get list and detail of network-ip-availabilities
            of networks, should fail to get list and detail of
            network-ip-availabilities of network11. network 21,network22
        """

        print ("\nTC-6")

        self.set_connections_for_user(self.user02)

        network21 = self._create_network("network21")
        assert network21 is not None
        network22 = self._create_network("network22", shared=True)
        assert network22 is not None

        self._create_subnet("subnet21", "network21",
                            cidr="192.168.195.0/24",
                            gateway_ip="192.168.195.1")
        assert "subnet21" in [s.name for s in self._list_subnets()]

        self._create_subnet("subnet22", "network22",
                            cidr="192.168.196.0/24",
                            gateway_ip="192.168.196.1")
        assert "subnet22" in [s.name for s in self._list_subnets()]

        self.set_connections_for_user(self.user11)
        network = self._create_network("network11")
        assert network is not None

        self._create_subnet("subnet11", "network11",
                            cidr="192.168.195.0/24",
                            gateway_ip="192.168.195.1")
        assert "subnet11" in [s.name for s in self._list_subnets()]

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)
            for name in ["network11", "network21", "network22"]:
                ip_availabilities = self._list_ip_availabilities(name)
                assert name not in [i.network_name for i in ip_availabilities]
                assert self._find_ip_availability(name) is None

    def test_uc_subnetpool_1(self, tc_teardown):
        """
        1. user11 tries to create dedicated subnetpool 'subnetpool11', and tries
            to create shared subnetpool 'subnetpool12',should succeed;
        2. user11/12/13 tries to get list and detail of subnetpools  created in
            step 1, should succeed;
        3. user11 tries to update subnetpools created in step1.should succeed;
        4. user12/13 tries to update/delete subnetpools created in step1.should
            fail;
        5. user11 tries to delete subnetpools created in step1.should succeed;
        6. user12/13 tries to create subnetpools mentioned in step1.should fail;
        """

        print ("\nTC-7")

        self.set_connections_for_user(self.user11)

        subnetpool11 = self._create_subnetpool(
                            "subnetpool11",
                            prefixes=["192.168.0.0/16", "10.10.24.0/21"])
        assert subnetpool11 is not None

        subnetpool12 = self._create_subnetpool(
                            "subnetpool12",
                            prefixes=["192.169.0.0/16", "10.10.38.0/21"],
                            shared=True)
        assert subnetpool12 is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            for name in ["subnetpool11", "subnetpool12"]:
                subnetpools = self._list_subnetpools()
                assert name in [s.name for s in subnetpools]

                subnetpool = self._get_subnetpool(name)
                assert subnetpool is not None

        self.set_connections_for_user(self.user11)
        for name in ["subnetpool11", "subnetpool12"]:
            subnetpool = self._get_subnetpool(name)
            new_max_prefixlen = subnetpool.maximum_prefix_length - 2

            args = {'max_prefixlen': new_max_prefixlen}
            self._update_subnetpool(name, **args)

            subnetpool = self._get_subnetpool(name)
            assert subnetpool.maximum_prefix_length == new_max_prefixlen

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)
            for name in ["subnetpool11", "subnetpool12"]:
                subnetpool = self._get_subnetpool(name)
                new_max_prefixlen = subnetpool.maximum_prefix_length + 2

                args = {'max_prefixlen': new_max_prefixlen}
                with pytest.raises(exceptions.HttpException) as err:
                    assert self._update_subnetpool(name, **args)
                assert err.match("HttpException: 403")

                with pytest.raises(exceptions.HttpException) as err:
                    assert self._delete_subnetpool(name)
                assert err.match("HttpException: 403")

                assert name in [s.name for s in self._list_subnetpools()]

        self.set_connections_for_user(self.user11)
        for name in ["subnetpool11", "subnetpool12"]:
            subnetpool = self._get_subnetpool(name)
            self._delete_subnetpool(name)
            assert name not in [s.name for s in self._list_subnetpools()]

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)

            with pytest.raises(exceptions.HttpException) as err:
                assert self._create_subnetpool(
                            "subnetpool11",
                            prefixes=["192.168.0.0/16", "10.10.24.0/21"])

            with pytest.raises(exceptions.HttpException) as err:
                assert self._create_subnetpool(
                            "subnetpool12",
                            prefixes=["192.169.0.0/16", "10.10.38.0/21"],
                            shared=True)

    def test_uc_subnetpool_2(self, tc_teardown):
        """
        1. user02 create dedicated subnetpool 'subnetpool21' and shared
            subnetpool 'subnetpool22' for project2,
        2. user11/12/13 tries to get list and detail of subnetpool, should
            succeed to get 'subnetpool22' and fail to get 'subnetpool21',
        3. user11/12/13 tries to update/delete , 'subnetpool22', should fail;
        """

        print ("\nTC-8")

        self.set_connections_for_user(self.user02)

        subnetpool21 = self._create_subnetpool(
                            "subnetpool21",
                            prefixes=["192.168.0.0/16", "10.10.24.0/21"])
        assert subnetpool21 is not None

        subnetpool22 = self._create_subnetpool(
                            "subnetpool22",
                            prefixes=["192.169.0.0/16", "10.10.48.0/21"],
                            shared=True)
        assert subnetpool22 is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            subnetpools = self._list_subnetpools()
            assert "subnetpool21" not in [s.name for s in subnetpools]
            assert self._find_subnetpool("subnetpool21") is None

            subnetpools = self._list_subnetpools()
            assert "subnetpool22" in [s.name for s in subnetpools]
            subnetpool = self._get_subnetpool("subnetpool22")
            assert subnetpool is not None
            new_max_prefixlen = subnetpool.maximum_prefix_length + 2

            args = {'max_prefixlen': new_max_prefixlen}
            with pytest.raises(exceptions.HttpException) as err:
                assert self._update_subnetpool("subnetpool22", **args)
            assert err.match("HttpException: 403")

            with pytest.raises(exceptions.HttpException) as err:
                assert self._delete_subnetpool("subnetpool22")
            assert err.match("HttpException: 403")

    def test_uc_addrscope_1(self, tc_teardown):
        """
        1. user11 tries to create dedicated address-scope 'addrscope11', and
            tries to create shared subnetpool 'addrscope12', should succeed;
        2. user11/12/13 tries to get list and detail of address-scopes  created
            in step 1, should succeed;
        3. user11 tries to update address-scopes created in step1.should
            succeed;
        4. user12/13 tries to update/delete address-scopes created in
            step1.should fail;
        5. user11 tries to delete address-scopes created in step1.should
            succeed;
        6. user12/13 tries to create address-scopes mentioned in step1.should
            fail;
        """

        print ("\nTC-9")

        self.set_connections_for_user(self.user11)

        addrscope11 = self._create_addrscope("addrscope11")
        assert addrscope11 is not None

        addrscope12 = self._create_addrscope("addrscope12", shared=True)
        assert addrscope12 is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            for name in ["addrscope11", "addrscope12"]:
                addrscopes = self._list_addrscopes()
                assert name in [a.name for a in addrscopes]

                addrscope = self._get_addrscope(name)
                assert addrscope is not None

        self.set_connections_for_user(self.user11)
        for name in ["addrscope11", "addrscope12"]:
            addrscope = self._get_addrscope(name)
            new_name = name + "_new"
            self._update_addrscope(name, new_name)
            addrscope = self._get_addrscope(new_name)
            assert addrscope is not None

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)

            for name in ["addrscope11_new", "addrscope12_new"]:
                addrscope = self._get_addrscope(name)
                new_name = name + "_new"
                with pytest.raises(exceptions.HttpException) as err:
                    assert self._update_addrscope(name, new_name)
                assert err.match("HttpException: 403")

                with pytest.raises(exceptions.HttpException) as err:
                    assert self._delete_addrscope(name)
                assert err.match("HttpException: 403")

        self.set_connections_for_user(self.user11)
        for name in ["addrscope11_new", "addrscope12_new"]:
            addrscope = self._get_addrscope(name)
            self._delete_addrscope(name)
            assert name not in [a.name for a in self._list_addrscopes()]

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)
            with pytest.raises(exceptions.HttpException) as err:
                assert self._create_addrscope("addrscope11", shared=True)
            assert err.match("HttpException: 403")

            with pytest.raises(exceptions.HttpException) as err:
                assert self._create_addrscope("addrscope12", shared=True)
            assert err.match("HttpException: 403")

    def test_uc_addrscope_2(self, tc_teardown):
        """
        1. user02 create dedicated address-scope 'addrscope21' and shared
            address-scope 'addrscope22',
        2. user11/12/13 tries to get list and detail of address-scopes, should
            succeed to get 'addrscope22' and fail to get 'addrscope21',
        3. user11/12/13 tries to update/delete 'addrscope22', should fail;
        """

        print ("\nTC-10")
        
        self.set_connections_for_user(self.user02)

        addrscope21 = self._create_addrscope("addrscope21")
        assert addrscope21 is not None

        addrscope22 = self._create_addrscope("addrscope22", shared=True)
        assert addrscope22 is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            assert "addrscope21" not in [a.name for a in self._list_addrscopes()]
            assert self._find_addrscope("addrscope21") is None

            assert "addrscope22" in [s.name for s in self._list_addrscopes()]
            addresscope = self._get_addrscope("addrscope22")
            assert addresscope is not None

            with pytest.raises(exceptions.HttpException) as err:
                assert self._update_addrscope("addrscope22", "addrscope22_new")
            assert err.match("HttpException: 403")

            with pytest.raises(exceptions.HttpException) as err:
                assert self._delete_addrscope("addrscope22")
            assert err.match("HttpException: 403")

    def test_uc_router_1(self, create_external_network, tc_teardown):
        """
        1. user02 create external network and subnet: extnet21, subnet21,
        2. user11 creates network 'network11' and 'subnet11', then tries to
            create router 'vr11', then tries to add router interface for vr11
            and 'network11',should succeed;
        3. user11/12/13 tries to get list and detail of routers  created in
            step 1, should succeed;
        4. user11 tries to update routers created in step1.should succeed;
        5. user12/13 tries to update/delete routers created in step1.should
            fail;
        6. user11 tries to remove router interface and tries to delete routers
            created in step1.should succeed;
        7. user12/13 tries to create routers mentioned in step1.should fail;
        """

        print ("\nTC-11")

        extnet, extsubnet = create_external_network

        self.set_connections_for_user(self.user11)

        network11 = self._create_network("network11")
        assert network11 is not None

        subnet11 = self._create_subnet("subnet11", "network11",
                                       cidr="10.10.20.0/24", gateway_ip="10.10.20.1")
        assert subnet11 is not None

        vr11 = self._create_router("vr11", extnet.name)

        ri = OpenStackRouterInterface("vr11", "subnet11")
        vr11 = self._add_interface_to_router(ri)
        assert subnet11.id in vr11.get('subnet_ids')

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            routers = self._list_routers()
            assert "vr11" in [r.name for r in routers]
            router = self._get_router("vr11")
            assert router is not None

        self.set_connections_for_user(self.user11)

        vr = self._get_router("vr11")
        descr = "Router VR11"
        args = {'description': descr}
        router = self._update_router("vr11", **args)

        vr = self._get_router("vr11")
        assert vr.description == descr

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)

            descr = "Router VR11 " + user.get("name")
            args = {'description': descr}
            with pytest.raises(exceptions.HttpException) as err:
                assert self._update_router("vr11", **args)
            assert err.match("HttpException: 403")

            with pytest.raises(exceptions.HttpException) as err:
                assert self._delete_router("vr11")
            assert err.match("HttpException: 403")

        self.set_connections_for_user(self.user11)
        vr11 = self._delete_interface_from_router(ri)
        self._delete_router("vr11")
        assert "vr11" not in [r.name for r in self._list_routers()]

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)
            with pytest.raises(exceptions.HttpException) as err:
                assert self._create_router("vr11", extnet.name)
            assert err.match("HttpException: 403")

    def test_uc_router_2(self, create_router_vr21):
        """
        1. user02 creates external network 'extnet2', and subnet2 for
            'extnet2', then create 'vr21'
        2. user11/12/13 tries to get list or detail of router vr21.should fail;
        """

        print ("\nTC-12")

        vr21 = create_router_vr21
        assert vr21 is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            assert "vr21" not in [r.name for r in self._list_routers()]
            assert self._find_router("vr21") is None

        # No teardown is needed, the router created by create_router_vr21 fixture will be used from now on

    def test_uc_floatingip_1(self, create_router_vr21, create_external_network, create_router_vr11, tc_teardown):
        """
        1. user02 create shared external network and subnet: extnet21, subnet21
        2. user11 creates network 'network11' and 'subnet11', then create
            router 'vr11',  add router interface for vr11 and 'network11',
        3. user11 launches vm11 over 'network11',which will create a port
            connecting to 'network11',
        4. user11 tries to create floatingip for vm11's port, should succeed;
        5. user12/13 tries to update/delete floatingip created in step4. should
            fail;
        6. user11 update/delete floatingip created in step4. should succeed.
        7. user12/13 tries to create floatingip as step4. should fail;
        """

        print ("\nTC-13")

        extnet, extsubnet = create_external_network

        self.set_connections_for_user(self.user11)

        network11 = self._create_network("network11")
        assert network11 is not None

        subnet11 = self._create_subnet("subnet11", "network11", cidr="10.10.20.0/24", gateway_ip="10.10.20.1")
        assert subnet11 is not None

        vr11 = create_router_vr11

        ri = OpenStackRouterInterface("vr11", "subnet11")
        vr11 = self._add_interface_to_router(ri)
        assert subnet11.id in vr11.get("subnet_ids")

        vm11 = self._create_server("vm11", "cirros", "m1.tiny", network_name="network11")
        vm11 = self._get_server("vm11")

        network = self._get_network("network11")
        vm11_port = [p for p in self._list_ports(device_id=vm11.id)][0]
        assert vm11_port.network_id == network.id

        fip11 = self._create_floatingip(subnet_id=extsubnet.id, floating_network_id=extnet.id, port_id=vm11_port.id)
        assert fip11 is not None

        fip11 = self._get_floatingip(fip11.name)
        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)

            new_descr = "Floating IP " + user.get("name")
            with pytest.raises(exceptions.HttpException) as err:
                assert self._update_floatingip(fip11.name, description=new_descr)
            assert err.match("HttpException: 403")

            with pytest.raises(exceptions.HttpException) as err:
                assert self._delete_floatingip(fip11.name)
            assert err.match("HttpException: 403")

        self.set_connections_for_user(self.user11)

        new_descr = "Floating IP " + user.get("name")
        self._update_floatingip(fip11.name, description=new_descr)
        fip11 = self._get_floatingip(fip11.name)
        assert fip11.description == new_descr

        self._delete_floatingip(fip11.name)
        assert fip11.name not in [f.name for f in self._list_floatingips()]

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)

            with pytest.raises(exceptions.HttpException) as err:
                assert self._create_floatingip(subnet_id=extsubnet.id,
                                               floating_network_id=extnet.id,
                                               port_id=vm11_port.id)
            assert err.match("HttpException: 403")

    def test_uc_floatingip_2(self, create_external_network, create_router_vr21, tc_teardown):
        """
        1. user02 create shared external network and subnet: extnet21, subnet21
        2. user10 creates network 'network21' and 'subnet21', then create
            router 'vr21',  add router interface for vr21 and 'network21',
        3. user02 launches vm21 over 'network21',which will create a port
            connecting to 'network21',
        4. user02 create floatingip for vm21's port;
        5. user11/12/13 tries to get list and detail of floatingip in created
            in step4. should fail;
        """

        print ("\nTC-14")

        self.set_connections_for_user(self.user02)

        extnet, extsubnet = create_external_network

        network21 = self._create_network("network21")
        assert network21 is not None
        networks = self._list_networks()
        assert "network21" in [n.name for n in networks]

        vr21 = create_router_vr21

        network = self._get_network("network21")
        subnet21 = self._create_subnet("subnet21", "network21", cidr="10.10.20.0/24", gateway_ip="10.10.20.1")
        assert subnet21 is not None

        ri = OpenStackRouterInterface("vr21", "subnet21")
        vr21 = self._add_interface_to_router(ri)
        assert subnet21.id in vr21.get("subnet_ids")

        vm21 = self._create_server("vm21", "cirros", "m1.tiny", network_name="network21")
        vm21 = self._get_server("vm21")

        network = self._get_network("network21")
        vm21_port = [p for p in self._list_ports(device_id=vm21.id)][0]
        assert vm21_port.network_id == network.id

        fip21 = self._create_floatingip(subnet_id=extsubnet.id, floating_network_id=extnet.id, port_id=vm21_port.id)
        assert fip21 is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            assert fip21.id not in [fip.id for fip in self._list_floatingips()]
            assert self._find_floatingip(fip21.name) is None

    def test_uc_portforwarding_1(self, create_external_network, create_router_vr11, tc_teardown):
        """
        https://docs.starlingx.io/api-ref/stx-docs/api-ref-networking-v2-cgcs-ext.html#port-forwarding

        1. user02 create external network and subnet: extnet21, subnet21,
        2. user11 creates network 'network11' and 'subnet11', then create router
           'vr11',  add router interface for vr11 and 'network11',
        3. user11 launches vm11 over 'network11',which will create a port
           connecting to 'network11',
        4. user11 tries to create floatingip for vm11's port, should succeed;
        5. user11 tries to create portforwarding for floatingip created on
           step4, should succeed;
        6. user11 tries to update the portforwarding created in step5, should
           succeed;
        7. user12/13 tries to update/delete portforwarding created in step5,
           should fail;
        8. user11 delete portforwarding created in step5, should succeed.
        9. user12/13 tries to create portforwarding as step5, should fail;
        """

        print ("\nTC-15")

        extnet, extsubnet = create_external_network

        self.set_connections_for_user(self.user11)

        network11 = self._create_network("network11")
        assert network11 is not None

        subnet = self._create_subnet("subnet11", "network11", cidr="10.10.20.0/24", gateway_ip="10.10.20.1")
        assert subnet is not None

        vr11 = create_router_vr11

        ri = OpenStackRouterInterface("vr11", "subnet11")
        vr11 = self._add_interface_to_router(ri)
        assert subnet.id in vr11.get("subnet_ids")

        vm11 = self._create_server("vm11", "cirros", "m1.tiny", network_name="network11")
        vm11 = self._get_server("vm11")

        network = self._get_network("network11")
        vm11_port = [p for p in self._list_ports(device_id=vm11.id)][0]
        assert vm11_port.network_id == network.id

        fip11 = self._create_floatingip(subnet_id=extsubnet.id, floating_network_id=extnet.id)
        assert fip11 is not None

        vm_ip_address = None
        for ip in vm11_port.fixed_ips:
            if ip.get('subnet_id') == subnet.id:
                vm_ip_address = ip.get('ip_address')

        fip = self._get_floatingip(fip11.name)
        fip_pf = self._create_portforwarding(
                        fip.id,
                        protocol="tcp",
                        internal_ip_address=vm_ip_address,
                        internal_port=25,
                        internal_port_id=vm11_port.id,
                        external_port=2230)
        assert fip_pf is not None

        fip_pf = self._get_portforwarding(fip_pf.id, fip.id)
        new_ext_port = fip_pf.external_port + 10
        fip_pf = self._update_portforwarding(fip_pf.id, fip.id, external_port=new_ext_port)
        assert fip_pf is not None
        fip_pf = self._get_portforwarding(fip_pf.id, fip.id)
        assert fip_pf.external_port == new_ext_port

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)

            fip_pf = self._get_portforwarding(fip_pf.id, fip.id)
            new_ext_port = fip_pf.external_port + 10
            with pytest.raises(exceptions.HttpException) as err:
                assert self._update_portforwarding(fip_pf.id, fip.id, external_port=new_ext_port)
            assert err.match("HttpException: 403")

            with pytest.raises(exceptions.HttpException) as err:
                assert self._delete_portforwarding(fip_pf.id, fip.id)
            assert err.match("HttpException: 403")

        self.set_connections_for_user(self.user11)
        self._delete_portforwarding(fip_pf.id, fip.id)
        port_forwardings = self._list_portforwarding(fip.id)
        assert fip_pf.id not in [f.id for f in port_forwardings]

        # FIXME: not throwing exceptions and allowing the operation
        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)

            with pytest.raises(exceptions.HttpException) as err:
                assert self._create_portforwarding(
                            fip.id,
                            protocol="tcp",
                            internal_ip_address=vm_ip_address,
                            internal_port=25,
                            internal_port_id=vm11_port.id,
                            external_port=2230)
            assert err.match("HttpException: 403")

    def test_uc_portforwarding_2(self, create_external_network, create_router_vr21, tc_teardown):
        """
        https://docs.starlingx.io/api-ref/stx-docs/api-ref-networking-v2-cgcs-ext.html#port-forwarding

        1. user02 create external network and subnet: extnet21, subnet21,
        2. user10 creates network 'network21' and 'subnet21', then create router
           'vr21',  add router interface for vr21 and 'network21',
        3. user02 launches vm21 over 'network21',which will create a port
           connecting to 'network21',
        4. user02 creates floatingip for vm21's port, should succeed;
        5. user02 creates portforwarding for floatingip created on step4;
        6. user11/12/13 tries to get list and detail of portfowarding in created
           in step5, should fail;
        """

        print ("\nTC-16")

        extnet, extsubnet = create_external_network

        self.set_connections_for_user(self.user02)

        network21 = self._create_network("network21")
        assert network21 is not None
        networks = self._list_networks()
        assert "network21" in [n.name for n in networks]

        network = self._get_network("network21")
        subnet22 = self._create_subnet("subnet21", "network21", cidr="10.10.20.0/24", gateway_ip="10.10.20.1")
        assert subnet22 is not None

        vr21 = create_router_vr21
        subnet = self._get_subnet("subnet21")
        ri = OpenStackRouterInterface("vr21", "subnet21")
        vr21 = self._add_interface_to_router(ri)
        assert subnet.id in vr21.get("subnet_ids")

        vm21 = self._create_server("vm21", "cirros", "m1.tiny", network_name="network21")
        vm21 = self._get_server("vm21")

        network = self._get_network("network21")
        vm21_port = [p for p in self._list_ports(device_id=vm21.id)][0]
        assert vm21_port.network_id == network.id

        fip21 = self._create_floatingip(subnet_id=extsubnet.id, floating_network_id=extnet.id)
        assert fip21 is not None

        vm_ip_address = None
        for ip in vm21_port.fixed_ips:
            if ip.get('subnet_id') == subnet.id:
                vm_ip_address = ip.get('ip_address')

        fip = self._get_floatingip(fip21.name)
        fip_pf21 = self._create_portforwarding(fip.id,
                                                protocol="tcp",
                                                internal_ip_address=vm_ip_address,
                                                internal_port=25,
                                                internal_port_id=vm21_port.id,
                                                external_port=2250)
        assert fip_pf21 is not None

        fip_pf = self._get_portforwarding(fip_pf21.id, fip.id)
        new_ext_port = fip_pf.external_port + 10
        fip_pf21 = self._update_portforwarding(fip_pf.id, fip.id, external_port=new_ext_port)
        fip_pf = self._get_portforwarding(fip_pf21.id, fip.id)
        assert fip_pf.external_port == new_ext_port

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            with pytest.raises(exceptions.ResourceNotFound):
                port_forwardings = self._list_portforwarding(fip.id)
                assert fip_pf.id not in [pf.id for pf in port_forwardings]

            with pytest.raises(exceptions.ResourceNotFound):
                assert self._get_portforwarding(fip_pf.id, fip.id)

        self.set_connections_for_user(self.user02)
        self._delete_portforwarding(fip_pf.id, fip.id)
        port_forwardings = self._list_portforwarding(fip.id)
        assert fip_pf.id not in [f.id for f in port_forwardings]

    @pytest.mark.parametrize('active_user', [
        ('user11'),
        ('user12')
    ])
    def test_uc_port_1(self, create_external_network, active_user, tc_teardown):
        """
        1. user02 create shared external network and subnet: extnet21,
            extsubnetnet21;
        2. user11 create network and subnet: network11. subnet11;
        3. user11 create shared network and subnet: network12, subnet12;
        4. user11/12 tries to create port 'extport21' for extnet21. port11 for
            network11, port12 for network12, should succeed;
        5. user11/12/13 tries to get list and detail of ports, should get
            'extport21', 'port11', 'port12';
        6. user13 tries to update/delete ports: extport11. port21, port12,
            should fail;
        7. user11/12 tries to update/delete ports: extport11, port21, port12,
            should succeed;
        """

        print ("\nTC-17")

        self.set_connections_for_user(self.user02)

        extnet, extsubnet = create_external_network

        self.set_connections_for_user(self.user11)

        network11 = self._create_network("network11")
        assert network11 is not None

        subnet11 = self._create_subnet("subnet11", "network11",
                                       cidr="10.10.20.0/24", gateway_ip="10.10.20.1")
        assert subnet11 is not None

        network12 = self._create_network("network12", shared=True)
        assert network12 is not None

        subnet12 = self._create_subnet("subnet12", "network12",
                                       cidr="10.10.20.0/24", gateway_ip="10.10.20.1")
        assert subnet12 is not None

        if active_user == "user11":
            self.set_connections_for_user(self.user11)
        else:
            self.set_connections_for_user(self.user12)
        for network_name, port_name in [("extnet21", "extport21"),
                                        ("network11", "port11"),
                                        ("network12", "port12")]:

            port = self._create_port(port_name, network_name)
            assert port is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            port_names = [p.name for p in self._list_ports()]
            for port_name in ["extport21", "port11", "port12"]:
                assert port_name in port_names

                port = self._get_port(port_name)
                assert port is not None

        self.set_connections_for_user(self.user13)
        for port_name in ["extport21", "port11", "port12"]:
            new_descr = user.get("name") + " " + port_name
            with pytest.raises(exceptions.HttpException) as err:
                assert self._update_port(port_name, description=new_descr)
            assert err.match("HttpException: 403")

            with pytest.raises(exceptions.HttpException) as err:
                assert self._delete_port(port_name)
            assert err.match("HttpException: 403")

        if active_user == "user11":
            self.set_connections_for_user(self.user11)
        else:
            self.set_connections_for_user(self.user12)

        for port_name in ["extport21", "port11", "port12"]:
            new_descr = user.get("name") + " " + port_name
            self._update_port(port_name, description=new_descr)
            port = self._get_port(port_name)
            assert port.description == new_descr

            self._delete_port(port.id)
            assert port_name not in [p.name for p in self._list_ports()]

    def test_uc_port_2(self, create_external_network, tc_teardown):
        """
        1. user02 create shared external network and subnet: extnet21,
            extsubnetnet21;
        2. user02 create network and subnet: network21. subnet21;
        3. user02 create shared network and subnet: network22. subnet22;
        4. user02 create port 'extport21' for extnet21. port21 for network21,
            port22 for network22;
        5. user11/12/13 tries to get list and detail of ports, should get
            'extport21', 'port21', 'port22'; should fail;
        """

        print ("\nTC-18")

        self.set_connections_for_user(self.user02)

        extnet, extsubnet = create_external_network

        network = self._create_network("network21")
        assert network is not None

        self._create_subnet("subnet21", "network21",
                            enable_dhcp=False,
                            cidr="10.10.20.0/24",
                            gateway_ip="10.10.20.1")
        assert "subnet21" in [s.name for s in self._list_subnets()]

        network = self._create_network("network22", shared=True)
        assert network is not None

        self._create_subnet("subnet22", "network22",
                            enable_dhcp=False,
                            cidr="10.10.30.0/24",
                            gateway_ip="10.10.30.1")
        assert "subnet22" in [s.name for s in self._list_subnets()]

        for network_name, port_name in [("extnet21", "extport21"),
                                        ("network21", "port21"),
                                        ("network22", "port22")]:

            port = self._create_port(port_name, network_name)
            assert port is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            port_names = [p.name for p in self._list_ports()]
            for port_name in ["extport21", "port21", "port22"]:
                assert port_name not in port_names
                assert self._find_port(port_name) is None

    def test_uc_trunk_1(self, tc_teardown):
        """
        1. user11 creates networks and subnets: 'network11'/'subnet11',
            'network12'/'subnet12', 'network13'/'subnet13';
        2. user11 creates parent-port 'parentport11' over 'network11', creates
            subport 'subport12' over 'network12', creates subport 'subport13'
            over 'network13';
        3. user11 tries to create trunk 'trunk11' with 'parentport11' and
            'subport12', should succeed;
        4. user11 tries to set 'subport13' to 'trunk11', should succeed;
        5. user11/12/13 tries to get list and detail of trunk 'trunk11', should
            succeed;
        6. user11/12/13 tries to get list and detail of trunk subport12.
            subport13, should succeed;
        7. user12/13 tries to remove subport13 from trunk11. should fail;
        8. user11 tries to remove subport13 from trunk11. should succeed;
        9. user12/13 tries to update/delete 'trunk11', should fail;
        10. user11 tries to update/delete trunk11, should succeed;
        11. user11 tries to update/delete 'subport12', 'subport13', should
            succeed;
        """

        print ("\nTC-19")

        self.set_connections_for_user(self.user11)

        ip_addr = "10.10.20.0"
        for network_name, subnet_name in [("network11", "subnet11"),
                                          ("network12", "subnet12"),
                                          ("network13", "subnet13")]:
            network = self._create_network(network_name)
            assert network is not None
            self._create_subnet(subnet_name, network_name,
                                cidr=ip_addr+"/24",
                                gateway_ip=str(netaddr.IPAddress(ip_addr) + 1))
            assert "subnet11" in [s.name for s in self._list_subnets()]
            ip_addr = str(netaddr.IPAddress(ip_addr) + 256)

        for network_name, port_name in [("network11", "parentport11"),
                                        ("network12", "subport12"),
                                        ("network13", "subport13")]:
            port = self._create_port(port_name, network_name)
            assert port is not None

        subport12 = self._get_port('subport12')
        subport13 = self._get_port('subport13')

        trunk11 = self._create_trunk("trunk11", "parentport11",
                                     sub_ports=[{
                                         "port_id": subport12.id,
                                         "segmentation_id": 11,
                                         "segmentation_type": "vlan"
                                     }])
        assert trunk11 is not None

        trunk = self._get_trunk("trunk11")
        self._add_trunk_subport("trunk11", "subport13", 12, "vlan")
        subports = self._get_trunk_subports("trunk11")
        assert subport13.id in [s.get('port_id') for s in subports]

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            trunks = self._list_trunks()
            assert "trunk11" in [t.name for t in trunks]

            trunk = self._get_trunk("trunk11")
            assert trunk is not None

            subports = self._get_trunk_subports("trunk11")
            for subport_name in ["subport12", "subport13"]:
                subport = self._get_port(subport_name)
                assert subport is not None
                assert subport.id in [s.get('port_id') for s in subports]

        subport13 = self._get_port("subport13")
        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)
            with pytest.raises(exceptions.HttpException) as err:
                assert self._remove_trunk_subport("trunk11", "subport13")
            assert err.match("HttpException: 403")
            subports = self._get_trunk_subports("trunk11")
            assert subport13.id in [s.get('port_id') for s in subports]

        self.set_connections_for_user(self.user11)
        self._remove_trunk_subport("trunk11", "subport13")
        subports = self._get_trunk_subports("trunk11")
        assert subport13.id not in [s.get('port_id') for s in subports]

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)
            new_descr = "Trunk " + user.get("name")
            with pytest.raises(exceptions.HttpException) as err:
                assert self._update_trunk("trunk11",
                                          description=new_descr)
            assert err.match("HttpException: 403")

            with pytest.raises(exceptions.HttpException) as err:
                assert self._delete_trunk("trunk11")
            assert err.match("HttpException: 403")

        self.set_connections_for_user(self.user11)
        new_descr = "Trunk user11"
        self._update_trunk("trunk11", description=new_descr)
        trunk = self._get_trunk("trunk11")
        assert trunk.description == new_descr
        self._delete_trunk("trunk11")
        assert trunk.name not in [t.name for t in self._list_trunks()]

        self.set_connections_for_user(self.user11)
        for port_name in ["subport12", "subport13"]:
            new_descr = user.get("name") + " " + port_name
            self._update_port(port_name, description=new_descr)
            port = self._get_port(port_name)
            assert port.description == new_descr

            self._delete_port(port_name)
            assert self._find_port(port_name) is None

    def test_uc_trunk_2(self, tc_teardown):
        """
        1. user02 creates networks and subnets:
            'network21'/'subnet21','network22'/'subnet22','network23'/'subnet23';
        2. user02 creates parent-port 'parentport21' over 'network21', creates
            subport 'subport22' over 'network22', creates subport 'subport23'
            over 'network23';
        3. user02 creates trunk 'trunk21' with 'parentport21' and 'subport22';
        4. user11/12/13 tries to get list of trunk and subports creaetd in
            step2 and setp3. should fail;
        """

        print ("\nTC-20")

        self.set_connections_for_user(self.user02)

        ip_addr = "10.10.20.0"
        for network_name, subnet_name in [("network21", "subnet21"),
                                          ("network22", "subnet22"),
                                          ("network23", "subnet23")]:
            network = self._create_network(network_name)
            assert network is not None
            subnet = self._create_subnet(subnet_name, network_name,
                                         cidr=ip_addr+"/24",
                                         gateway_ip=str(netaddr.IPAddress(ip_addr) + 1))
            assert subnet is not None
            ip_addr = str(netaddr.IPAddress(ip_addr) + 256)

        for network_name, port_name in [("network21", "parentport21"),
                                        ("network22", "subport22"),
                                        ("network23", "subport23")]:
            port = self._create_port(port_name, network_name)
            assert port is not None

        subport22 = self._get_port('subport22')

        trunk21 = self._create_trunk("trunk21", "parentport21",
                                     sub_ports=[{
                                         "port_id": subport22.id,
                                         "segmentation_id": 11,
                                         "segmentation_type": "vlan"
                                     }])
        assert trunk21 is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)
            assert "trunk21" not in [t.name for t in self._list_trunks()]
            assert self._find_trunk("trunk21") is None
            with pytest.raises(exceptions.NotFoundException):
                assert not self._get_trunk_subports("trunk21")

    def test_uc_rbacpolicy_1(self, tc_teardown):
        """
        1. user11 creates network and subnet: 'network11' and 'subnet11';
        2. user11 tries to create rbac-policy with type: network, should
            succeed;
        3. user11/12/13 tries to get list and detail of rbac-poliy cretaed in
            step2. should succeed;
        4. user12/13 tries to update/delete rback-policy created in step2.
            should fail;
        5. user11 tries to update/delete rback-policy created in step2. should
            succeed;
        """

        print ("\nTC-21")

        self.set_connections_for_user(self.user11)

        network = self._create_network("network11")
        assert network is not None

        subnet = self._create_subnet("subnet11", "network11",
                                     enable_dhcp=False,
                                     cidr="192.168.195.0/24",
                                     gateway_ip="192.168.195.1")
        assert subnet is not None

        rbac_policy = self._create_rbac_policy(
                    action="access_as_shared",
                    network_id=network.id,
                    target_tenant='project1')
        assert rbac_policy is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)
            assert rbac_policy.id in [rp.id for rp in self._list_rbac_policies()]
            rp = self._get_rbac_policy(rbac_policy.id)
            assert rp is not None

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)

            with pytest.raises(exceptions.HttpException) as err:
                assert self._update_rbac_policy(rbac_policy.id,
                                                target_tenant="project2")
            assert err.match("HttpException: 403")

            with pytest.raises(exceptions.HttpException) as err:
                assert self._delete_rbac_policy(rbac_policy.id)
            assert err.match("HttpException: 403")

        self.set_connections_for_user(self.user11)
        self._update_rbac_policy(rbac_policy.id, target_tenant="project2")
        rbac_policy = self._get_rbac_policy(rbac_policy.id)
        # NOTE(myumi): target_project_id receives the target_tenant on
        # openstacksdk (why?)
        assert rbac_policy.target_project_id == "project2"
        self._delete_rbac_policy(rbac_policy.id)
        assert self._find_rbac_policy(rbac_policy.id) is None

    def test_uc_rbacpolicy_2(self, tc_teardown):
        """
        1. user02 creates network and subnet: 'network21', 'subnet21';
        2. user02 creates rbac-policy with type: network;
        3. user11/12/13 tries to get list and detail of rback created in step2.
            should fail;
        """

        print ("\nTC-22")

        self.set_connections_for_user(self.user02)

        network = self._create_network("network21")
        assert network is not None

        self._create_subnet("subnet21", "network21", enable_dhcp=False,
                            cidr="192.168.195.0/24", gateway_ip="192.168.195.1")
        assert "subnet21" in [s.name for s in self._list_subnets()]

        rbac_policy = self._create_rbac_policy(
                    action="access_as_shared",
                    network_id=network.id,
                    target_tenant='project2')
        assert rbac_policy is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)
            rbac_policies = self._list_rbac_policies()
            assert rbac_policy.id not in [rp.id for rp in rbac_policies]
            assert self._find_rbac_policy(rbac_policy.id) is None

    def test_uc_sg_1(self, tc_teardown):
        """
        1. user11 tries to create security-group 'sg11', should succeed;
        2. user11 tries to create securit-group-rule 'sgrule11' for 'sg11',
            should succeed;
        3. user11/12/13 tries to get list and detail of security-groups: sg11.
            should succeed;
        4. user11/12/13 tries to get list and detail of security-group-rule
            created in step2. should succeed;
        5. user12/13 tries to delete security-group-rule created in step2. should
            fail;
        6. user11 tries to delete security-group-rule created in step2. should
            succeed;
        7. user12/13 tries to update/delete security-group-rule in step1. should
            fail;
        8. user11 tries to update/delete security-group in step1. should succeed;
        """

        print ("\nTC-23")

        self.set_connections_for_user(self.user11)

        security_group = self._create_security_group(name="sg11")
        assert security_group is not None

        rule = self._create_security_group_rule(
                    "sg11",
                    direction="ingress",
                    protocol="icmp",
                    ethertype="IPv4")
        assert rule is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            assert self._get_security_group("sg11") is not None
            assert "sg11" in [sg.name for sg in self._list_security_groups()]

            assert self._get_security_group_rule(rule.id) is not None
            rules = self._list_security_group_rules(security_group.id)
            assert "icmp" in [r.protocol for r in rules]

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)

            with pytest.raises(exceptions.HttpException) as err:
                assert self._delete_security_group_rule(rule.id)
            err.match("HttpException: 403")

        self.set_connections_for_user(self.user11)
        self._delete_security_group_rule(rule.id)
        rules = self._list_security_group_rules(security_group.id)
        assert "icmp" not in [r.protocol for r in rules]

        for user in [self.user12, self.user13]:
            self.set_connections_for_user(user)

            new_descr = user.get("name") + "'s security group"
            with pytest.raises(exceptions.HttpException) as err:
                assert self._update_security_group("sg11", description=new_descr)
            assert err.match("HttpException: 403")

            with pytest.raises(exceptions.HttpException) as err:
                self._delete_security_group("sg11")
            assert err.match("HttpException: 403")

        self.set_connections_for_user(self.user11)
        new_descr = user.get("name") + "'s security group"
        self._update_security_group("sg11", description=new_descr)
        sg = self._get_security_group("sg11")
        assert sg.description == new_descr

        self._delete_security_group("sg11")
        assert self._find_security_group("sg11") is None

    def test_uc_sg_2(self, tc_teardown):
        """
        1. user02 tries to create security-group 'sg21', should succeed;
        2. user02 tries to create securit-group-rule 'sgrule21' for 'sg11',
            should succeed;
        3. user11/12/13 tries to get list and detail of security-groups: sg21.
            should fail;
        4. user11/12/13 tries to get list and detail of security-group-rules
            created in step2. should fail;
        """

        print ("\nTC-24")

        self.set_connections_for_user(self.user02)

        self._create_security_group(name="sg21")
        security_group = self._get_security_group("sg21")
        assert security_group is not None

        rule = self._create_security_group_rule(
                    "sg21",
                    protocol="icmp",
                    direction="ingress",
                    ethertype="IPv4")
        assert rule is not None

        for user in [self.user11, self.user12, self.user13]:
            self.set_connections_for_user(user)

            assert "sg21" not in [s.name for s in self._list_security_groups()]
            assert self._find_security_group("sg21") is None

            rules = self._list_security_group_rules(security_group.id)
            assert "icmp" not in [r.protocol for r in rules]
            with pytest.raises(exceptions.ResourceNotFound):
                assert self._get_security_group_rule(rule.id) is None
