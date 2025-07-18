#
# Copyright (c) 2019-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging
from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import utils
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack
from k8sapp_openstack.utils import get_current_vswitch_label

LOG = logging.getLogger(__name__)

DATA_NETWORK_TYPES = [constants.NETWORK_TYPE_DATA]
SRIOV_NETWORK_TYPES = [constants.NETWORK_TYPE_PCI_SRIOV]


class NeutronHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the neutron chart"""

    CHART = app_constants.HELM_CHART_NEUTRON
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_NEUTRON

    SERVICE_NAME = app_constants.HELM_CHART_NEUTRON
    AUTH_USERS = ['neutron']
    SERVICE_USERS = ['nova', 'placement', 'designate', 'ironic']

    def __init__(self, operator):
        super(NeutronHelm, self).__init__(operator)
        self.ports_by_ifaceid = {}
        self.labels_by_hostid = {}
        self.ifdatanets_by_ifaceid = {}
        self.interfaces_by_hostid = {}
        self.addresses_by_hostid = {}

    def get_vswitch_labels(self):
        vswitch_labels = get_current_vswitch_label(self.get_vswitch_label_combinations())
        if len(vswitch_labels) == 0:
            vswitch_labels = {app_constants.VSWITCH_LABEL_NONE}
        return list(vswitch_labels)

    def get_overrides(self, namespace=None):
        self.ports_by_ifaceid = self._get_interface_ports()
        self.labels_by_hostid = self._get_host_labels()
        self.ifdatanets_by_ifaceid = self._get_interface_datanets()
        self.interfaces_by_hostid = self._get_host_interfaces(
            sort_key=self._interface_sort_key)
        self.addresses_by_hostid = self._get_host_addresses()

        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': {
                    'replicas': {
                        'server': self._num_provisioned_controllers(),
                        'rpc_server': self._num_provisioned_controllers(),
                    },
                },
                'conf': self._get_conf_overrides(),
                'manifests': self._get_manifests_overrides(),
                'endpoints': self._get_endpoints_overrides(),
                'vswitch_labels': self.get_vswitch_labels()
            }
        }

        if self._is_openstack_https_ready(self.SERVICE_NAME):
            overrides[common.HELM_NS_OPENSTACK] = \
                self._enable_certificates(overrides[common.HELM_NS_OPENSTACK])

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides

    def _get_per_host_overrides(self):
        host_list = []
        config_map = []
        hosts = self.dbapi.ihost_get_list()

        for host in hosts:
            host_labels = self.labels_by_hostid.get(host.id, [])
            if (host.invprovision in [constants.PROVISIONED,
                                      constants.PROVISIONING] or
                    host.ihost_action in [constants.UNLOCK_ACTION,
                                          constants.FORCE_UNLOCK_ACTION]):
                if (constants.WORKER in utils.get_personalities(host) and
                        utils.has_openstack_compute(host_labels)):
                    hostname = str(host.hostname)
                    host_neutron = {
                        'name': hostname,
                        'conf': {
                            'plugins': {
                                'openvswitch_agent': self._get_dynamic_ovs_agent_config(host),
                                'sriov_agent': self._get_dynamic_sriov_agent_config(host),
                            }
                        }
                    }
                    # if ovs runs on host, auto bridge add is covered by sysinv
                    if (self.is_openvswitch_enabled() or self.is_openvswitch_dpdk_enabled()):
                        host_neutron['conf'].update({
                            'auto_bridge_add': self._get_host_bridges(host)})

                    # add first host to config_map
                    if not config_map:
                        config_map.append({
                            'conf': host_neutron['conf'],
                            'name': [hostname]
                        })
                    else:
                        # check if an identical configuration already exists in the config_map
                        for config in config_map:
                            if config['conf'] == host_neutron['conf']:
                                config['name'].append(hostname)
                                break
                        else:
                            # add new config to config_map
                            config_map.append({
                                'conf': host_neutron['conf'],
                                'name': [hostname]
                            })

        for config in config_map:
            host_list.append(config)

        return host_list

    def _interface_sort_key(self, iface):
        """
        Sort interfaces by interface type placing ethernet interfaces ahead of
        aggregated ethernet interfaces, and vlan interfaces last.
        """
        if iface['iftype'] == constants.INTERFACE_TYPE_ETHERNET:
            return 0, iface['ifname']
        elif iface['iftype'] == constants.INTERFACE_TYPE_AE:
            return 1, iface['ifname']
        else:  # if iface['iftype'] == constants.INTERFACE_TYPE_VLAN:
            return 2, iface['ifname']

    def _get_datapath_type(self):
        if self.is_openvswitch_dpdk_enabled():
            return "netdev"
        else:
            return "system"

    def _get_host_bridges(self, host):
        bridges = {}
        index = 0
        for iface in self.interfaces_by_hostid.get(host.id, []):
            if self._is_data_network_type(iface) or self._is_sriov_network_type(iface):
                if any(dn.datanetwork_network_type in
                       [constants.DATANETWORK_TYPE_FLAT,
                        constants.DATANETWORK_TYPE_VLAN] for dn in
                       self.ifdatanets_by_ifaceid.get(iface.id, [])):
                    # obtain the assigned bridge for interface
                    brname = 'br-phy%d' % index
                    port_name = self._get_interface_port_name(host, iface)
                    bridges[brname] = port_name.encode('utf8', 'strict')
                    index += 1
        return bridges

    def _get_dynamic_ovs_agent_config(self, host):
        local_ip = None
        tunnel_types = None
        bridge_mappings = ""
        index = 0
        for iface in self.interfaces_by_hostid.get(host.id, []):
            if self._is_data_network_type(iface) or self._is_sriov_network_type(iface):
                datanets = self.ifdatanets_by_ifaceid.get(iface.id, [])
                for datanet in datanets:
                    dn_name = datanet['datanetwork_name'].strip()
                    LOG.debug('_get_dynamic_ovs_agent_config '
                              'host=%s datanet=%s', host.hostname, dn_name)
                    if (self._is_data_network_type(iface) and
                        datanet.datanetwork_network_type ==
                            constants.DATANETWORK_TYPE_VXLAN):
                        local_ip = self._get_interface_primary_address(
                            self.context, host, iface)
                        tunnel_types = constants.DATANETWORK_TYPE_VXLAN
                    elif (datanet.datanetwork_network_type in
                          [constants.DATANETWORK_TYPE_FLAT,
                           constants.DATANETWORK_TYPE_VLAN]):
                        brname = 'br-phy%d' % index
                        bridge_mappings += ('%s:%s,' % (dn_name, brname))
                        index += 1

        agent = {}
        ovs = {
            'integration_bridge': 'br-int',
            'datapath_type': self._get_datapath_type(),
            'vhostuser_socket_dir': '/var/run/openvswitch',
        }

        if tunnel_types:
            agent['tunnel_types'] = tunnel_types
        if local_ip:
            ovs['local_ip'] = local_ip
        if bridge_mappings:
            ovs['bridge_mappings'] = str(bridge_mappings)

        # https://access.redhat.com/documentation/en-us/
        # red_hat_enterprise_linux_openstack_platform/7/html/
        # networking_guide/bridge-mappings
        # required for vlan, not flat, vxlan:
        #     ovs['network_vlan_ranges'] = physnet1:10:20,physnet2:21:25

        return {
            'agent': agent,
            'ovs': ovs,
        }

    def _get_dynamic_sriov_agent_config(self, host):
        physical_device_mappings = ""
        for iface in self.interfaces_by_hostid.get(host.id, []):
            if self._is_sriov_network_type(iface):
                # obtain the assigned datanets for interface
                datanets = self.ifdatanets_by_ifaceid.get(iface.id, [])
                port_name = self._get_interface_port_name(host, iface)
                for datanet in datanets:
                    dn_name = datanet['datanetwork_name'].strip()
                    physical_device_mappings += ('%s:%s,' % (dn_name, port_name))
        sriov_nic = {
            'physical_device_mappings': str(physical_device_mappings),
        }

        return {
            'securitygroup': {
                'firewall_driver': 'noop',
            },
            # Mitigate host OS memory leak of cgroup session-*scope files
            # and kernel slab resources. The leak is triggered using 'sudo'
            # which utilizes the host dbus-daemon. The sriov agent frequently
            # polls devices via 'ip link show' using run_as_root=True, but
            # does not actually require 'sudo'.
            'agent': {
                'root_helper': '',
            },
            'sriov_nic': sriov_nic,
        }

    def _get_ml2_physical_network_mtus(self):
        ml2_physical_network_mtus = []
        datanetworks = self.dbapi.datanetworks_get_all()
        for datanetwork in datanetworks:
            dn_str = str(datanetwork.name) + ":" + str(datanetwork.mtu)
            ml2_physical_network_mtus.append(dn_str)

        return ",".join(ml2_physical_network_mtus)

    def _get_flat_networks(self):
        flat_nets = []
        datanetworks = self.dbapi.datanetworks_get_all()
        for datanetwork in datanetworks:
            if datanetwork.network_type == constants.DATANETWORK_TYPE_FLAT:
                flat_nets.append(str(datanetwork.name))
        return ",".join(flat_nets)

    def _get_neutron_ml2_config(self):
        ml2_config = {
            'ml2': {
                'physical_network_mtus': self._get_ml2_physical_network_mtus()
            },
            'ml2_type_flat': {
                'flat_networks': self._get_flat_networks()
            }
        }
        LOG.info("_get_neutron_ml2_config=%s" % ml2_config)
        return ml2_config

    def _is_data_network_type(self, iface):
        return iface.ifclass == constants.INTERFACE_CLASS_DATA

    def _is_sriov_network_type(self, iface):
        return iface.ifclass == constants.INTERFACE_CLASS_PCI_SRIOV

    def _get_interface_ports(self):
        """
        Builds a dictionary of ports indexed by interface id
        """
        ports = {}
        db_ports = self.dbapi.port_get_list()
        for port in db_ports:
            ports.setdefault(port.interface_id, []).append(port)
        return ports

    def _get_interface_port_name(self, host, iface):
        """
        Determine the port name of the underlying device.
        """
        if (iface['iftype'] == constants.INTERFACE_TYPE_VF and iface['uses']):
            for i in self.interfaces_by_hostid.get(host.id, []):
                if i.ifname == iface['uses'][0]:
                    lower_iface = i
            if lower_iface:
                return self._get_interface_port_name(host, lower_iface)
        assert iface['iftype'] == constants.INTERFACE_TYPE_ETHERNET
        ifports = self.ports_by_ifaceid.get(iface.id, [])
        if ifports:
            return ifports[0]['name']

    def _get_interface_primary_address(self, context, host, iface):
        """
        Determine the primary IP address on an interface (if any).  If multiple
        addresses exist then the first address is returned.
        """
        for address in self.addresses_by_hostid.get(host.id, []):
            if address.ifname == iface.ifname:
                return address.address

        return None

    def _get_endpoints_overrides(self):
        overrides = {
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS, self.SERVICE_USERS),
            },
            'network': {
                'host_fqdn_override':
                    self._get_endpoints_host_fqdn_overrides(
                        self.SERVICE_NAME),
                'port': self._get_endpoints_port_api_public_overrides(),
                'scheme': self._get_endpoints_scheme_public_overrides(),
            },
            'oslo_cache': {
                'auth': {
                    'memcache_secret_key':
                        self._get_common_password('auth_memcache_key')
                }
            },
            'oslo_db': {
                'auth': self._get_endpoints_oslo_db_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS)
            },
            'oslo_messaging': {
                'auth': self._get_endpoints_oslo_messaging_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS)
            },
        }

        return overrides

    def get_region_name(self):
        return self._get_service_region_name(self.SERVICE_NAME)

    def _is_ha(self):
        """
        Determine if the system supports multiple deployments of
        agents/services based on the number of available nodes.
        """
        if utils.is_aio_simplex_system(self.dbapi):
            return False
        return True

    def _get_ha_count(self):
        """
        Determine the number of redundant deployments of
        agents/services the system supports.
        - AIO-SX supports only a single copy.
        - AIO-DX supports two redundant copies.
        - Any other deployment will be based on the number of
          available compute nodes, fixing three as the maximum
          value for redundant deployments.

        :returns: the number of supported redundant deployments
        """
        if not self._is_ha():
            return 1

        if utils.is_aio_duplex_system(self.dbapi):
            return 2

        compute_count = 0
        hosts = self.dbapi.ihost_get_list()
        for host in hosts:
            host_labels = self.labels_by_hostid.get(host.id, [])
            if (host.invprovision in [constants.PROVISIONED,
                                      constants.PROVISIONING] or
                    host.ihost_action in [constants.UNLOCK_ACTION,
                                          constants.FORCE_UNLOCK_ACTION]):
                if (constants.WORKER in utils.get_personalities(host) and
                        utils.has_openstack_compute(host_labels)):
                    compute_count += 1

        if compute_count >= 3:
            return 3
        else:
            return compute_count

    def _get_conf_overrides(self):
        host_overrides = self._get_per_host_overrides()
        overrides = {
            'neutron': {
                'DEFAULT': {
                    'dhcp_agents_per_network': self._get_ha_count(),
                }
            },
            'plugins': {
                'ml2_conf': self._get_neutron_ml2_config()
            },
            'overrides': {
                'neutron_ovs-agent': {
                    'hosts': host_overrides
                },
                'neutron_dhcp-agent': {
                    'hosts': host_overrides
                },
                'neutron_l3-agent': {
                    'hosts': host_overrides
                },
                'neutron_metadata-agent': {
                    'hosts': host_overrides
                },
                'neutron_sriov-agent': {
                    'hosts': host_overrides
                },
            },
            'paste': {
                'app:neutronversions': {
                    'paste.app_factory':
                        'neutron.pecan_wsgi.app:versions_factory'
                },
            },
        }

        if self._is_openstack_https_ready(self.SERVICE_NAME):
            overrides = self._update_overrides(overrides, {
                'neutron': {
                     'keystone_authtoken': {
                         'cafile': self.get_ca_file(),
                     },
                     'nova': {
                         'cafile': self.get_ca_file(),
                     },
                },
                'metadata_agent': {
                    'DEFAULT': {
                        'auth_ca_cert': self.get_ca_file(),
                    },
                }
            })

        return overrides

    def _get_manifests_overrides(self):
        manifests_overrides = {}
        ovs_or_ovs_dpdk_enabled = self.is_openvswitch_enabled() or self.is_openvswitch_dpdk_enabled()
        manifests_overrides.update({'daemonset_l3_agent': ovs_or_ovs_dpdk_enabled})
        return manifests_overrides
