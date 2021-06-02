#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

from tests.fv_rbac import OpenStackBasicTesting
from tests.fv_rbac import debug1

class OpenStackNetworkingTesting(OpenStackBasicTesting):

    def _find_ip_availability(self, network_name_or_id, ignore_missing=True, **args):
        return self.os_sdk_conn.network.find_network_ip_availability(network_name_or_id, ignore_missing=ignore_missing, **args)

    def _get_ip_availability(self, network_name_or_id):
        network = self._find_ip_availability(network_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.get_network_ip_availability(network.id)

    def _list_ip_availabilities(self, network_name):
        return self.os_sdk_conn.network.network_ip_availabilities(network_name=network_name)

    def _create_subnetpool(self, name, prefixes, shared=False, autoclear=True):
        subnetpool = self.os_sdk_conn.network.create_subnet_pool(
                    name=name, prefixes=prefixes, shared=shared)
        if debug1: print("created subnetpool: " + subnetpool.name + " id: " + subnetpool.id)
        if autoclear:
            self.subnet_pools_clearing.append(subnetpool.id)
        return subnetpool

    def _delete_subnetpool(self, name_or_id, autoclear=True):
        subnetpool = self._find_subnetpool(name_or_id, ignore_missing=False)
        self.os_sdk_conn.network.delete_subnet_pool(subnetpool.id)
        if debug1: print("deleted subnetpool: " + subnetpool.name + " id: " + subnetpool.id)
        if autoclear:
            self.subnet_pools_clearing.remove(subnetpool.id)

    def _update_subnetpool(self, name_or_id, **args):
        subnetpool = self._find_subnetpool(name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.update_subnet_pool(subnetpool.id, **args)

    def _list_subnetpools(self):
        return self.os_sdk_conn.network.subnet_pools()

    def _find_subnetpool(self, name_or_id, ignore_missing=True, **args):
        return self.os_sdk_conn.network.find_subnet_pool(name_or_id, ignore_missing=ignore_missing, **args)

    def _get_subnetpool(self, name_or_id):
        subnetpool = self._find_subnetpool(name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.get_subnet_pool(subnetpool.id)

    def _create_addrscope(self, name, ip_version=4, shared=False, autoclear=True):
        addrscope = self.os_sdk_conn.network.create_address_scope(name=name, ip_version=ip_version, shared=shared)
        if debug1: print("created addrscope: " + addrscope.name + " id: " + addrscope.id)
        if autoclear:
            self.address_scopes_clearing.append(addrscope.id)
        return addrscope

    def _delete_addrscope(self, name_or_id, autoclear=True):
        addrscope = self._find_addrscope(name_or_id, ignore_missing=False)
        self.os_sdk_conn.network.delete_address_scope(addrscope.id)
        if debug1: print("deleted addrscope: " + addrscope.name + " id: " + addrscope.id)
        if autoclear:
            self.address_scopes_clearing.remove(addrscope.id)

    def _update_addrscope(self, name_or_id, new_name):
        addrscope = self._find_addrscope(name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.update_address_scope(addrscope.id, name=new_name)

    def _list_addrscopes(self):
        return self.os_sdk_conn.network.address_scopes()

    def _find_addrscope(self, name_or_id, ignore_missing=True, **args):
        return self.os_sdk_conn.network.find_address_scope(name_or_id, ignore_missing=ignore_missing, **args)

    def _get_addrscope(self, name_or_id):
        addrscope = self._find_addrscope(name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.get_address_scope(addrscope.id)

    def _create_portforwarding(self, fip_id, protocol, internal_ip_address, internal_port, internal_port_id, external_port):
        return self.os_sdk_conn.network.create_port_forwarding(
            floatingip_id=fip_id,
            protocol=protocol,
            internal_ip_address=internal_ip_address,
            internal_port=internal_port,
            internal_port_id=internal_port_id,
            external_port=external_port
        )

    def _delete_portforwarding(self, pf_id, fip_id):
        return self.os_sdk_conn.network.delete_port_forwarding(pf_id, fip_id)

    def _update_portforwarding(self, pf_id, fip_id, **args):
        return self.os_sdk_conn.network.update_port_forwarding(pf_id, fip_id, **args)

    def _list_portforwarding(self, fip_id):
        return self.os_sdk_conn.network.port_forwardings(fip_id)

    def _get_portforwarding(self, pf_id, fip_id):
        return self.os_sdk_conn.network.get_port_forwarding(pf_id, fip_id)

    def _create_trunk(self, name, port_name_or_id, sub_ports, autoclear=True):
        port = self._find_port(port_name_or_id, ignore_missing=False)
        trunk = self.os_sdk_conn.network.create_trunk(name=name, port_id=port.id, sub_ports=sub_ports)
        if debug1: print("created trunk: " + trunk.name + " id: " + trunk.id)
        if autoclear:
            self.trunks_clearing.append(trunk.id)
        return trunk

    def _delete_trunk(self, name_or_id, autoclear=True):
        trunk = self._find_trunk(name_or_id, ignore_missing=False)
        self.os_sdk_conn.network.delete_trunk(trunk.id)
        if debug1: print("deleted trunk: " + trunk.name + " id: " + trunk.id)
        if autoclear:
            self.trunks_clearing.remove(trunk.id)

    def _update_trunk(self, name_or_id, **args):
        trunk = self._find_trunk(name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.update_trunk(trunk, **args)

    def _list_trunks(self):
        return self.os_sdk_conn.network.trunks()

    def _find_trunk(self, name_or_id, ignore_missing=True, **args):
        return self.os_sdk_conn.network.find_trunk(name_or_id, ignore_missing=ignore_missing, **args)

    def _get_trunk(self, name_or_id):
        trunk = self._find_trunk(name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.get_trunk(trunk.id)

    def _get_trunk_subports(self, name_or_id):
        trunk = self._find_trunk(name_or_id, ignore_missing=False)
        subports = self.os_sdk_conn.network.get_trunk_subports(trunk)
        return subports.get('sub_ports')

    def _add_trunk_subport(self, trunk_name_or_id, port_name_or_id, seg_id, seg_type):
        trunk = self._find_trunk(trunk_name_or_id, ignore_missing=False)
        port = self._find_port(port_name_or_id, ignore_missing=False)
        port_list = [{
            'port_id': port.id,
            'segmentation_id': seg_id,
            'segmentation_type': seg_type
        }]
        return self.os_sdk_conn.network.add_trunk_subports(trunk.id, port_list)

    def _remove_trunk_subport(self, trunk_name_or_id, port_name_or_id):
        trunk = self._find_trunk(trunk_name_or_id, ignore_missing=False)
        port = self._find_port(port_name_or_id, ignore_missing=False)
        port_list = [{'port_id': port.id}]
        return self.os_sdk_conn.network.delete_trunk_subports(trunk.id, port_list)

    def _create_rbac_policy(self, action, network_id, target_tenant):
        return self.os_sdk_conn.network.create_rbac_policy(
                        action=action,
                        object_id=network_id,
                        object_type="network",
                        target_tenant=target_tenant)

    def _delete_rbac_policy(self, policy_id):
        return self.os_sdk_conn.network.delete_rbac_policy(policy_id)

    def _update_rbac_policy(self, policy_id, **args):
        return self.os_sdk_conn.network.update_rbac_policy(policy_id, **args)

    def _list_rbac_policies(self):
        return self.os_sdk_conn.network.rbac_policies()

    def _find_rbac_policy(self, policy_id, ignore_missing=True, **args):
        return self.os_sdk_conn.network.find_rbac_policy(policy_id, ignore_missing=ignore_missing, **args)

    def _get_rbac_policy(self, policy_id):
        return self.os_sdk_conn.network.get_rbac_policy(policy_id)

    def _create_security_group_rule(self, name_or_id, direction, protocol, ethertype, **attrs):
        sg = self._find_security_group(name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.create_security_group_rule(security_group_id=sg.id, direction=direction, protocol=protocol, ethertype=ethertype, **attrs)

    def _delete_security_group_rule(self, rule_id):
        return self.os_sdk_conn.network.delete_security_group_rule(rule_id)

    def _list_security_group_rules(self, sg_id):
        return self.os_sdk_conn.network.security_group_rules(security_group_id=sg_id)

    def _find_security_group_rule(self, name_or_id, ignore_missing=True, **args):
        return self.os_sdk_conn.network.find_security_group_rule(name_or_id, ignore_missing=ignore_missing, **args)

    def _get_security_group_rule(self, sg_id):
        return self.os_sdk_conn.network.get_security_group_rule(sg_id)
