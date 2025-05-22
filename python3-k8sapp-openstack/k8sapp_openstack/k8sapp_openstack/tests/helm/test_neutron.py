#
# Copyright (c) 2020-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.common import constants
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
