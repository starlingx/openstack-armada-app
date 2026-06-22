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
import testtools

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import nova
from k8sapp_openstack.tests import test_plugins


class NovaHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                               base.HelmTestCaseMixin):
    def setUp(self):
        super(NovaHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class NovaGetOverrideTest(NovaHelmTestCase,
                          dbbase.ControllerHostTestCase):

    def setUp(self):
        super(NovaGetOverrideTest, self).setUp()
        self.operator = helm.HelmOperator(self.dbapi)
        self.nova = nova.NovaHelm(self.operator)
        pvc_resolution_patcher = mock.patch(
            'k8sapp_openstack.helm.nova.NovaHelm._resolve_nova_pvc_overrides',
            return_value={}
        )
        pvc_resolution_patcher.start()
        self.addCleanup(pvc_resolution_patcher.stop)
        self.worker = self._create_test_host(
            personality=constants.WORKER,
            administrative=constants.ADMIN_LOCKED)
        self.ifaces = self._create_test_host_platform_interface(self.worker)
        self.dbapi.address_create({
            'name': 'test',
            'family': self.oam_subnet.version,
            'prefix': self.oam_subnet.prefixlen,
            'address': str(self.oam_subnet[24]),
            'interface_id': self.ifaces[0].id,
            'enable_dad': self.oam_subnet.version == 6
        })

    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_nova_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {},
            'conf': {},
            'endpoints': {
                'compute': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
                'compute_novnc_proxy': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            },
        })

    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_nova_overrides_use_cluster_host_subnet_for_host_and_migration(
            self, *_):
        cluster_host_network = self.dbapi.network_get_by_type(
            constants.NETWORK_TYPE_CLUSTER_HOST
        )
        cluster_host_pool = self.dbapi.address_pool_get(cluster_host_network.pool_uuid)
        expected_subnet = '%s/%s' % (
            str(cluster_host_pool.network), str(cluster_host_pool.prefix)
        )

        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK
        )

        self.assertEqual(
            overrides['conf']['libvirt']['live_migration_network_cidr'],
            expected_subnet
        )
        self.assertEqual(
            overrides['conf']['hypervisor']['host_network_cidr'],
            expected_subnet
        )
        self.assertEqual(
            overrides['network']['ssh']['from_subnet'],
            expected_subnet
        )

    @mock.patch('k8sapp_openstack.helm.nova.NovaHelm._get_cluster_host_subnet',
                return_value=None)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_nova_overrides_skip_family_defaults_when_cluster_host_cidr_is_unavailable(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK
        )

        self.assertNotIn('libvirt', overrides['conf'])
        self.assertNotIn('hypervisor', overrides['conf'])

    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    def test_nova_overrides_reuses_neutron_ironic_placement_users(self, *_):
        overrides_neutron = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NEUTRON,
            cnamespace=common.HELM_NS_OPENSTACK)
        overrides_ironic = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_IRONIC,
            cnamespace=common.HELM_NS_OPENSTACK)
        overrides_placement = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_PLACEMENT,
            cnamespace=common.HELM_NS_OPENSTACK)
        overrides_nova = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertEqual(
            overrides_nova["endpoints"]["identity"]["auth"]["neutron"],
            overrides_neutron["endpoints"]["identity"]["auth"]["neutron"],
        )
        self.assertEqual(
            overrides_nova["endpoints"]["identity"]["auth"]["ironic"],
            overrides_ironic["endpoints"]["identity"]["auth"]["ironic"],
        )
        self.assertEqual(
            overrides_nova["endpoints"]["identity"]["auth"]["placement"],
            overrides_placement["endpoints"]["identity"]["auth"]["placement"],
        )

    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value={})
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
    def test_nova_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'conf': {
                'nova': {
                    'keystone_authtoken': {
                        'cafile': nova.NovaHelm.get_ca_file()
                    },
                    'libvirt': {
                        'virt_type': mock.ANY,
                        'volume_use_multipath': mock.ANY,
                    },
                    'vnc': {
                        'novncproxy_base_url': mock.ANY,
                    },
                },
                'enable_iscsi': mock.ANY,
                'ceph': {
                    'ephemeral_storage': mock.ANY,
                    'admin_keyring': mock.ANY,
                },
                'overrides': {
                    'nova_compute': mock.ANY,
                },
            },
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': nova.NovaHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'nova': {
                            'cacert': nova.NovaHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'neutron': {
                            'cacert': nova.NovaHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'placement': {
                            'cacert': nova.NovaHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'test': {
                            'cacert': nova.NovaHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                },
                'compute': {
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
                'compute_novnc_proxy': {
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
            'secrets': {
                'tls': {
                    'compute_metadata': {
                        'metadata': {
                            'public': 'nova-tls-public',
                        },
                    },
                },
            },
        })

    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_nova_overrides_invalid_namespace(self, *_):
        """
        Asserts that an exception is raised if an invalid namespace
        is given when retrieving Helm override parameters.
        """
        self.assertRaises(exception.InvalidHelmNamespace,
                          self.operator.get_helm_chart_overrides,
                          app_constants.HELM_CHART_NOVA,
                          cnamespace=common.HELM_NS_DEFAULT)

    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_nova_overrides_missing_namespace(self, *_):
        """
        Tests that the default Helm override parameters
        are returned when no namespace is passed.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA)
        self.assertIsInstance(overrides, dict)
        self.assertIn(common.HELM_NS_OPENSTACK, overrides)

    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.nova.NovaHelm._resolve_nova_pvc_overrides',
        return_value={
            'enabled': True,
            'name': "nova-instances",
            'storage_class': "netapp-nas-backend",
        }
    )
    def test_nova_overrides_resolves_pvc_storage_class(
        self,
        mock_resolve_nova_pvc_overrides,
        *_
    ):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK
        )

        self.assertEqual(
            overrides['storage_conf']['pvc']['volume']['class_name'],
            "netapp-nas-backend"
        )
        self.assertEqual(
            overrides['storage_conf']['pvc']['enabled'],
            True
        )
        self.assertEqual(
            overrides['storage_conf']['pvc']['name'],
            "nova-instances"
        )
        self.assertEqual(
            overrides['conf']['nova']['DEFAULT']['instances_path'],
            app_constants.DEFAULT_NOVA_PVC_INSTANCES_PATH
        )
        mock_resolve_nova_pvc_overrides.assert_called_once_with()

    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.nova.NovaHelm._resolve_nova_pvc_overrides',
        return_value={}
    )
    def test_nova_overrides_skips_pvc_resolution_when_not_enabled(
        self,
        mock_resolve_nova_pvc_overrides,
        *_
    ):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK
        )

        self.assertNotIn('storage_conf', overrides)
        mock_resolve_nova_pvc_overrides.assert_called_once_with()

    @mock.patch('k8sapp_openstack.helm.nova.get_ceph_fsid')
    @mock.patch('k8sapp_openstack.helm.nova.NovaHelm.'
                '_get_cinder_volumes_backends', return_value=[])
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready',
                return_value=False)
    def test_nova_overrides_skips_ceph_fsid_when_ceph_disabled(
            self, _https, _appval, _backends, mock_get_ceph_fsid):
        """NetApp-only / no ceph backend: the _ceph_enabled guard must
        prevent get_ceph_fsid() from being called at all, so no ceph CLI
        subprocess is spawned during override generation.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK)

        mock_get_ceph_fsid.assert_not_called()
        # ceph section always exists under conf, but is disabled
        # and carries no real fsid (secret_uuid stays 'null').
        self.assertFalse(overrides['conf']['ceph']['enabled'])
        self.assertEqual(
            overrides['conf']['ceph']['cinder']['secret_uuid'],
            'null')

    @mock.patch('k8sapp_openstack.helm.nova.get_ceph_fsid',
                return_value='89bd29e9-c505-4170-a097-04dc8e43c897')
    @mock.patch('k8sapp_openstack.helm.nova.is_ceph_backend_available',
                return_value=(False, None))
    @mock.patch('k8sapp_openstack.helm.nova.NovaHelm.'
                '_get_cinder_volumes_backends',
                return_value=[app_constants.CEPH_BACKEND_NAME])
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready',
                return_value=False)
    def test_nova_overrides_uses_ceph_fsid_when_ceph_enabled(
            self, _https, _appval, _backends, _rook, mock_get_ceph_fsid):
        """Ceph enabled + healthy (happy path): get_ceph_fsid() is called
        and its uuid propagates into the ceph/libvirt override secrets.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK)

        mock_get_ceph_fsid.assert_called_once_with()
        self.assertEqual(
            overrides['conf']['ceph']['cinder']['secret_uuid'],
            '89bd29e9-c505-4170-a097-04dc8e43c897')
        self.assertEqual(
            overrides['conf']['nova']['libvirt']['rbd_secret_uuid'],
            '89bd29e9-c505-4170-a097-04dc8e43c897')


class TestEnableMultipath(testtools.TestCase):
    """Unit tests for NovaHelm._enable_multipath()."""

    def _make_helm(self):
        return nova.NovaHelm(None)

    # ------------------------------------------------------------------
    # ESB-first cases
    # ------------------------------------------------------------------

    @mock.patch('k8sapp_openstack.helm.nova.get_backends_conf')
    def test_esb_iscsi_enables_multipath(self, mock_get_backends_conf):
        """ESB entry with protocol: iscsi enables multipath without consulting NetApp."""
        mock_get_backends_conf.return_value = {
            'dell-iscsi': {'name': 'dell-iscsi', 'protocol': 'iscsi'}
        }
        result = self._make_helm()._enable_multipath()
        self.assertTrue(result)

    @mock.patch('k8sapp_openstack.helm.nova.get_backends_conf')
    def test_esb_fcp_enables_multipath(self, mock_get_backends_conf):
        """ESB entry with protocol: fcp enables multipath without consulting NetApp."""
        mock_get_backends_conf.return_value = {
            'vendor-fc': {'name': 'vendor-fc', 'protocol': 'fcp'}
        }
        result = self._make_helm()._enable_multipath()
        self.assertTrue(result)

    @mock.patch('k8sapp_openstack.helm.nova.get_backends_conf')
    def test_esb_nfs_does_not_enable_multipath(self, mock_get_backends_conf):
        """ESB entry with protocol: nfs does not trigger multipath on its own."""
        mock_get_backends_conf.return_value = {
            'dell-nfs': {'name': 'dell-nfs', 'protocol': 'nfs'}
        }
        with mock.patch('k8sapp_openstack.helm.nova.check_netapp_backends',
                        return_value={'netapp-iscsi': False, 'netapp-fc': False}):
            result = self._make_helm()._enable_multipath()
        self.assertFalse(result)

    @mock.patch('k8sapp_openstack.helm.nova.get_backends_conf')
    def test_esb_local_does_not_enable_multipath(self, mock_get_backends_conf):
        """ESB entry with protocol: local does not trigger multipath."""
        mock_get_backends_conf.return_value = {
            'local-backend': {'name': 'local-backend', 'protocol': 'local'}
        }
        with mock.patch('k8sapp_openstack.helm.nova.check_netapp_backends',
                        return_value={'netapp-iscsi': False, 'netapp-fc': False}):
            result = self._make_helm()._enable_multipath()
        self.assertFalse(result)

    @mock.patch('k8sapp_openstack.helm.nova.get_backends_conf')
    def test_esb_check_short_circuits_before_netapp(self, mock_get_backends_conf):
        """When ESB returns iscsi/fcp, check_netapp_backends is never called."""
        mock_get_backends_conf.return_value = {
            'dell-iscsi': {'name': 'dell-iscsi', 'protocol': 'iscsi'}
        }
        with mock.patch('k8sapp_openstack.helm.nova.check_netapp_backends') as mock_netapp:
            result = self._make_helm()._enable_multipath()
        self.assertTrue(result)
        mock_netapp.assert_not_called()

    # ------------------------------------------------------------------
    # NetApp fallback cases
    # ------------------------------------------------------------------

    @mock.patch('k8sapp_openstack.helm.nova.get_backends_conf', return_value={})
    @mock.patch('k8sapp_openstack.helm.nova.check_netapp_backends',
                return_value={'netapp-iscsi': True, 'netapp-fc': False})
    def test_netapp_iscsi_fallback_enables_multipath(self, *_):
        """No ESB entries: NetApp iSCSI backend enables multipath."""
        result = self._make_helm()._enable_multipath()
        self.assertTrue(result)

    @mock.patch('k8sapp_openstack.helm.nova.get_backends_conf', return_value={})
    @mock.patch('k8sapp_openstack.helm.nova.check_netapp_backends',
                return_value={'netapp-iscsi': False, 'netapp-fc': True})
    def test_netapp_fc_fallback_enables_multipath(self, *_):
        """No ESB entries: NetApp FC backend enables multipath."""
        result = self._make_helm()._enable_multipath()
        self.assertTrue(result)

    @mock.patch('k8sapp_openstack.helm.nova.get_backends_conf', return_value={})
    @mock.patch('k8sapp_openstack.helm.nova.check_netapp_backends',
                return_value={'netapp-iscsi': False, 'netapp-fc': False})
    def test_no_backends_disables_multipath(self, *_):
        """No ESB entries and no NetApp iSCSI/FC: multipath is disabled."""
        result = self._make_helm()._enable_multipath()
        self.assertFalse(result)

    @mock.patch('k8sapp_openstack.helm.nova.get_backends_conf')
    @mock.patch('k8sapp_openstack.helm.nova.check_netapp_backends',
                return_value={'netapp-iscsi': False, 'netapp-fc': False})
    def test_esb_no_protocol_key_falls_through_to_netapp(
            self, mock_netapp, mock_get_backends_conf):
        """ESB entry missing 'protocol' key does not trigger multipath on its own."""
        mock_get_backends_conf.return_value = {
            'mystery-backend': {'name': 'mystery-backend'}
        }
        result = self._make_helm()._enable_multipath()
        self.assertFalse(result)
        mock_netapp.assert_called_once()

    @mock.patch('k8sapp_openstack.helm.nova.get_backends_conf')
    @mock.patch('k8sapp_openstack.helm.nova.check_netapp_backends',
                return_value={'netapp-iscsi': True, 'netapp-fc': False})
    def test_esb_nfs_plus_netapp_iscsi_enables_multipath(
            self, mock_netapp, mock_get_backends_conf):
        """ESB NFS (no multipath) + NetApp iSCSI: multipath enabled via fallback."""
        mock_get_backends_conf.return_value = {
            'dell-nfs': {'name': 'dell-nfs', 'protocol': 'nfs'}
        }
        result = self._make_helm()._enable_multipath()
        self.assertTrue(result)
