#
# Copyright (c) 2020-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm import common
from sysinv.helm import helm
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

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

    def _make_data_iface(self, ifname='data0', iface_id=1):
        iface = mock.MagicMock()
        iface.id = iface_id
        iface.ifname = ifname
        iface.iftype = constants.INTERFACE_TYPE_ETHERNET
        iface.ifclass = constants.INTERFACE_CLASS_DATA
        iface.uses = []
        # support dict-style access, mirroring how
        # _get_dynamic_ovs_agent_config/_get_interface_port_name index iface
        iface.__getitem__.side_effect = lambda key: getattr(iface, key)
        return iface

    def _make_datanet(self, name, network_type):
        datanet = mock.MagicMock()
        datanet.datanetwork_network_type = network_type
        datanet.__getitem__.side_effect = lambda key: {
            'datanetwork_name': name,
        }[key]
        return datanet

    @mock.patch('k8sapp_openstack.utils.is_openvswitch_enabled', return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=True)
    @mock.patch('sysinv.common.utils.has_openstack_compute', return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_bridge_mappings_empty_string_for_vxlan_only_host(self, *_):
        """
        Regression test for _get_dynamic_ovs_agent_config (Closes-bug: 2164937):
        a VXLAN-only host must get bridge_mappings as an explicit empty string,
        not have the key omitted (which lets mergo fall back to public:br-ex).
        """
        host = mock.MagicMock(id=1, hostname='controller-1')
        iface = self._make_data_iface(ifname='data0', iface_id=101)
        datanet = self._make_datanet('datanet0', constants.DATANETWORK_TYPE_VXLAN)

        self.neutron_helm.interfaces_by_hostid = {host.id: [iface]}
        self.neutron_helm.ifdatanets_by_ifaceid = {iface.id: [datanet]}
        self.neutron_helm.addresses_by_hostid = {
            host.id: [mock.MagicMock(ifname='data0', address='172.16.0.10')]
        }

        with mock.patch.object(neutron.NeutronHelm, 'context',
                               new_callable=mock.PropertyMock,
                               return_value=mock.MagicMock()):
            config = self.neutron_helm._get_dynamic_ovs_agent_config(host)

        self.assertIn('bridge_mappings', config['ovs'])
        self.assertEqual('', config['ovs']['bridge_mappings'])
        self.assertEqual('172.16.0.10', config['ovs']['local_ip'])
        self.assertEqual(constants.DATANETWORK_TYPE_VXLAN,
                         config['agent']['tunnel_types'])

    @mock.patch('k8sapp_openstack.utils.is_openvswitch_enabled', return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=True)
    @mock.patch('sysinv.common.utils.has_openstack_compute', return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_bridge_mappings_populated_for_vlan_host(self, *_):
        """
        A host with a VLAN-mapped data interface must still get a populated
        bridge_mappings string (existing behaviour must not regress).
        """
        host = mock.MagicMock(id=2, hostname='controller-0')
        iface = self._make_data_iface(ifname='data0', iface_id=201)
        datanet = self._make_datanet('group0-data0', constants.DATANETWORK_TYPE_VLAN)

        self.neutron_helm.interfaces_by_hostid = {host.id: [iface]}
        self.neutron_helm.ifdatanets_by_ifaceid = {iface.id: [datanet]}
        self.neutron_helm.addresses_by_hostid = {host.id: []}
        self.neutron_helm.ports_by_ifaceid = {iface.id: [{'name': 'eth0'}]}

        config = self.neutron_helm._get_dynamic_ovs_agent_config(host)

        self.assertIn('bridge_mappings', config['ovs'])
        self.assertTrue(config['ovs']['bridge_mappings'].startswith('group0-data0:br-phy'))
        self.assertNotIn('local_ip', config['ovs'])
        self.assertNotIn('tunnel_types', config['agent'])


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
