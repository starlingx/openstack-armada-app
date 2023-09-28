#
# Copyright (c) 2019-2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import collections
import copy
import os

from oslo_log import log as logging
from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import interface
from sysinv.common import utils
from sysinv.common.storage_backend_conf import StorageBackendConfig
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack
from k8sapp_openstack.utils import get_ceph_uuid

LOG = logging.getLogger(__name__)

# Align ephemeral rbd_user with the cinder rbd_user so that the same libvirt
# secret can be used for accessing both pools. This also aligns with the
# behavior defined in nova/virt/libvirt/volume/net.py:_set_auth_config_rbd()
RBD_POOL_USER = "cinder"

DEFAULT_NOVA_PCI_ALIAS = [
    {"vendor_id": constants.NOVA_PCI_ALIAS_QAT_PF_VENDOR,
     "product_id": constants.NOVA_PCI_ALIAS_QAT_DH895XCC_PF_DEVICE,
     "name": constants.NOVA_PCI_ALIAS_QAT_DH895XCC_PF_NAME},
    {"vendor_id": constants.NOVA_PCI_ALIAS_QAT_VF_VENDOR,
     "product_id": constants.NOVA_PCI_ALIAS_QAT_DH895XCC_VF_DEVICE,
     "name": constants.NOVA_PCI_ALIAS_QAT_DH895XCC_VF_NAME},
    {"vendor_id": constants.NOVA_PCI_ALIAS_QAT_PF_VENDOR,
     "product_id": constants.NOVA_PCI_ALIAS_QAT_C62X_PF_DEVICE,
     "name": constants.NOVA_PCI_ALIAS_QAT_C62X_PF_NAME},
    {"vendor_id": constants.NOVA_PCI_ALIAS_QAT_VF_VENDOR,
     "product_id": constants.NOVA_PCI_ALIAS_QAT_C62X_VF_DEVICE,
     "name": constants.NOVA_PCI_ALIAS_QAT_C62X_VF_NAME},
    {"name": constants.NOVA_PCI_ALIAS_GPU_NAME},
    {"vendor_id": app_constants.NOVA_PCI_ALIAS_GPU_MATROX_VENDOR,
     "product_id": app_constants.NOVA_PCI_ALIAS_GPU_MATROX_G200E_DEVICE,
     "name": app_constants.NOVA_PCI_ALIAS_GPU_MATROX_G200E_NAME},
    {"vendor_id": app_constants.NOVA_PCI_ALIAS_GPU_NVIDIA_VENDOR,
     "product_id": app_constants.NOVA_PCI_ALIAS_GPU_NVIDIA_TESLA_M60_DEVICE,
     "name": app_constants.NOVA_PCI_ALIAS_GPU_NVIDIA_TESLA_M60_NAME},
    {"vendor_id": app_constants.NOVA_PCI_ALIAS_GPU_NVIDIA_VENDOR,
     "product_id": app_constants.NOVA_PCI_ALIAS_GPU_NVIDIA_TESLA_P40_DEVICE,
     "name": app_constants.NOVA_PCI_ALIAS_GPU_NVIDIA_TESLA_P40_NAME},
    {"vendor_id": app_constants.NOVA_PCI_ALIAS_GPU_NVIDIA_VENDOR,
     "product_id": app_constants.NOVA_PCI_ALIAS_GPU_NVIDIA_TESLA_T4_PF_DEVICE,
     "device_type": app_constants.NOVA_PCI_ALIAS_DEVICE_TYPE_PF,
     "name": app_constants.NOVA_PCI_ALIAS_GPU_NVIDIA_TESLA_T4_PF_NAME},
]


class NovaHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the nova chart"""

    CHART = app_constants.HELM_CHART_NOVA
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_NOVA

    # (lcavalca): 'nova' is used as ingress fqdn by nova-api-proxy
    SERVICE_FQDN = 'nova-api-internal'
    SERVICE_NAME = app_constants.HELM_CHART_NOVA
    AUTH_USERS = ['nova', ]
    SERVICE_USERS = ['neutron', 'ironic', 'placement']
    NOVNCPROXY_SERVICE_NAME = 'novncproxy'
    NOVNCPROXY_NODE_PORT = '30680'

    def __init__(self, operator):
        super(NovaHelm, self).__init__(operator)
        self.labels_by_hostid = {}
        self.cpus_by_hostid = {}
        self.interfaces_by_hostid = {}
        self.cluster_host_network = None
        self.addresses_by_hostid = {}
        self.memory_by_hostid = {}
        self.ethernet_ports_by_hostid = {}
        self.ifdatanets_by_ifaceid = {}
        self.datanets_by_netuuid = {}
        self.rbd_config = {}

    def get_overrides(self, namespace=None):
        self._rook_ceph = self._is_rook_ceph()

        self.labels_by_hostid = self._get_host_labels()
        self.cpus_by_hostid = self._get_host_cpus()
        self.interfaces_by_hostid = self._get_host_interfaces()
        self.cluster_host_network = self.dbapi.network_get_by_type(
            constants.NETWORK_TYPE_CLUSTER_HOST)
        self.addresses_by_hostid = self._get_host_addresses()
        self.memory_by_hostid = self._get_host_imemory()
        self.ethernet_ports_by_hostid = self._get_host_ethernet_ports()
        self.ifdatanets_by_ifaceid = self._get_interface_datanets()
        self.datanets_by_netuuid = self._get_datanetworks()
        self.rbd_config = self._get_storage_ceph_config()
        ssh_privatekey, ssh_publickey = \
            self._get_or_generate_ssh_keys(self.SERVICE_NAME, common.HELM_NS_OPENSTACK)

        overrides = {
            common.HELM_NS_OPENSTACK: {
                'manifests': self._get_compute_ironic_manifests(),
                'pod': {
                    'mounts': {
                        'nova_compute': {
                            'nova_compute': self._get_mount_overrides()
                        }
                    },
                    'replicas': {
                        'api_metadata': self._num_provisioned_controllers(),
                        'placement': self._num_provisioned_controllers(),
                        'osapi': self._num_provisioned_controllers(),
                        'conductor': self._num_provisioned_controllers(),
                        'consoleauth': self._num_provisioned_controllers(),
                        'scheduler': self._num_provisioned_controllers(),
                        'novncproxy': self._num_provisioned_controllers()
                    }
                },
                'conf': self._get_conf_overrides(),
                'endpoints': self._get_endpoints_overrides(),
                'network': {
                    'ssh': {
                        'enabled': 'true',
                        'private_key': ssh_privatekey,
                        'public_key': ssh_publickey,
                        'from_subnet': self._get_ssh_subnet(),
                    },
                    'novncproxy': {
                        'node_port': {
                            'enabled': self._get_network_node_port_overrides()
                        }
                    }
                },
                'ceph_client': self._get_ceph_client_overrides(),
            }
        }

        # https://bugs.launchpad.net/starlingx/+bug/1956229
        # The volume/volumeMount below are needed if we want to use the root user to ssh to the destiny host during a
        # migration operation
        overrides[common.HELM_NS_OPENSTACK]["pod"]["mounts"]["nova_compute"]["nova_compute"]["volumeMounts"].append({
            "name": "userhome",
            "mountPath": "/root",
        })
        overrides[common.HELM_NS_OPENSTACK]["pod"]["mounts"]["nova_compute"]["nova_compute"]["volumes"].append({
            "name": "userhome",
            "hostPath": {
                "path": "/var/lib/nova-user-home"
            }
        })

        if self._is_openstack_https_ready():
            overrides[common.HELM_NS_OPENSTACK] = self._update_overrides(
                overrides[common.HELM_NS_OPENSTACK],
                {'secrets': self._get_secrets_overrides()}
            )

            overrides[common.HELM_NS_OPENSTACK] = \
                self._enable_certificates(overrides[common.HELM_NS_OPENSTACK])

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides

    def _get_mount_overrides(self):
        return self._get_mount_uefi_overrides()

    def _get_compute_ironic_manifests(self):
        ironic_operator = self._operator.chart_operators[
            app_constants.HELM_CHART_IRONIC]
        openstack_app = utils.find_openstack_app(self.dbapi)
        enabled = ironic_operator._is_enabled(
            openstack_app.name,
            app_constants.HELM_CHART_IRONIC,
            common.HELM_NS_OPENSTACK
        )
        return {
            'statefulset_compute_ironic': enabled
        }

    def _get_endpoints_overrides(self):
        overrides = {
            'identity': {
                'name': 'keystone',
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS, self.SERVICE_USERS),
            },
            'compute': {
                'host_fqdn_override':
                    self._get_endpoints_host_fqdn_overrides(self.SERVICE_FQDN),

                'port': self._get_endpoints_port_api_public_overrides(),
                'scheme': self._get_endpoints_scheme_public_overrides(),
            },
            'compute_novnc_proxy': {
                'host_fqdn_override':
                    self._get_endpoints_host_fqdn_overrides(
                        self.NOVNCPROXY_SERVICE_NAME),
                'port': self._get_endpoints_port_api_public_overrides(),
                'scheme': self._get_endpoints_scheme_public_overrides(),
            },
            'oslo_cache': {
                'auth': {
                    'memcache_secret_key':
                        self._get_common_password('auth_memcache_key')
                }
            },
            'oslo_messaging': {
                'auth': self._get_endpoints_oslo_messaging_overrides(
                    self.SERVICE_NAME, [self.SERVICE_NAME])
            },
        }

        db_passwords = {'auth': self._get_endpoints_oslo_db_overrides(
            self.SERVICE_NAME, [self.SERVICE_NAME])}
        overrides.update({
            'oslo_db': db_passwords,
            'oslo_db_api': copy.deepcopy(db_passwords),
            'oslo_db_cell0': copy.deepcopy(db_passwords),
        })

        return overrides

    def _get_novncproxy_base_url(self):
        # Get the openstack endpoint public domain name
        endpoint_domain = self._get_service_parameter(
            constants.SERVICE_TYPE_OPENSTACK,
            constants.SERVICE_PARAM_SECTION_OPENSTACK_HELM,
            constants.SERVICE_PARAM_NAME_ENDPOINT_DOMAIN)
        if endpoint_domain is not None:
            location = "%s.%s" % (self.NOVNCPROXY_SERVICE_NAME,
                                  str(endpoint_domain.value).lower())
        else:
            if self._is_ipv6_cluster_service():
                location = "[%s]:%s" % (self._get_oam_address(),
                                        self.NOVNCPROXY_NODE_PORT)
            else:
                location = "%s:%s" % (self._get_oam_address(),
                                        self.NOVNCPROXY_NODE_PORT)
        url = "%s://%s/vnc_auto.html" % (self._get_public_protocol(),
                                         location)
        return url

    def _get_virt_type(self):
        if utils.is_virtual():
            return 'qemu'
        else:
            return 'kvm'

    def _update_host_cpu_maps(self, host, compute_config):
        host_cpus = self._get_host_cpu_list(host, threads=True)
        if host_cpus:
            # "Applicaton" CPUs on the platform are used for regular Openstack
            # VMs
            vm_cpus = self._get_host_cpu_list(
                host, function=constants.APPLICATION_FUNCTION, threads=True)
            vm_cpu_list = [c.cpu for c in vm_cpus]
            vm_cpu_fmt = "\"%s\"" % utils.format_range_set(vm_cpu_list)
            compute_config.update({'cpu_shared_set': vm_cpu_fmt})

            # "Application-isolated" CPUs are completely isolated from the host
            # process scheduler and are used on Openstack VMs that require
            # dedicated CPUs
            isol_cpus = self._get_host_cpu_list(
                host, function=constants.ISOLATED_FUNCTION, threads=True)
            isol_cpu_list = [c.cpu for c in isol_cpus]
            isol_cpu_fmt = "\"%s\"" % utils.format_range_set(isol_cpu_list)
            compute_config.update({'cpu_dedicated_set': isol_cpu_fmt})

    def _get_pci_pt_whitelist(self, host, iface_context):
        # Process all configured PCI passthrough interfaces and add them to
        # the list of devices to whitelist
        devices = []
        for iface in iface_context['interfaces'].values():
            if iface['ifclass'] in [constants.INTERFACE_CLASS_PCI_PASSTHROUGH]:
                port = interface.get_interface_port(iface_context, iface)
                dnames = interface._get_datanetwork_names(iface_context, iface)
                device = {
                    'address': port['pciaddr'],
                    'physical_network': dnames,
                }
                LOG.debug('_get_pci_pt_whitelist '
                          'host=%s, device=%s', host.hostname, device)
                devices.append(device)

        # Process all enabled PCI devices configured for PT and SRIOV and
        # add them to the list of devices to whitelist.
        # Since we are now properly initializing the qat driver and
        # restarting sysinv, we need to add VF devices to the regular
        # whitelist instead of the sriov whitelist
        pci_devices = self.dbapi.pci_device_get_by_host(host.id)
        for pci_device in pci_devices:
            if pci_device.enabled:
                device = {
                    'address': pci_device.pciaddr,
                }
                LOG.debug('_get_pci_pt_whitelist '
                          'host=%s, device=%s', host.hostname, device)
                devices.append(device)

        return devices

    def _get_pci_sriov_whitelist(self, host, iface_context):
        # Process all configured SRIOV interfaces and add each VF
        # to the list of devices to whitelist
        devices = []
        for iface in iface_context['interfaces'].values():
            if iface['ifclass'] in [constants.INTERFACE_CLASS_PCI_SRIOV]:
                port = interface.get_sriov_interface_port(iface_context, iface)
                dnames = interface._get_datanetwork_names(iface_context, iface)
                vf_addrs = port['sriov_vfs_pci_address'].split(",")
                vf_addrs = interface.get_sriov_interface_vf_addrs(iface_context, iface, vf_addrs)
                if vf_addrs:
                    for vf_addr in vf_addrs:
                        device = {
                            'address': vf_addr,
                            'physical_network': dnames,
                        }
                        LOG.debug('_get_pci_sriov_whitelist '
                                  'host=%s, device=%s', host.hostname, device)
                        devices.append(device)

        return devices

    def _get_pci_alias(self):
        """
        Generate multistring values containing global PCI alias
        configuration for QAT and GPU devices.

        The multistring type with list of JSON string values is used
        to generate one-line-per-entry formatting, since JSON list of
        dict is not supported by nova.
        """
        alias_config = DEFAULT_NOVA_PCI_ALIAS[:]
        LOG.debug('_get_pci_alias: aliases = %s', alias_config)
        multistring = self._oslo_multistring_override(
            name='alias', values=alias_config)
        return multistring

    def _get_port_interface_id_index(self, host):
        """
        Builds a dictionary of ports for a supplied host indexed by interface id.

        A duplicate of _get_port_interface_id_index() from config/.../sysinv/common/interface.py
        with modification to use cached data instead of querying the DB.
        """
        ports = {}
        for port in self.ethernet_ports_by_hostid.get(host.id, []):
            ports[port.interface_id] = port
        return ports

    def _get_interface_name_index(self, host):
        """
        Builds a dictionary of interfaces for a supplied host indexed by interface name.

        A duplicate of _get_interface_name_index() from config/.../sysinv/common/interface.py
        with modification to use cached data instead of querying the DB.
        """
        interfaces = {}
        for iface in self.interfaces_by_hostid.get(host.id, []):
            interfaces[iface.ifname] = iface
        return interfaces

    def _get_interface_name_datanets(self, host):
        """
        Builds a dictionary of datanets for a supplied host indexed by interface name.

        A duplicate of _get_interface_name_datanets() from config/.../sysinv/common/interface.py
        with modification to use cached data instead of querying the DB.
        """
        datanets = {}
        for iface in self.interfaces_by_hostid.get(host.id, []):

            datanetworks = []
            for ifdatanet in self.ifdatanets_by_ifaceid.get(iface.id, []):
                datanetworks.append(ifdatanet.datanetwork_uuid)

            datanetworks_list = []
            for datanetwork in datanetworks:
                dn = self.datanets_by_netuuid.get(datanetwork)
                if not dn:
                    raise exception.DataNetworkNotFound(
                        datanetwork_uuid=datanetwork)
                datanetwork_dict = \
                    {'name': dn.name,
                     'uuid': dn.uuid,
                     'network_type': dn.network_type,
                     'mtu': dn.mtu}
                if dn.network_type == constants.DATANETWORK_TYPE_VXLAN:
                    datanetwork_dict.update(
                        {'multicast_group': dn.multicast_group,
                         'port_num': dn.port_num,
                         'ttl': dn.ttl,
                         'mode': dn.mode})
                datanetworks_list.append(datanetwork_dict)
            datanets[iface.ifname] = datanetworks_list

        LOG.debug('_get_interface_name_datanets '
                  'host=%s, datanets=%s', host.hostname, datanets)

        return datanets

    def _get_address_interface_name_index(self, host):
        """
        Builds a dictionary of address lists for a supplied host indexed by interface name.

        A duplicate of _get_address_interface_name_index() from config/.../sysinv/common/interface.py
        with modification to use cached data instead of querying the DB.
        """
        addresses = collections.defaultdict(list)
        for address in self.addresses_by_hostid.get(host.id, []):
            addresses[address.ifname].append(address)
        return addresses

    def _update_host_pci_whitelist(self, host, pci_config):
        """
        Generate multistring values containing PCI passthrough
        and SR-IOV devices.

        The multistring type with list of JSON string values is used
        to generate one-line-per-entry pretty formatting.
        """
        # obtain interface information specific to this host
        iface_context = {
            'ports': self._get_port_interface_id_index(host),
            'interfaces': self._get_interface_name_index(host),
            'interfaces_datanets': self._get_interface_name_datanets(host),
            'addresses': self._get_address_interface_name_index(host)
        }

        # This host's list of PCI passthrough and SR-IOV device dictionaries
        devices = []
        devices.extend(self._get_pci_pt_whitelist(host, iface_context))
        devices.extend(self._get_pci_sriov_whitelist(host, iface_context))
        if not devices:
            return

        # Convert device list into passthrough_whitelist multistring
        multistring = self._oslo_multistring_override(
            name='passthrough_whitelist', values=devices)
        if multistring is not None:
            pci_config.update(multistring)

    def _update_host_storage(self, host, default_config, libvirt_config):
        remote_storage = False
        for label in self.labels_by_hostid.get(host.id, []):
            if (label.label_key == common.LABEL_REMOTE_STORAGE and
                    label.label_value == common.LABEL_VALUE_ENABLED):
                remote_storage = True
                break

        if remote_storage:
            libvirt_config.update({'images_type': 'rbd',
                                   'images_rbd_pool': self.rbd_config.get('rbd_pool'),
                                   'images_rbd_ceph_conf': self.rbd_config.get('rbd_ceph_conf')})
        else:
            libvirt_config.update({'images_type': 'default'})

    def _update_host_addresses(self, host, default_config, vnc_config, libvirt_config):
        cluster_host_ip = self._get_cluster_host_ip(
            host, self.addresses_by_hostid)

        default_config.update({'my_ip': cluster_host_ip})
        vnc_config.update({'server_listen': cluster_host_ip})
        vnc_config.update({'server_proxyclient_address': cluster_host_ip})
        libvirt_config.update({'live_migration_inbound_addr': cluster_host_ip})

    def _get_ssh_subnet(self):
        address_pool = self.dbapi.address_pool_get(self.cluster_host_network.pool_uuid)
        return '%s/%s' % (str(address_pool.network), str(address_pool.prefix))

    def _update_reserved_memory(self, host, default_config):
        reserved_pages = []
        reserved_host_memory = 0
        for cell in self.memory_by_hostid.get(host.id, []):
            reserved_4K_pages = 'node:%d,size:4,count:%d' % (
                                cell.numa_node,
                                cell.platform_reserved_mib * constants.NUM_4K_PER_MiB)
            reserved_pages.append(reserved_4K_pages)
            # vswitch pages will be either 2M or 1G
            reserved_vswitch_pages = 'node:%d,size:%d,count:%d' % (cell.numa_node,
                                     cell.vswitch_hugepages_size_mib * constants.Ki,
                                     cell.vswitch_hugepages_nr)
            reserved_pages.append(reserved_vswitch_pages)
            reserved_host_memory += cell.platform_reserved_mib
            reserved_host_memory += cell.vswitch_hugepages_size_mib * cell.vswitch_hugepages_nr

        multistring = self._oslo_multistring_override(
            name='reserved_huge_pages', values=reserved_pages)
        if multistring is not None:
            default_config.update(multistring)
        default_config.update({'reserved_host_memory_mb': reserved_host_memory})

    # (LP 1881672): method not currently used, but leaving it present in case we implement
    # an automatic mechanism for users to enable NUMA-aware vswitch features.
    def _get_interface_numa_nodes(self, context):
        # Process all ethernet interfaces with physical port and add each port numa_node to
        # the dict of interface_numa_nodes
        interface_numa_nodes = {}

        # Update the numa_node of this interface and its all used_by interfaces
        def update_iface_numa_node(iface, numa_node):
            if iface['ifname'] in interface_numa_nodes:
                interface_numa_nodes[iface['ifname']].add(numa_node)
            else:
                interface_numa_nodes[iface['ifname']] = set([numa_node])
            upper_ifnames = iface['used_by'] or []
            for upper_ifname in upper_ifnames:
                upper_iface = context['interfaces'][upper_ifname]
                update_iface_numa_node(upper_iface, numa_node)

        for iface in context['interfaces'].values():
            if iface['iftype'] == constants.INTERFACE_TYPE_ETHERNET:
                port = context['ports'][iface['id']]
                if port and port.numa_node >= 0:
                    update_iface_numa_node(iface, port.numa_node)

        return interface_numa_nodes

    # (LP 1881672): method not currently used, but leaving it present in case we implement
    # an automatic mechanism for users to enable NUMA-aware vswitch features.
    def _update_host_neutron_physnet(self, host, neutron_config, per_physnet_numa_config):
        '''
        Generate physnets configuration option and dynamically-generate
        configuration groups to enable nova feature numa-aware-vswitches.
        '''
        # obtain interface information specific to this host
        iface_context = {
            'ports': self._get_port_interface_id_index(host),
            'interfaces': self._get_interface_name_index(host),
            'interfaces_datanets': self._get_interface_name_datanets(host),
        }

        # find out the numa_nodes of ports which the physnet(datanetwork) is bound with
        physnet_numa_nodes = {}
        tunneled_net_numa_nodes = set()
        interface_numa_nodes = self._get_interface_numa_nodes(iface_context)
        for iface in iface_context['interfaces'].values():
            if iface['ifname'] not in interface_numa_nodes:
                continue
            # Only the physnets with valid numa_node can be insert into physnet_numa_nodes
            # or tunneled_net_numa_nodes
            if_numa_nodes = interface_numa_nodes[iface['ifname']]
            for datanet in interface.get_interface_datanets(iface_context, iface):
                if datanet['network_type'] in [constants.DATANETWORK_TYPE_FLAT,
                                                constants.DATANETWORK_TYPE_VLAN]:
                    dname = str(datanet['name'])
                    if dname in physnet_numa_nodes:
                        physnet_numa_nodes[dname] = if_numa_nodes | physnet_numa_nodes[dname]
                    else:
                        physnet_numa_nodes[dname] = if_numa_nodes
                elif datanet['network_type'] in [constants.DATANETWORK_TYPE_VXLAN]:
                    tunneled_net_numa_nodes = if_numa_nodes | tunneled_net_numa_nodes

        if physnet_numa_nodes:
            physnet_names = ','.join(physnet_numa_nodes.keys())
            neutron_config.update({'physnets': physnet_names})
            # For L2-type networks, configuration group name must be set with 'neutron_physnet_{datanet.name}'
            # For L3-type networks, configuration group name must be set with 'neutron_tunneled'
            for dname in physnet_numa_nodes.keys():
                group_name = 'neutron_physnet_' + dname
                numa_nodes = ','.join('%s' % n for n in physnet_numa_nodes[dname])
                per_physnet_numa_config.update({group_name: {'numa_nodes': numa_nodes}})
        if tunneled_net_numa_nodes:
            numa_nodes = ','.join('%s' % n for n in tunneled_net_numa_nodes)
            per_physnet_numa_config.update({'neutron_tunneled': {'numa_nodes': numa_nodes}})

    def _get_host_ethernet_ports(self):
        """
        Builds a dictionary of ethernet ports indexed by host id
        """
        ethernet_ports = {}
        db_ethernet_ports = self.dbapi.ethernet_port_get_list()
        for port in db_ethernet_ports:
            ethernet_ports.setdefault(port.host_id, []).append(port)
        return ethernet_ports

    def _get_host_imemory(self):
        """
        Builds a dictionary of memory indexed by host id
        """
        memory = {}
        db_memory = self.dbapi.imemory_get_list()
        for m in db_memory:
            memory.setdefault(m.forihostid, []).append(m)
        return memory

    def _get_host_cpus(self):
        """
        Builds a dictionary of cpus indexed by host id
        """
        cpus = {}
        db_cpus = self.dbapi.icpu_get_list()
        for cpu in db_cpus:
            cpus.setdefault(cpu.forihostid, []).append(cpu)
        return cpus

    def _get_host_cpu_list(self, host, function=None, threads=False):
        """
        Retrieve a list of CPUs for the host, filtered by function and thread
        siblings (if supplied)
        """
        cpus = []
        for c in self.cpus_by_hostid.get(host.id, []):
            if c.thread != 0 and not threads:
                continue
            if c.allocated_function == function or not function:
                cpus.append(c)
        return cpus

    def _get_storage_ceph_config(self):
        rbd_pool = app_constants.CEPH_POOL_EPHEMERAL_NAME
        rbd_ceph_conf = os.path.join(constants.CEPH_CONF_PATH,
                                     constants.SB_TYPE_CEPH_CONF_FILENAME)

        # If NOVA is a service on a ceph-external backend, use the ephemeral_pool
        # and ceph_conf file that are stored in that DB entry.
        # If NOVA is not on any ceph-external backend, it must be on the internal
        # ceph backend with default "ephemeral" pool and default "/etc/ceph/ceph.conf"
        # config file
        sb_list = self.dbapi.storage_backend_get_list_by_type(
            backend_type=constants.SB_TYPE_CEPH_EXTERNAL)
        if sb_list:
            for sb in sb_list:
                if constants.SB_SVC_NOVA in sb.services:
                    ceph_ext_obj = self.dbapi.storage_ceph_external_get(sb.id)
                    rbd_pool = sb.capabilities.get('ephemeral_pool')
                    rbd_ceph_conf = \
                        constants.CEPH_CONF_PATH + os.path.basename(ceph_ext_obj.ceph_conf)

        rbd_config = {
            'rbd_pool': rbd_pool,
            'rbd_ceph_conf': rbd_ceph_conf
        }
        return rbd_config

    def _get_datanetworks(self):
        """
        Builds a dictionary of datanetworks indexed by datanetwork uuid
        """
        datanets = {}
        db_datanets = self.dbapi.datanetworks_get_all()
        for datanet in db_datanets:
            datanets.update({datanet.uuid: datanet})
        return datanets

    def _get_per_host_overrides(self):
        host_list = []
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
                    default_config = {}
                    compute_config = {}
                    vnc_config = {}
                    libvirt_config = {}
                    pci_config = {}
                    self._update_host_cpu_maps(host, compute_config)
                    self._update_host_storage(host, default_config, libvirt_config)
                    self._update_host_addresses(host, default_config, vnc_config,
                                                libvirt_config)
                    self._update_host_pci_whitelist(host, pci_config)
                    self._update_reserved_memory(host, default_config)
                    host_nova = {
                        'name': hostname,
                        'conf': {
                            'nova': {
                                'DEFAULT': default_config,
                                'compute': compute_config if compute_config else None,
                                'vnc': vnc_config,
                                'libvirt': libvirt_config,
                                'pci': pci_config if pci_config else None,
                            }
                        }
                    }
                    host_list.append(host_nova)
        return host_list

    def get_region_name(self):
        return self._get_service_region_name(self.SERVICE_NAME)

    def _get_rook_ceph_rbd_ephemeral_storage(self):
        ephemeral_storage_conf = {}
        ephemeral_pools = []

        # Get the values for replication and min replication from the storage
        # backend attributes.
        replication = 2
        if utils.is_aio_simplex_system(self.dbapi):
            replication = 1

        # Form the dictionary with the info for the ephemeral pool.
        # If needed, multiple pools can be specified.
        ephemeral_pool = {
            'rbd_pool_name': constants.CEPH_POOL_EPHEMERAL_NAME,
            'rbd_user': RBD_POOL_USER,
            'rbd_crush_rule': "storage_tier_ruleset",
            'rbd_replication': replication,
            'rbd_chunk_size': constants.CEPH_POOL_EPHEMERAL_PG_NUM
        }
        ephemeral_pools.append(ephemeral_pool)

        ephemeral_storage_conf = {
            'type': 'rbd',
            'rbd_pools': ephemeral_pools
        }

        return ephemeral_storage_conf

    def _get_rbd_ephemeral_storage(self):
        if self._rook_ceph:
            return self._get_rook_ceph_rbd_ephemeral_storage()

        ephemeral_storage_conf = {}
        ephemeral_pools = []

        # Get the values for replication and min replication from the storage
        # backend attributes.
        replication, min_replication = \
            StorageBackendConfig.get_ceph_pool_replication(self.dbapi)

        # For now, the ephemeral pool will only be on the primary Ceph tier
        rule_name = "{0}{1}{2}".format(
            constants.SB_TIER_DEFAULT_NAMES[
                constants.SB_TIER_TYPE_CEPH],
            constants.CEPH_CRUSH_TIER_SUFFIX,
            "-ruleset").replace('-', '_')

        chunk_size = self._estimate_ceph_pool_pg_num(self.dbapi.istor_get_all())

        # Form the dictionary with the info for the ephemeral pool.
        # If needed, multiple pools can be specified.
        ephemeral_pool = {
            'rbd_pool_name': app_constants.CEPH_POOL_EPHEMERAL_NAME,
            'rbd_user': RBD_POOL_USER,
            'rbd_crush_rule': rule_name,
            'rbd_replication': replication,
            'rbd_chunk_size': min(chunk_size, app_constants.CEPH_POOL_EPHEMERAL_CHUNK_SIZE)
        }
        ephemeral_pools.append(ephemeral_pool)

        ephemeral_storage_conf = {
            'type': 'rbd',
            'rbd_pools': ephemeral_pools
        }

        return ephemeral_storage_conf

    def _get_network_node_port_overrides(self):
        # If openstack endpoint FQDN is configured, disable node_port 30680
        # which will enable the Ingress for the novncproxy service
        endpoint_fqdn = self._get_service_parameter(
            constants.SERVICE_TYPE_OPENSTACK,
            constants.SERVICE_PARAM_SECTION_OPENSTACK_HELM,
            constants.SERVICE_PARAM_NAME_ENDPOINT_DOMAIN)
        if endpoint_fqdn:
            return False
        else:
            return True

    def _get_conf_overrides(self):
        admin_keyring = 'null'
        if self._rook_ceph:
            admin_keyring = self._get_rook_ceph_admin_keyring()

        overrides = {
            'ceph': {
                'ephemeral_storage': self._get_rbd_ephemeral_storage(),
                'admin_keyring': admin_keyring,
            },
            'nova': {
                'libvirt': {
                    'virt_type': self._get_virt_type(),
                },
                'vnc': {
                    'novncproxy_base_url': self._get_novncproxy_base_url(),
                },
                'pci': self._get_pci_alias(),
            },
            'overrides': {
                'nova_compute': {
                    'hosts': self._get_per_host_overrides()
                }
            },
        }

        ceph_uuid = get_ceph_uuid()
        if ceph_uuid:
            overrides['ceph']['cinder'] = {
                'secret_uuid': ceph_uuid,
            }
            overrides['nova']['libvirt'] = {
                'rbd_secret_uuid': ceph_uuid,
            }

        if self._is_openstack_https_ready():
            overrides = self._update_overrides(overrides, {
                'nova': {
                    'keystone_authtoken': {
                        'cafile': self.get_ca_file(),
                    },
                    'cinder': {
                        'cafile': self.get_ca_file(),
                    },
                    'glance': {
                        'cafile': self.get_ca_file(),
                    },
                    'keystone': {
                        'cafile': self.get_ca_file(),
                    },
                    'neutron': {
                        'cafile': self.get_ca_file(),
                    },
                    'placement': {
                        'cafile': self.get_ca_file(),
                    },
                    'ironic': {
                        'cafile': self.get_ca_file(),
                    },
                }
            })

        return overrides

    def _get_secrets_overrides(self):
        return {
            'tls': {
                'compute_metadata': {
                    'metadata': {
                        'public': 'nova-tls-public'
                    }
                }
            }
        }
