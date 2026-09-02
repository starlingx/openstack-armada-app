#
# Copyright (c) 2020-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import eventlet
import mock
from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm import common
from sysinv.helm import helm
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

from k8sapp_openstack import utils as app_utils
from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import neutron
from k8sapp_openstack.tests import test_plugins


class NeutronHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                          base.HelmTestCaseMixin):
    def setUp(self):
        super(NeutronHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class NeutronGetOverrideTest(NeutronHelmTestCase,
                             dbbase.ControllerHostTestCase):
    def setUp(self):
        super(NeutronGetOverrideTest, self).setUp()
        self.app.dbapi = mock.MagicMock()
        self.neutron_helm = neutron.NeutronHelm(self.app.dbapi)
        self.neutron_helm.labels_by_hostid = {}

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_neutron_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NEUTRON,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {},
            'conf': {},
            'endpoints': {
                'network': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            },
        })

    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_neutron_reuses_nova_user(self, *_):
        overrides_nova = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK)
        overrides_neutron = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NEUTRON,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertEqual(
            overrides_nova["endpoints"]["identity"]["auth"]["nova"],
            overrides_neutron["endpoints"]["identity"]["auth"]["nova"],
        )

    @mock.patch('os.path.exists', return_value=True)
    @mock.patch('six.moves.builtins.open', mock.mock_open(read_data="fake"))
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=True)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm.get_ca_file',
        return_value='/etc/ssl/private/openstack/ca-cert.pem'
    )
    @mock.patch(
        'k8sapp_openstack.utils.get_openstack_certificate_values',
        return_value={
            app_constants.OPENSTACK_CERT: 'fake',
            app_constants.OPENSTACK_CERT_KEY: 'fake',
            app_constants.OPENSTACK_CERT_CA: 'fake'
        }
    )
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_neutron_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NEUTRON,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'conf': {
                'neutron': {
                    'keystone_authtoken': {
                        'cafile': neutron.NeutronHelm.get_ca_file()
                    },
                    'nova': {
                        'cafile': neutron.NeutronHelm.get_ca_file()
                    },
                },
                'metadata_agent': {
                    'DEFAULT': {
                        'auth_ca_cert': neutron.NeutronHelm.get_ca_file()
                    },
                },
            },
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': neutron.NeutronHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'neutron': {
                            'cacert': neutron.NeutronHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'nova': {
                            'cacert': neutron.NeutronHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'test': {
                            'cacert': neutron.NeutronHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                },
                'network': {
                    'host_fqdn_override': {
                        'public': {
                            # 'host': mock.ANY,
                            'tls': {
                                'ca': 'fake',
                                'crt': 'fake',
                                'key': 'fake',
                            },
                        },
                    },
                },
            },
            'manifests': {
                'certificates': True,
            },
        })

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_neutron_overrides_invalid_namespace(self, *_):
        """
        Asserts that an exception is raised if an invalid namespace
        is given when retrieving Helm override parameters.
        """
        self.assertRaises(exception.InvalidHelmNamespace,
                          self.operator.get_helm_chart_overrides,
                          app_constants.HELM_CHART_NEUTRON,
                          cnamespace=common.HELM_NS_DEFAULT)

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_neutron_overrides_missing_namespace(self, *_):
        """
        Tests that the default Helm override parameters
        are returned when no namespace is passed.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NEUTRON)
        self.assertIsInstance(overrides, dict)
        self.assertIn(common.HELM_NS_OPENSTACK, overrides)

    @mock.patch('k8sapp_openstack.utils.is_openvswitch_enabled',
                return_value=True)
    def test_get_manifests_overrides_openvswitch_enabled(self, mock_is_openvswitch_enabled):
        """
        Test for the _get_manifests_overrides function to ensure the correct
        'daemonset_l3_agent' value is returned based on the openvswitch status.
        """
        self.app.dbapi.ihost_get_list.return_value = [
            mock.MagicMock(id=1),
            mock.MagicMock(id=2)
        ]
        overrides = self.neutron_helm._get_manifests_overrides()
        self.assertEqual({'daemonset_l3_agent': True}, overrides)

    @mock.patch('k8sapp_openstack.utils.is_openvswitch_enabled',
                return_value=False)
    @mock.patch('k8sapp_openstack.utils.is_openvswitch_dpdk_enabled',
                return_value=False)
    def test_get_manifests_overrides_openvswitch_disabled(self, *_):
        """
        Test for the _get_manifests_overrides function to ensure the correct
        'daemonset_l3_agent' value is returned based on the openvswitch status.
        """
        self.app.dbapi.ihost_get_list.return_value = [
            mock.MagicMock(id=1),
            mock.MagicMock(id=2)
        ]
        overrides = self.neutron_helm._get_manifests_overrides()
        self.assertEqual({'daemonset_l3_agent': False}, overrides)


class NeutronGetPerHostOverrideTest(NeutronHelmTestCase,
                                    dbbase.ControllerHostTestCase):

    def setUp(self):
        super(NeutronGetPerHostOverrideTest, self).setUp()
        self.operator = helm.HelmOperator(self.dbapi)
        self.neutron_helm = neutron.NeutronHelm(self.operator)

    def _create_workers(self, count=1):
        for i in range(count):
            self.worker_zero = self._create_test_host(
                personality=constants.WORKER,
                administrative=constants.ADMIN_LOCKED,
                invprovision=constants.PROVISIONED,
                unit=i
            )

    @mock.patch('k8sapp_openstack.utils.is_openvswitch_enabled',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready',
                return_value=True)
    @mock.patch('sysinv.common.utils.has_openstack_compute', return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_get_per_host_overrides_single_host(self, *_):
        """
        Test _get_per_host_overrides to ensure configurations are created only
        when host configurations differ, avoiding duplicates.
        """
        self._create_workers()
        overrides = self.neutron_helm._get_per_host_overrides()
        self.assertEqual(
            ['worker-0'],
            overrides[0]['name']
        )

    @mock.patch('k8sapp_openstack.utils.is_openvswitch_enabled',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready',
                return_value=True)
    @mock.patch('sysinv.common.utils.has_openstack_compute', return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_get_per_host_overrides_two_hosts_identical_configs(self, *_):
        """
        Test _get_per_host_overrides to ensure configurations are created only
        when host configurations differ, avoiding duplicates.
        """
        self._create_workers(2)
        overrides = self.neutron_helm._get_per_host_overrides()
        self.assertEqual(
            ['worker-0', 'worker-1'],
            overrides[0]['name']
        )

    @mock.patch('k8sapp_openstack.helm.neutron.NeutronHelm._get_host_bridges',
                side_effect=lambda host: {f'br-phy-{host.hostname}': 54321})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openvswitch_enabled',
                return_value=True)
    @mock.patch('sysinv.common.utils.has_openstack_compute',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_get_per_host_overrides_two_hosts_diff_configs(self, *_):
        """
        Test _get_per_host_overrides to ensure configurations are created only
        when host configurations differ, avoiding duplicates.
        """
        self._create_workers(2)
        overrides = self.neutron_helm._get_per_host_overrides()
        self.assertEqual(
            len(overrides),
            2
        )
        self.assertEqual(
            ['worker-0'],
            overrides[0]['name']
        )
        self.assertEqual(
            ['worker-1'],
            overrides[1]['name']
        )

    @mock.patch('k8sapp_openstack.utils.is_openvswitch_enabled',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready',
                return_value=True)
    @mock.patch('sysinv.common.utils.has_openstack_compute', return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_get_per_host_overrides_three_hosts_identical_configs(self, *_):
        """
        Test _get_per_host_overrides to ensure configurations are created only
        when host configurations differ, avoiding duplicates.
        """
        self._create_workers(3)
        overrides = self.neutron_helm._get_per_host_overrides()
        self.assertEqual(
            ['worker-0', 'worker-1', 'worker-2'],
            overrides[0]['name']
        )

    @mock.patch('k8sapp_openstack.helm.neutron.NeutronHelm._get_host_bridges',
                side_effect=lambda host: {f'br-phy-{host.hostname}': 54321})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openvswitch_enabled',
                return_value=True)
    @mock.patch('sysinv.common.utils.has_openstack_compute',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_get_per_host_overrides_three_hosts_diff_configs(self, *_):
        """
        Test _get_per_host_overrides to ensure configurations are created only
        when host configurations differ, avoiding duplicates.
        """
        self._create_workers(3)
        overrides = self.neutron_helm._get_per_host_overrides()
        self.assertEqual(
            len(overrides),
            3
        )
        self.assertEqual(
            ['worker-0'],
            overrides[0]['name']
        )
        self.assertEqual(
            ['worker-1'],
            overrides[1]['name']
        )
        self.assertEqual(
            ['worker-2'],
            overrides[2]['name']
        )

    @mock.patch(
        'k8sapp_openstack.helm.neutron.NeutronHelm._get_host_bridges',
        side_effect=lambda host: {
            'br-phy-0': 54321
        } if int(host.hostname[-1]) % 2 == 0 else {
            'br-phy-1': 54321
        }
    )
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openvswitch_enabled',
                return_value=True)
    @mock.patch('sysinv.common.utils.has_openstack_compute',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_get_per_host_overrides_four_hosts_half_alike_configs(self, *_):
        """
        Test _get_per_host_overrides to ensure configurations are created only
        when host configurations differ, avoiding duplicates.
        """
        self._create_workers(4)
        overrides = self.neutron_helm._get_per_host_overrides()
        self.assertEqual(
            len(overrides),
            2
        )
        self.assertEqual(
            ['worker-0', 'worker-2'],
            overrides[0]['name']
        )
        self.assertEqual(
            ['worker-1', 'worker-3'],
            overrides[1]['name']
        )


class NeutronMl2ConfigTest(NeutronHelmTestCase,
                           dbbase.ControllerHostTestCase):

    def setUp(self):
        super(NeutronMl2ConfigTest, self).setUp()
        self.operator = helm.HelmOperator(self.dbapi)
        self.neutron_helm = neutron.NeutronHelm(self.operator)

    def _create_datanetwork(self, name, network_type):
        return dbutils.create_test_datanetwork(name=name,
                                               network_type=network_type,
                                               mtu=1500)

    def test_get_vlan_networks(self):
        """
        Test _get_vlan_networks to ensure VLAN data networks are registered
        and the other types are left out. The base fixture already provides
        data0 and data1, both VLAN.
        """
        self._create_datanetwork('dn-flat', constants.DATANETWORK_TYPE_FLAT)
        self._create_datanetwork('dn-vlan', constants.DATANETWORK_TYPE_VLAN)

        self.assertEqual(
            'data0,data1,dn-vlan',
            self.neutron_helm._get_vlan_networks()
        )

    def test_get_vlan_networks_without_vlan_datanetworks(self):
        """
        Test _get_vlan_networks to ensure an empty value is returned when no
        VLAN data network is provisioned.
        """
        for datanetwork in self.datanetworks:
            self.dbapi.datanetwork_destroy(datanetwork.uuid)
        self._create_datanetwork('dn-flat', constants.DATANETWORK_TYPE_FLAT)

        self.assertEqual(
            '',
            self.neutron_helm._get_vlan_networks()
        )

    def test_get_neutron_ml2_config_vlan_ranges(self):
        """
        Test _get_neutron_ml2_config to ensure the VLAN data networks reach
        ml2_type_vlan.network_vlan_ranges.
        """
        ml2_config = self.neutron_helm._get_neutron_ml2_config()

        self.assertEqual(
            'data0,data1',
            ml2_config['ml2_type_vlan']['network_vlan_ranges']
        )


class NeutronBridgeTestCase(NeutronHelmTestCase, dbbase.ControllerHostTestCase):
    """Coverage for the OVS bridge naming of the Neutron overrides.

    Both 'bridge_mappings' (openvswitch_agent config) and 'auto_bridge_add'
    are exercised, for the same topology, in both vswitch modes.

    The tests are organized in four groups, and which assertions share a test
    method is itself deliberate:

    1. 'test_openvswitch_*' assert bridge_mappings and auto_bridge_add
       together, because with OVS-kernel both are expected to be untouched by
       this change.

    2. 'test_dpdk_bridge_mappings_unchanged_*' assert ONLY bridge_mappings, for
       the configurations OVS-DPDK already supports.  Their mapping must be
       exactly the same before and after this change, and keeping the
       auto_bridge_add assertion out of them is what makes that provable: with
       both in the same method, the auto_bridge_add mismatch would fail the test
       and hide the fact that the mapping did not change.

    3. 'test_dpdk_bridge_mappings_aligned_*' assert the mappings that DO change,
       for the configurations where the application used to name a bridge the
       platform never creates.

    4. 'test_dpdk_auto_bridge_add_*' assert the change that is deliberate: with
       OVS-DPDK the application asks the agent for no bridge at all.

    Two choices about fidelity:

    - The topology is created in the test database, so that the plugin reads
      it through its own queries instead of having it injected.

    - The vswitch mode is induced through the host labels, letting the whole
      get_current_vswitch_label() chain run.  Mocking is_openvswitch_enabled()
      or is_openvswitch_dpdk_enabled() directly would produce a state that
      cannot exist on any host: both compare the *whole* vswitch label set by
      equality, so they are mutually exclusive by construction.
    """

    def setUp(self):
        super(NeutronBridgeTestCase, self).setUp()
        self.operator = helm.HelmOperator(self.dbapi)
        self.neutron_helm = neutron.NeutronHelm(self.operator)
        # The production entry points of HelmOperator are decorated with
        # @helm_context, which initializes the per-thread cache the plugin
        # reads through self.context.  These tests call the internal override
        # generation directly, so the cache is initialized the same way.
        setattr(eventlet.greenthread.getcurrent(), '_helm_context', dict())
        self.worker = self._create_test_host(
            personality=constants.WORKER,
            administrative=constants.ADMIN_LOCKED,
            invprovision=constants.PROVISIONED,
            unit=0)
        self.port_index = 0

    # ------------------------------------------------------------------
    # topology helpers
    # ------------------------------------------------------------------
    def _add_label(self, label):
        """Add a 'key=value' label to the worker host."""
        key, value = label.split('=')
        dbutils.create_test_label(host_id=self.worker.id,
                                  label_key=key,
                                  label_value=value)

    def _set_vswitch_mode(self, dpdk=False):
        """Make the worker an openstack compute node with a vswitch mode."""
        self._add_label('%s=%s' % (common.LABEL_COMPUTE_LABEL,
                                   common.LABEL_VALUE_ENABLED))
        self._add_label(app_constants.OPENVSWITCH_LABEL)
        if dpdk:
            self._add_label(app_constants.DPDK_LABEL)

    def _add_interface(self, ifname, ifclass, iftype, datanets=(),
                       uses=(), vlan_id=None, with_port=True):
        """Create an interface with its port and data network assignments.

        datanets is a sequence of (name, network_type) tuples.
        """
        interface = dbutils.create_test_interface(
            ifname=ifname,
            ifclass=ifclass,
            iftype=iftype,
            vlan_id=vlan_id,
            uses=list(uses),
            forihostid=self.worker.id,
            ihost_uuid=self.worker.uuid)
        if with_port:
            dbutils.create_test_ethernet_port(
                name='eth%s' % self.port_index,
                host_id=self.worker.id,
                interface_id=interface.id,
                pciaddr='0000:00:00.%s' % self.port_index,
                dev_id=1)
            self.port_index += 1
        for name, network_type in datanets:
            datanetwork = dbutils.create_test_datanetwork(
                name=name, network_type=network_type)
            dbutils.create_test_interface_datanetwork(
                interface_id=interface.id, datanetwork_id=datanetwork.id)
        return interface

    # ------------------------------------------------------------------
    # override generation
    # ------------------------------------------------------------------
    def _get_host_config(self):
        """Generate the per-host overrides and return the worker's config.

        Reproduces the cache priming that get_overrides() does before calling
        _get_per_host_overrides(), without the unrelated parts of the full
        override generation.
        """
        helm_obj = self.neutron_helm
        helm_obj.ports_by_ifaceid = helm_obj._get_interface_ports()
        helm_obj.labels_by_hostid = helm_obj._get_host_labels()
        helm_obj.ifdatanets_by_ifaceid = helm_obj._get_interface_datanets()
        helm_obj.interfaces_by_hostid = helm_obj._get_host_interfaces(
            sort_key=helm_obj._interface_sort_key)
        helm_obj.addresses_by_hostid = helm_obj._get_host_addresses()

        overrides = helm_obj._get_per_host_overrides()
        self.assertEqual(1, len(overrides),
                         "expected overrides for a single host")
        return overrides[0]['conf']

    def _get_bridge_mappings(self, conf):
        ovs = conf['plugins']['openvswitch_agent']['ovs']
        return ovs.get('bridge_mappings')

    def _get_bridge_mappings_as_dict(self, conf):
        """Parse 'physnet:bridge,...' into a dict, ignoring the entry order."""
        mappings = self._get_bridge_mappings(conf)
        if not mappings:
            return {}
        return dict(entry.split(':')
                    for entry in mappings.rstrip(',').split(','))

    def _get_auto_bridge_add(self, conf):
        # values are bytes (kept from the pre-existing implementation), so
        # decode for readable assertions
        table = conf.get('auto_bridge_add')
        if table is None:
            return None
        return {k: v.decode('utf8') if isinstance(v, bytes) else v
                for k, v in table.items()}

    def _add_bond(self, ifname='bond0', ifclass=constants.INTERFACE_CLASS_DATA,
                  datanets=()):
        """Create an AE interface over two ethernet members."""
        members = []
        for index in (0, 1):
            member = self._add_interface('%s-member%s' % (ifname, index),
                                         None,
                                         constants.INTERFACE_TYPE_ETHERNET)
            members.append(member.ifname)
        return self._add_interface(ifname, ifclass,
                                   constants.INTERFACE_TYPE_AE,
                                   datanets=datanets, uses=members,
                                   with_port=False)

    # ------------------------------------------------------------------
    # topology builders, shared by the bridge_mappings and the
    # auto_bridge_add tests of the same scenario
    # ------------------------------------------------------------------
    def _topology_ethernet_vlan(self):
        """One ethernet data interface with a vlan data network.

        The most common deployment configuration.
        """
        self._add_interface('data0', constants.INTERFACE_CLASS_DATA,
                            constants.INTERFACE_TYPE_ETHERNET,
                            datanets=[('physnet0',
                                       constants.DATANETWORK_TYPE_VLAN)])

    def _topology_ethernet_flat(self):
        """One ethernet data interface with a flat data network."""
        self._add_interface('data0', constants.INTERFACE_CLASS_DATA,
                            constants.INTERFACE_TYPE_ETHERNET,
                            datanets=[('physnet0',
                                       constants.DATANETWORK_TYPE_FLAT)])

    def _topology_bond_vlan(self):
        """One AE data interface with a vlan data network.

        The topology used to validate the OVS-kernel support in 26.03, and the
        one this change adds support for with OVS-DPDK.
        """
        self._add_bond(datanets=[('physnet0',
                                  constants.DATANETWORK_TYPE_VLAN)])

    def _topology_bond_and_ethernet(self):
        """An AE data interface alongside an ethernet data interface."""
        self._add_interface('data0', constants.INTERFACE_CLASS_DATA,
                            constants.INTERFACE_TYPE_ETHERNET,
                            datanets=[('physnet0',
                                       constants.DATANETWORK_TYPE_VLAN)])
        self._add_bond(datanets=[('physnet1',
                                  constants.DATANETWORK_TYPE_VLAN)])

    def _topology_vlan_over_bond(self):
        """A vlan data interface on top of an AE interface."""
        self._add_bond(ifclass=None)
        self._add_interface('vlan100', constants.INTERFACE_CLASS_DATA,
                            constants.INTERFACE_TYPE_VLAN,
                            datanets=[('physnet0',
                                       constants.DATANETWORK_TYPE_FLAT)],
                            uses=['bond0'], vlan_id=100, with_port=False)

    def _topology_two_datanets(self):
        """One data interface carrying two data networks."""
        self._add_interface('data0', constants.INTERFACE_CLASS_DATA,
                            constants.INTERFACE_TYPE_ETHERNET,
                            datanets=[('physnet0',
                                       constants.DATANETWORK_TYPE_VLAN),
                                      ('physnet1',
                                       constants.DATANETWORK_TYPE_VLAN)])

    def _topology_bond_and_vxlan_only(self):
        """An AE data interface alongside a data interface with only vxlan.

        The vxlan one is never mapped by the agent, but the platform still
        creates a bridge for it and therefore consumes a bridge index.
        """
        self._add_interface('data0', constants.INTERFACE_CLASS_DATA,
                            constants.INTERFACE_TYPE_ETHERNET,
                            datanets=[('physnet0',
                                       constants.DATANETWORK_TYPE_VXLAN)])
        self._add_bond(datanets=[('physnet1',
                                  constants.DATANETWORK_TYPE_FLAT)])

    def _topology_bond_and_sriov(self):
        """An AE data interface coexisting with an SR-IOV interface."""
        self._add_bond(datanets=[('physnet0',
                                  constants.DATANETWORK_TYPE_VLAN)])
        self._add_interface('sriov0', constants.INTERFACE_CLASS_PCI_SRIOV,
                            constants.INTERFACE_TYPE_ETHERNET,
                            datanets=[('physnet1',
                                       constants.DATANETWORK_TYPE_VLAN)])

    def _topology_sriov_only(self):
        """An SR-IOV interface with no data interface on the host."""
        self._add_interface('sriov0', constants.INTERFACE_CLASS_PCI_SRIOV,
                            constants.INTERFACE_TYPE_ETHERNET,
                            datanets=[('physnet0',
                                       constants.DATANETWORK_TYPE_VLAN)])

    # ==================================================================
    # OVS-kernel: nothing changes.  bridge_mappings and auto_bridge_add are
    # asserted together because both are expected to be untouched, so there is
    # no risk of one masking the other.
    # ==================================================================
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_openvswitch_ethernet_vlan(self, *_):
        self._set_vswitch_mode()
        self._topology_ethernet_vlan()

        conf = self._get_host_config()

        # the raw string is asserted once, to pin the format
        self.assertEqual('physnet0:br-phy0,',
                         self._get_bridge_mappings(conf))
        self.assertEqual({'br-phy0': 'eth0'},
                         self._get_auto_bridge_add(conf))
        self.assertEqual(
            'system',
            conf['plugins']['openvswitch_agent']['ovs']['datapath_type'])

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_openvswitch_ethernet_flat(self, *_):
        self._set_vswitch_mode()
        self._topology_ethernet_flat()

        conf = self._get_host_config()

        self.assertEqual({'physnet0': 'br-phy0'},
                         self._get_bridge_mappings_as_dict(conf))
        self.assertEqual({'br-phy0': 'eth0'},
                         self._get_auto_bridge_add(conf))
        # unlike a vlan data network, a flat one is also advertised to ml2
        self.assertEqual('physnet0', self.neutron_helm._get_flat_networks())

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_openvswitch_bond_vlan(self, *_):
        self._set_vswitch_mode()
        self._topology_bond_vlan()

        conf = self._get_host_config()

        self.assertEqual({'physnet0': 'br-phy0'},
                         self._get_bridge_mappings_as_dict(conf))
        # with OVS-kernel the AE is a Linux bond, so the agent attaches it
        self.assertEqual({'br-phy0': 'bond0'},
                         self._get_auto_bridge_add(conf))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_openvswitch_bond_and_ethernet(self, *_):
        self._set_vswitch_mode()
        self._topology_bond_and_ethernet()

        conf = self._get_host_config()

        self.assertEqual({'physnet0': 'br-phy0', 'physnet1': 'br-phy1'},
                         self._get_bridge_mappings_as_dict(conf))
        self.assertEqual({'br-phy0': 'eth0', 'br-phy1': 'bond0'},
                         self._get_auto_bridge_add(conf))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_openvswitch_vlan_over_bond(self, *_):
        self._set_vswitch_mode()
        self._topology_vlan_over_bond()

        conf = self._get_host_config()

        self.assertEqual({'physnet0': 'br-phy0'},
                         self._get_bridge_mappings_as_dict(conf))
        # the OS vlan interface name, not the underlying bond
        self.assertEqual({'br-phy0': 'vlan#100'},
                         self._get_auto_bridge_add(conf))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_openvswitch_two_datanets(self, *_):
        self._set_vswitch_mode()
        self._topology_two_datanets()

        conf = self._get_host_config()

        # Pre-existing inconsistency, frozen on purpose: bridge_mappings
        # increments per data network while auto_bridge_add increments per
        # interface, so br-phy1 is mapped but never created.  Fixing it would
        # rename bridges on working OVS-kernel systems, so it is left out.
        self.assertEqual({'physnet0': 'br-phy0', 'physnet1': 'br-phy1'},
                         self._get_bridge_mappings_as_dict(conf))
        self.assertEqual({'br-phy0': 'eth0'},
                         self._get_auto_bridge_add(conf))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_openvswitch_bond_and_vxlan_only(self, *_):
        self._set_vswitch_mode()
        self._topology_bond_and_vxlan_only()

        conf = self._get_host_config()

        self.assertEqual({'physnet1': 'br-phy0'},
                         self._get_bridge_mappings_as_dict(conf))
        self.assertEqual({'br-phy0': 'bond0'},
                         self._get_auto_bridge_add(conf))
        self.assertEqual(
            constants.DATANETWORK_TYPE_VXLAN,
            conf['plugins']['openvswitch_agent']['agent']['tunnel_types'])

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_openvswitch_bond_and_sriov(self, *_):
        self._set_vswitch_mode()
        self._topology_bond_and_sriov()

        conf = self._get_host_config()

        # SR-IOV sorts as an ethernet interface, ahead of the AE, and consumes
        # a bridge index.  This is the pre-existing behaviour and it is kept:
        # with OVS-kernel the application creates every bridge it maps, so its
        # own indexing is self consistent.
        self.assertEqual({'physnet1': 'br-phy0', 'physnet0': 'br-phy1'},
                         self._get_bridge_mappings_as_dict(conf))
        self.assertEqual({'br-phy0': 'eth2', 'br-phy1': 'bond0'},
                         self._get_auto_bridge_add(conf))

    # ==================================================================
    # OVS-DPDK, bridge_mappings of the configurations already supported.
    #
    # These assert ONLY bridge_mappings, on purpose: OVS-DPDK is already
    # supported for these topologies, so their mapping must be exactly the same
    # before and after this change.  Keeping the auto_bridge_add assertion out
    # of them is what makes that provable -- with both in the same test, the
    # auto_bridge_add mismatch would fail the test and hide the fact that the
    # mapping did not change.
    # ==================================================================
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_bridge_mappings_unchanged_ethernet_vlan(self, *_):
        self._set_vswitch_mode(dpdk=True)
        self._topology_ethernet_vlan()

        conf = self._get_host_config()

        self.assertEqual({'physnet0': 'br-phy0'},
                         self._get_bridge_mappings_as_dict(conf))
        self.assertEqual(
            'netdev',
            conf['plugins']['openvswitch_agent']['ovs']['datapath_type'])

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_bridge_mappings_unchanged_ethernet_flat(self, *_):
        self._set_vswitch_mode(dpdk=True)
        self._topology_ethernet_flat()

        conf = self._get_host_config()

        self.assertEqual({'physnet0': 'br-phy0'},
                         self._get_bridge_mappings_as_dict(conf))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_bridge_mappings_unchanged_bond_and_ethernet(self, *_):
        self._set_vswitch_mode(dpdk=True)
        self._topology_bond_and_ethernet()

        conf = self._get_host_config()

        # both orderings place ethernet ahead of AE, so the names are the same
        # the application produced before this change
        self.assertEqual({'physnet0': 'br-phy0', 'physnet1': 'br-phy1'},
                         self._get_bridge_mappings_as_dict(conf))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_bridge_mappings_unchanged_vlan_over_bond(self, *_):
        self._set_vswitch_mode(dpdk=True)
        self._topology_vlan_over_bond()

        conf = self._get_host_config()

        self.assertEqual({'physnet0': 'br-phy0'},
                         self._get_bridge_mappings_as_dict(conf))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_bridge_mappings_unchanged_bond_vlan(self, *_):
        """The topology this change adds support for.

        Its mapping happens to be the same one the application produced before,
        which is why the OVS-DPDK support for a single AE data interface was
        already working: what this change fixes for it is that the application
        no longer asks the agent to touch the bridge (see the auto_bridge_add
        test of the same topology).
        """
        self._set_vswitch_mode(dpdk=True)
        self._topology_bond_vlan()

        conf = self._get_host_config()

        self.assertEqual({'physnet0': 'br-phy0'},
                         self._get_bridge_mappings_as_dict(conf))

    # ==================================================================
    # OVS-DPDK, bridge_mappings of the configurations that were diverging.
    #
    # Here the mapping DOES change: before this change it named a bridge the
    # platform never creates.  These are the three divergences of the analysis.
    # ==================================================================
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_bridge_mappings_aligned_two_datanets(self, *_):
        """Two data networks on one interface share the platform's bridge.

        The platform creates exactly one bridge per data interface, so mapping
        the second data network to a second bridge pointed at something that
        does not exist.
        """
        self._set_vswitch_mode(dpdk=True)
        self._topology_two_datanets()

        conf = self._get_host_config()

        self.assertEqual({'physnet0': 'br-phy0', 'physnet1': 'br-phy0'},
                         self._get_bridge_mappings_as_dict(conf))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_bridge_mappings_aligned_bond_and_vxlan_only(self, *_):
        """A data interface with only a vxlan data network consumes an index.

        The platform bridges every data interface regardless of the data
        network type, so the AE is the second bridge, not the first.
        """
        self._set_vswitch_mode(dpdk=True)
        self._topology_bond_and_vxlan_only()

        conf = self._get_host_config()

        self.assertEqual({'physnet1': 'br-phy1'},
                         self._get_bridge_mappings_as_dict(conf))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_bridge_mappings_aligned_bond_and_sriov(self, *_):
        """The data interface and the SR-IOV one use distinct bridges.

        The platform creates a br-phy bridge for the AE data interface only.
        The SR-IOV data network must still be mapped, so the OVS agent binds
        its DHCP/L3/metadata helper ports, but to a separate br-sriov bridge
        that the agent creates (see auto_bridge_add), never to the platform's
        br-phy0 (which would leave two uplinks on one bridge).

        Regression guard for the DHCP binding fixed by change 951900: before
        this fix the SR-IOV data network was left unmapped on OVS-DPDK.
        """
        self._set_vswitch_mode(dpdk=True)
        self._topology_bond_and_sriov()

        conf = self._get_host_config()

        self.assertEqual({'physnet0': 'br-phy0', 'physnet1': 'br-sriov0'},
                         self._get_bridge_mappings_as_dict(conf))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_bridge_mappings_sriov_only_is_mapped(self, *_):
        """An SR-IOV-only host still maps its data network.

        The platform creates no br-phy bridge here, but the SR-IOV data
        network's helper ports are handled by the OVS agent, so the network is
        mapped to an agent-created br-sriov bridge.  Regression guard for
        change 951900 on OVS-DPDK.
        """
        self._set_vswitch_mode(dpdk=True)
        self._topology_sriov_only()

        conf = self._get_host_config()

        self.assertEqual({'physnet0': 'br-sriov0'},
                         self._get_bridge_mappings_as_dict(conf))

    # ==================================================================
    # OVS-DPDK, auto_bridge_add.
    #
    # This is the part that changes deliberately: with OVS-DPDK every physical
    # bridge is created by the platform, so the application asks the agent for
    # none of them.  Asserted separately from bridge_mappings for the reason
    # explained above.
    # ==================================================================
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_auto_bridge_add_ethernet_vlan(self, *_):
        self._set_vswitch_mode(dpdk=True)
        self._topology_ethernet_vlan()

        self.assertEqual({}, self._get_auto_bridge_add(self._get_host_config()))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_auto_bridge_add_ethernet_flat(self, *_):
        self._set_vswitch_mode(dpdk=True)
        self._topology_ethernet_flat()

        self.assertEqual({}, self._get_auto_bridge_add(self._get_host_config()))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_auto_bridge_add_bond_vlan(self, *_):
        """The AE bridge and its OVS bond belong to the platform.

        Before this change the application asked the agent to add br-phy0 and
        to attach the bond to it.  On a host with OVS-DPDK those requests were
        inert -- the bridge already existed and there is no Linux netdev for a
        DPDK interface to attach -- but asking for them at all is wrong.
        """
        self._set_vswitch_mode(dpdk=True)
        self._topology_bond_vlan()

        self.assertEqual({}, self._get_auto_bridge_add(self._get_host_config()))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_auto_bridge_add_bond_and_ethernet(self, *_):
        self._set_vswitch_mode(dpdk=True)
        self._topology_bond_and_ethernet()

        self.assertEqual({}, self._get_auto_bridge_add(self._get_host_config()))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_auto_bridge_add_vlan_over_bond(self, *_):
        self._set_vswitch_mode(dpdk=True)
        self._topology_vlan_over_bond()

        self.assertEqual({}, self._get_auto_bridge_add(self._get_host_config()))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_auto_bridge_add_bond_and_sriov(self, *_):
        """Only the SR-IOV bridge is requested from the agent.

        The AE data interface's br-phy bridge is created by the platform and
        must not be requested from the agent.  The SR-IOV interface gets no
        platform bridge, so its br-sriov bridge is requested here, with the
        SR-IOV port attached, so the data network's helper ports can bind.
        """
        self._set_vswitch_mode(dpdk=True)
        self._topology_bond_and_sriov()

        # bond members consume eth0/eth1, so the SR-IOV port is eth2.
        self.assertEqual({'br-sriov0': 'eth2'},
                         self._get_auto_bridge_add(self._get_host_config()))

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_dpdk_auto_bridge_add_sriov_only(self, *_):
        """On an SR-IOV-only host the agent is asked for the br-sriov bridge.

        Regression guard for change 951900 on OVS-DPDK: the SR-IOV data
        network's helper ports need this agent-created bridge to bind.
        """
        self._set_vswitch_mode(dpdk=True)
        self._topology_sriov_only()

        self.assertEqual({'br-sriov0': 'eth0'},
                         self._get_auto_bridge_add(self._get_host_config()))

    # ==================================================================
    # invariants
    # ==================================================================
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_auto_bridge_add_is_always_a_table(self, *_):
        """auto_bridge_add must never be emitted as None.

        The chart renders this value with toJson and the agent init script
        iterates over the result without guarding the bridge creation, so None
        would create a bridge literally named 'null' on the host, and omitting
        the key would let the bridge list of the chart ({br-ex: null}) create
        br-ex.  An empty table is the only safe way to say "nothing to do".
        """
        self._set_vswitch_mode(dpdk=True)

        table = self._get_auto_bridge_add(self._get_host_config())

        self.assertIsNotNone(table)
        self.assertEqual({}, table)

    def test_platform_interface_sort_key_matches_the_platform(self):
        """The sort key replica must order interfaces like the platform does.

        Compared against the live sysinv implementation instead of a
        transcription of it, so that a future change to the platform's ordering
        is detected here rather than silently diverging.
        """
        try:
            from sysinv.puppet import interface as puppet_interface
        except ImportError:  # pragma: no cover
            self.skipTest('sysinv.puppet.interface is not importable')

        ifaces = [
            {'ifname': 'vlan100', 'iftype': constants.INTERFACE_TYPE_VLAN,
             'ifclass': constants.INTERFACE_CLASS_DATA},
            {'ifname': 'data1', 'iftype': constants.INTERFACE_TYPE_ETHERNET,
             'ifclass': constants.INTERFACE_CLASS_DATA},
            {'ifname': 'bond0', 'iftype': constants.INTERFACE_TYPE_AE,
             'ifclass': constants.INTERFACE_CLASS_DATA},
            {'ifname': 'data0', 'iftype': constants.INTERFACE_TYPE_ETHERNET,
             'ifclass': constants.INTERFACE_CLASS_DATA},
            {'ifname': 'lo', 'iftype': constants.INTERFACE_TYPE_VIRTUAL,
             'ifclass': constants.INTERFACE_CLASS_DATA},
        ]

        self.assertEqual(
            [iface['ifname'] for iface in
             sorted(ifaces, key=puppet_interface.interface_sort_key)],
            [iface['ifname'] for iface in
             sorted(ifaces, key=app_utils.platform_interface_sort_key)])
