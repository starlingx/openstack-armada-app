#
# Copyright (c) 2020-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import collections
import random

import mock
from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import utils as cutils
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
        ceph_resolution_patcher = mock.patch(
            'k8sapp_openstack.helm.nova.is_nova_ephemeral_ceph_enabled',
            return_value=False
        )
        ceph_resolution_patcher.start()
        self.addCleanup(ceph_resolution_patcher.stop)
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

    @mock.patch('k8sapp_openstack.helm.nova.NovaHelm._enable_multipath', return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_nova_overrides_enable_multipath_conf_daemonset(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertTrue(overrides['manifests']['daemonset_multipath_conf'])
        self.assertIn('statefulset_compute_ironic', overrides['manifests'])

    @mock.patch('k8sapp_openstack.helm.nova.NovaHelm._enable_multipath', return_value=False)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_nova_overrides_disable_multipath_conf_daemonset(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertFalse(overrides['manifests']['daemonset_multipath_conf'])

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
        self.assertEqual(
            overrides['conf']['address_selection']['node_network_cidrs'],
            [expected_subnet]
        )

    @mock.patch('k8sapp_openstack.helm.nova.NovaHelm._get_cluster_host_subnets',
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
        self.assertEqual(
            overrides['conf']['address_selection']['node_network_cidrs'],
            []
        )

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

    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.nova.NovaHelm._resolve_nova_pvc_overrides',
        return_value={}
    )
    @mock.patch(
        'k8sapp_openstack.helm.nova.is_nova_ephemeral_ceph_enabled',
        return_value=True
    )
    @mock.patch(
        'k8sapp_openstack.helm.nova.NovaHelm._get_rbd_ephemeral_storage',
        return_value={
            'type': 'rbd',
            'rbd_pools': [{
                'rbd_pool_name': 'ephemeral',
                'rbd_user': 'cinder',
                'rbd_crush_rule': 'storage_tier_ruleset',
                'rbd_replication': 2,
                'rbd_chunk_size': 256,
            }]
        }
    )
    def test_nova_overrides_resolves_ceph_backend(
        self,
        mock_get_rbd_ephemeral_storage,
        mock_is_nova_ephemeral_ceph_enabled,
        *_
    ):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK
        )

        self.assertEqual(
            overrides['conf']['nova']['libvirt']['images_type'],
            'rbd'
        )
        self.assertEqual(
            overrides['conf']['nova']['libvirt']['images_rbd_pool'],
            'ephemeral'
        )
        self.assertEqual(
            overrides['rbd_pool']['replication'],
            2
        )
        self.assertEqual(
            overrides['rbd_pool']['crush_rule'],
            'storage_tier_ruleset'
        )
        self.assertEqual(
            overrides['rbd_pool']['app_name'],
            app_constants.CEPH_POOL_EPHEMERAL_NAME
        )
        mock_is_nova_ephemeral_ceph_enabled.assert_called_once_with()
        mock_get_rbd_ephemeral_storage.assert_called()

    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.nova.NovaHelm._resolve_nova_pvc_overrides',
        return_value={}
    )
    @mock.patch(
        'k8sapp_openstack.helm.nova.is_nova_ephemeral_ceph_enabled',
        return_value=False
    )
    def test_nova_overrides_skips_ceph_when_not_selected(
        self,
        mock_is_nova_ephemeral_ceph_enabled,
        *_
    ):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK
        )

        self.assertNotIn('rbd_pool', overrides)
        mock_is_nova_ephemeral_ceph_enabled.assert_called_once_with()


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


# ---------------------------------------------------------------------------
# Multi-NUMA fixtures
# ---------------------------------------------------------------------------
Cpu = collections.namedtuple(
    'Cpu', ['cpu', 'thread', 'allocated_function', 'numa_node'])
Mem = collections.namedtuple(
    'Mem', ['numa_node', 'platform_reserved_mib',
            'vswitch_hugepages_size_mib', 'vswitch_hugepages_nr'])
Host = collections.namedtuple('Host', ['id'])
# Minimal ethernet_ports row stand-in for _get_interface_numa_nodes.
Port = collections.namedtuple('Port', ['interface_id', 'numa_node'])


def make_icpu(host_id, num_nodes, cores_per_node=8):
    """Build an icpu list spread across num_nodes NUMA nodes.

    On every node one core each is assigned PLATFORM, VSWITCH, SHARED and
    ISOLATED; the remaining cores on the node are APPLICATION. CPU ids are
    globally unique and ascending, so the APPLICATION and ISOLATED sets drawn
    back out span every node rather than collapsing onto node 0 -- a fixture
    that only produced node-0 CPUs would pass against a socket-shaped
    implementation and defeat the point of the multi-node check.
    """
    functions = [
        constants.PLATFORM_FUNCTION,
        constants.VSWITCH_FUNCTION,
        constants.SHARED_FUNCTION,
        constants.ISOLATED_FUNCTION,
    ]
    cpus = []
    cpu_id = 0
    for node in range(num_nodes):
        for i in range(cores_per_node):
            if i < len(functions):
                fn = functions[i]
            else:
                fn = constants.APPLICATION_FUNCTION
            cpus.append(Cpu(cpu=cpu_id, thread=0,
                            allocated_function=fn, numa_node=node))
            cpu_id += 1
    return cpus


def make_imemory(host_id, num_nodes, platform_mib=1000,
                 vswitch_size_mib=2, vswitch_nr=512):
    """Build an imemory list, one cell per NUMA node.

    vswitch_size_mib may be a scalar (applied to every node) or a per-node
    list, allowing a mix of 2 MiB and 1 GiB pages across nodes.
    """
    cells = []
    for node in range(num_nodes):
        if isinstance(vswitch_size_mib, (list, tuple)):
            size = vswitch_size_mib[node]
        else:
            size = vswitch_size_mib
        cells.append(Mem(numa_node=node,
                         platform_reserved_mib=platform_mib,
                         vswitch_hugepages_size_mib=size,
                         vswitch_hugepages_nr=vswitch_nr))
    return cells


def helm_with(cpus=None, memory=None, host_id=0):
    """Return a fresh NovaHelm(None) with inventory assigned directly.

    No dbapi, no mocking of format_range_set or _oslo_multistring_override --
    the real utils.format_range_set and OpenstackBaseHelm._oslo_multistring_override
    run, so the assertions pin end-to-end output.
    """
    helm_obj = nova.NovaHelm(None)
    if cpus is not None:
        helm_obj.cpus_by_hostid = {host_id: cpus}
    if memory is not None:
        helm_obj.memory_by_hostid = {host_id: memory}
    return helm_obj


class NovaMultiNumaTest(testtools.TestCase):
    """Regression fence for the NUMA-facing NovaHelm methods.

    NovaHelm._update_host_cpu_maps and NovaHelm._update_reserved_memory read
    per-node inventory out of instance attributes and format it without any
    assumption that node count equals socket count, so they are expected to
    stay correct when a host reports more NUMA nodes than it has sockets (for
    example a 2-socket host exposing 4 or 8 nodes under sub-NUMA clustering).
    These tests assert that behaviour at 1, 4 and 8 NUMA nodes so that a later
    change to helm/nova.py that broke it would be caught.

    Each case constructs its own nova.NovaHelm(None) via helm_with() and
    assigns cpus_by_hostid / memory_by_hostid on it, so no inventory state is
    shared between cases. Those attributes are plain instance state initialised
    in NovaHelm.__init__, so a fresh instance per case is the whole isolation
    requirement; there is no memoised node count that can leak from an 8-node
    case into a 4-node one.
    """

    def setUp(self):
        super(NovaMultiNumaTest, self).setUp()
        self._clear_module_caches()

    def tearDown(self):
        super(NovaMultiNumaTest, self).tearDown()
        self._clear_module_caches()

    @staticmethod
    def _clear_module_caches():
        """Clear any module-level @lru_cache reachable from the call path.

        Precedent: TestNumaNodes in sysinv/tests/agent/test_node.py clears
        node_module._read_numa_nodes.cache_clear() in both setUp and tearDown
        so a sticky node count from one case cannot let a later case pass. The
        two methods here read only instance attributes and reach no
        node-count-bearing cache, but any module-level cache in the shared
        sysinv.common.utils call path is cleared defensively -- guarded by
        hasattr, because the installed sysinv may expose none -- so this test
        cannot inherit cached state from whatever ran before it.
        """
        for name in ('format_range_set', 'get_debian_codename'):
            fn = getattr(cutils, name, None)
            if fn is not None and hasattr(fn, 'cache_clear'):
                fn.cache_clear()

    # ------------------------------------------------------------------
    # _update_host_cpu_maps
    # ------------------------------------------------------------------

    def test_cpu_maps_1_4_8_nodes(self):
        """cpu_shared_set / cpu_dedicated_set at 1, 4 and 8 nodes.

        Asserts the exact strings, including the embedded double quotes,
        written as literals rather than recomputed from the fixture. Also
        asserts that CPUs drawn from every node in the fixture appear in the
        output, since a fixture producing only node-0 CPUs would pass against a
        socket-shaped implementation and defeat the multi-node check. The
        1-node fixture is a regression guard so a later fix cannot assume
        multi-node input.

        make_icpu(.., N, cores_per_node=8) lays out, per node:
          node k cpus = [8k .. 8k+7]; 8k=PLATFORM 8k+1=VSWITCH 8k+2=SHARED
          8k+3=ISOLATED, 8k+4..8k+7 = APPLICATION
        so APPLICATION (-> cpu_shared_set) is cpus 4-7 on every node and
        ISOLATED (-> cpu_dedicated_set) is cpu 3 on every node.
        """
        expected = {
            1: ('"4-7"', '"3"'),
            4: ('"4-7,12-15,20-23,28-31"', '"3,11,19,27"'),
            8: ('"4-7,12-15,20-23,28-31,36-39,44-47,52-55,60-63"',
                '"3,11,19,27,35,43,51,59"'),
        }
        for num_nodes, (shared, dedicated) in expected.items():
            helm_obj = helm_with(cpus=make_icpu(0, num_nodes))
            compute_config = {}
            helm_obj._update_host_cpu_maps(Host(id=0), compute_config)
            self.assertEqual(compute_config['cpu_shared_set'], shared)
            self.assertEqual(compute_config['cpu_dedicated_set'], dedicated)

            # CPUs from every node must appear, not just node 0.
            for node in range(num_nodes):
                app_cpu_on_node = str(8 * node + 4)
                self.assertIn(app_cpu_on_node, compute_config['cpu_shared_set'])

    def test_cpu_maps_shared_function_absent(self):
        """SHARED_FUNCTION negative control.

        The word "shared" appears in both constants.SHARED_FUNCTION and the
        cpu_shared_set key and means different things: SHARED_FUNCTION is a
        StarlingX CPU role, while cpu_shared_set is Nova's pool of floating VM
        CPUs. _update_host_cpu_maps derives cpu_shared_set from
        constants.APPLICATION_FUNCTION alone and reads SHARED_FUNCTION nowhere,
        so the SHARED cpus (cpu 2 on every node in the fixture) must be absent
        from cpu_shared_set.
        """
        for num_nodes in (1, 4, 8):
            helm_obj = helm_with(cpus=make_icpu(0, num_nodes))
            compute_config = {}
            helm_obj._update_host_cpu_maps(Host(id=0), compute_config)
            for node in range(num_nodes):
                shared_cpu_on_node = str(8 * node + 2)
                # Match the token exactly so e.g. '2' does not match '12'/'20'.
                tokens = compute_config['cpu_shared_set'].strip('"').replace(
                    '-', ',').split(',')
                self.assertNotIn(shared_cpu_on_node, tokens)

    def test_cpu_maps_icpu_permutation_byte_identical(self):
        """icpu permutation -> byte-identical output.

        This is a stronger claim than the reserved-memory permutation test
        (test_reserved_memory_row_permutation_multiset), which only asserts
        multiset equality: here the formatted string is identical regardless
        of input row order. It holds because utils.format_range_set in
        sysinv/common/utils.py sorts before grouping into ranges, so the input
        row order cannot affect the formatted string.
        """
        cpus = make_icpu(0, 4)
        ordered = helm_with(cpus=cpus)
        ordered_config = {}
        ordered._update_host_cpu_maps(Host(id=0), ordered_config)

        shuffled = list(cpus)
        random.Random(1234).shuffle(shuffled)
        shuffled_helm = helm_with(cpus=shuffled)
        shuffled_config = {}
        shuffled_helm._update_host_cpu_maps(Host(id=0), shuffled_config)

        self.assertEqual(shuffled_config, ordered_config)

    # ------------------------------------------------------------------
    # _update_reserved_memory
    # ------------------------------------------------------------------

    def test_reserved_memory_cardinality_4_8_nodes(self):
        """Exactly 2N reserved_huge_pages entries at 4 and 8 nodes.

        One size:4 (4K) entry and one vswitch-page entry per node, each
        carrying only its own row's node: key. Expected values are derived from
        the fixture, not transcribed: the 4K count is
        platform_reserved_mib * constants.NUM_4K_PER_MiB and the vswitch page
        size is vswitch_hugepages_size_mib * constants.Ki.
        """
        for num_nodes in (4, 8):
            cells = make_imemory(0, num_nodes)
            helm_obj = helm_with(memory=cells)
            default_config = {}
            helm_obj._update_reserved_memory(Host(id=0), default_config)
            values = default_config['reserved_huge_pages']['values']

            self.assertEqual(len(values), 2 * num_nodes)

            expected = []
            for cell in cells:
                count_4k = cell.platform_reserved_mib * constants.NUM_4K_PER_MiB
                expected.append(
                    'node:%d,size:4,count:%d' % (cell.numa_node, count_4k))
                page_size = cell.vswitch_hugepages_size_mib * constants.Ki
                expected.append(
                    'node:%d,size:%d,count:%d' % (
                        cell.numa_node, page_size, cell.vswitch_hugepages_nr))
            self.assertEqual(values, expected)

            # Each entry carries only its own row's node, no other.
            for node in range(num_nodes):
                node_entries = [v for v in values
                                if v.startswith('node:%d,' % node)]
                self.assertEqual(len(node_entries), 2)

    def test_reserved_memory_total_both_terms(self):
        """reserved_host_memory_mb is the sum of both terms.

        Equals the sum over all rows of
        platform_reserved_mib + (vswitch_hugepages_size_mib * vswitch_hugepages_nr),
        derived here from both terms rather than hard-coded. The vswitch
        hugepage term is included alongside platform_reserved_mib; omitting it
        is an easy mistake.
        """
        for num_nodes in (4, 8):
            cells = make_imemory(0, num_nodes)
            helm_obj = helm_with(memory=cells)
            default_config = {}
            helm_obj._update_reserved_memory(Host(id=0), default_config)

            expected_total = sum(
                cell.platform_reserved_mib
                + cell.vswitch_hugepages_size_mib * cell.vswitch_hugepages_nr
                for cell in cells)
            self.assertEqual(
                default_config['reserved_host_memory_mb'], expected_total)

    def test_reserved_memory_row_permutation_multiset(self):
        """Row permutation asserted as a multiset, not list identity.

        _oslo_multistring_override in k8sapp_openstack/helm/openstack.py builds
        values in row order, so list equality against a reordered input fails
        for a reason unrelated to correctness; the invariant that actually
        holds is multiset equality of values plus exact equality of
        reserved_host_memory_mb.

        The complementary list-order assertion is kept here to document the
        syntactic behaviour: the values list order tracks the supplied row
        order. That same row-order dependence is why the two-host
        de-duplication test fixes each host's row order explicitly -- two
        hosts with semantically identical memory but different row order would
        otherwise produce unequal conf dicts.
        """
        ascending = make_imemory(0, 4)
        base = helm_with(memory=ascending)
        base_config = {}
        base._update_reserved_memory(Host(id=0), base_config)
        ascending_values = base_config['reserved_huge_pages']['values']

        # Reversed, then shuffled.
        for reordered in (list(reversed(ascending)),
                          random.Random(99).sample(ascending, len(ascending))):
            helm_obj = helm_with(memory=reordered)
            cfg = {}
            helm_obj._update_reserved_memory(Host(id=0), cfg)
            values = cfg['reserved_huge_pages']['values']

            # Multiset equality: same entries, order may differ.
            self.assertEqual(sorted(values), sorted(ascending_values))
            # Exact total regardless of row order.
            self.assertEqual(cfg['reserved_host_memory_mb'],
                             base_config['reserved_host_memory_mb'])

            # Complementary syntactic fact: the values list order tracks the
            # supplied row order. List equality against the ascending output is
            # therefore WRONG here (the rows differ in order), which is exactly
            # why the assertion above is a multiset comparison.
            expected_for_this_order = []
            for cell in reordered:
                count_4k = cell.platform_reserved_mib * constants.NUM_4K_PER_MiB
                expected_for_this_order.append(
                    'node:%d,size:4,count:%d' % (cell.numa_node, count_4k))
                page_size = cell.vswitch_hugepages_size_mib * constants.Ki
                expected_for_this_order.append(
                    'node:%d,size:%d,count:%d' % (
                        cell.numa_node, page_size, cell.vswitch_hugepages_nr))
            self.assertEqual(values, expected_for_this_order)

    def test_reserved_memory_heterogeneous_page_size(self):
        """Each row emits its own page size.

        vswitch_size_mib alternates 1 GiB (1024 MiB) and 2 MiB per node; each
        row must emit size:1048576 for the 1 GiB rows and size:2048 for the
        2 MiB rows (1024 * Ki and 2 * Ki respectively). This pins the per-node
        keyed emission so that each NUMA node keeps its own page size rather
        than collapsing to a single host-wide value.
        """
        sizes = [1024, 2, 1024, 2, 1024, 2, 1024, 2]
        cells = make_imemory(0, 8, vswitch_size_mib=sizes)
        helm_obj = helm_with(memory=cells)
        default_config = {}
        helm_obj._update_reserved_memory(Host(id=0), default_config)
        values = default_config['reserved_huge_pages']['values']

        for cell in cells:
            if cell.vswitch_hugepages_size_mib == 1024:
                expected_page = 'node:%d,size:1048576,count:%d' % (
                    cell.numa_node, cell.vswitch_hugepages_nr)
            else:
                expected_page = 'node:%d,size:2048,count:%d' % (
                    cell.numa_node, cell.vswitch_hugepages_nr)
            self.assertIn(expected_page, values)

    # ------------------------------------------------------------------
    # _get_per_host_overrides de-duplication
    # ------------------------------------------------------------------

    def test_per_host_dedup_two_divergent_hosts(self):
        """Two hosts whose per-node memory diverges -> two entries.

        _get_per_host_overrides collapses hosts with identical conf into a
        single entry; two hosts whose per-node memory differs must stay
        distinct. Asserted on the entry count (2), never on "the shared entry".

        Each host's row order is fixed by the fixture: reserved_huge_pages.values
        is an ordered list, so two hosts with semantically identical memory but
        different row order would produce unequal conf dicts for a reason
        unrelated to what this test asserts.

        _get_per_host_overrides needs more than the two instance caches --
        dbapi.ihost_get_list(), utils.get_personalities(host),
        utils.has_openstack_compute(host_labels), and _update_host_pci_whitelist
        reaching dbapi.pci_device_get_by_host -- so a mock.Mock() dbapi
        returning stub worker hosts and empty PCI device lists is used in
        preference to the DB-backed NovaGetOverrideTest style.
        """
        host_a = mock.Mock()
        host_a.id = 0
        host_a.hostname = 'compute-0'
        host_a.invprovision = constants.PROVISIONED
        host_a.ihost_action = None
        host_b = mock.Mock()
        host_b.id = 1
        host_b.hostname = 'compute-1'
        host_b.invprovision = constants.PROVISIONED
        host_b.ihost_action = None

        dbapi = mock.Mock()
        dbapi.ihost_get_list.return_value = [host_a, host_b]
        dbapi.pci_device_get_by_host.return_value = []

        # NovaHelm.dbapi is a read-only property backed by operator.dbapi
        # (sysinv/helm/base.py), so the stub dbapi is supplied through a stub
        # operator rather than assigned on the helm instance directly.
        operator = mock.Mock()
        operator.dbapi = dbapi
        helm_obj = nova.NovaHelm(operator)
        # Divergent per-node memory: host A has 4 nodes, host B has 8.
        helm_obj.cpus_by_hostid = {0: make_icpu(0, 4), 1: make_icpu(1, 8)}
        helm_obj.memory_by_hostid = {0: make_imemory(0, 4),
                                     1: make_imemory(1, 8)}
        helm_obj.labels_by_hostid = {0: [], 1: []}
        # Empty per-host interface/port/address/datanet caches so the PCI
        # whitelist pass finds no devices and emits nothing.
        helm_obj.ethernet_ports_by_hostid = {}
        helm_obj.interfaces_by_hostid = {}
        helm_obj.ifdatanets_by_ifaceid = {}
        helm_obj.datanets_by_netuuid = {}
        helm_obj.addresses_by_hostid = {}

        with mock.patch(
                'k8sapp_openstack.helm.nova.utils.get_personalities',
                return_value=[constants.WORKER]), \
                mock.patch(
                    'k8sapp_openstack.helm.nova.utils.has_openstack_compute',
                    return_value=True), \
                mock.patch.object(
                    helm_obj, '_update_host_storage'):
            host_list = helm_obj._get_per_host_overrides()

        self.assertEqual(len(host_list), 2)

    # ------------------------------------------------------------------
    # _get_interface_numa_nodes
    # ------------------------------------------------------------------

    @staticmethod
    def _iface(iface_id, ifname, iftype=None):
        if iftype is None:
            iftype = constants.INTERFACE_TYPE_ETHERNET
        return {'id': iface_id, 'ifname': ifname, 'iftype': iftype,
                'used_by': []}

    def test_interface_numa_nodes_missing_port_row_skipped(self):
        """Ethernet interface with no port row is skipped, not a KeyError."""
        helm_obj = nova.NovaHelm(None)
        context = {
            'interfaces': {'eth0': self._iface(1, 'eth0')},
            'ports': {},
        }
        self.assertEqual(helm_obj._get_interface_numa_nodes(context), {})

    def test_interface_numa_nodes_none_numa_node_skipped(self):
        """numa_node None is skipped, not a TypeError; valid sibling kept."""
        helm_obj = nova.NovaHelm(None)
        context = {
            'interfaces': {
                'eth0': self._iface(1, 'eth0'),
                'eth1': self._iface(2, 'eth1'),
            },
            'ports': {
                1: Port(interface_id=1, numa_node=None),
                2: Port(interface_id=2, numa_node=0),
            },
        }
        result = helm_obj._get_interface_numa_nodes(context)
        self.assertNotIn('eth0', result)
        self.assertEqual(result, {'eth1': {0}})

    def test_neutron_physnet_numa_node_none_sentinel_omitted(self):
        """NUMA_NODE_NONE physnet omitted from physnets and the physnet groups.

        NUMA_NODE_NONE (-1) is distinct from None and must stay excluded by the
        existing >= 0 test; a valid-node sibling proves the omission is specific
        to the sentinel row.
        """
        helm_obj = nova.NovaHelm(None)
        host = Host(id=0)

        ifaces = {
            'eth0': self._iface(1, 'eth0'),
            'eth1': self._iface(2, 'eth1'),
        }
        ports = {
            1: Port(interface_id=1, numa_node=constants.NUMA_NODE_NONE),
            2: Port(interface_id=2, numa_node=0),
        }
        datanets_by_ifname = {
            'eth0': [{'name': 'physnet_none',
                      'network_type': constants.DATANETWORK_TYPE_FLAT}],
            'eth1': [{'name': 'physnet_ok',
                      'network_type': constants.DATANETWORK_TYPE_FLAT}],
        }

        neutron_config = {}
        per_physnet_numa_config = {}
        with mock.patch.object(helm_obj, '_get_port_interface_id_index',
                               return_value=ports), \
                mock.patch.object(helm_obj, '_get_interface_name_index',
                                  return_value=ifaces), \
                mock.patch.object(helm_obj, '_get_interface_name_datanets',
                                  return_value=datanets_by_ifname), \
                mock.patch(
                    'k8sapp_openstack.helm.nova.interface'
                    '.get_interface_datanets',
                    side_effect=lambda ctx, iface:
                        datanets_by_ifname[iface['ifname']]):
            helm_obj._update_host_neutron_physnet(
                host, neutron_config, per_physnet_numa_config)

        physnets = neutron_config.get('physnets', '').split(',')
        self.assertNotIn('physnet_none', physnets)
        self.assertNotIn('neutron_physnet_physnet_none', per_physnet_numa_config)
        self.assertIn('physnet_ok', physnets)
        self.assertEqual(
            per_physnet_numa_config['neutron_physnet_physnet_ok'],
            {'numa_nodes': '0'})
