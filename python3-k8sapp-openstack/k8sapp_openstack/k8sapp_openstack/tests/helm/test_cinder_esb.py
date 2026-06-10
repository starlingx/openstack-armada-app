#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for ESB (Extended Storage Backend) support in CinderHelm.

Tests cover:
- active_protocols computation (strict, ESB, hybrid, orphan entries)
- Pod security context derivation from active_protocols
- ESB backend emission into conf.backends and enabled_backends
- Strict-mode regression (no ESB present)
"""

import mock
from sysinv.helm import common
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base
import testtools

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import cinder
from k8sapp_openstack.tests import test_plugins


class CinderESBTestCase(test_plugins.K8SAppOpenstackAppMixin,
                        base.HelmTestCaseMixin):
    """Base test case for Cinder ESB tests."""

    def setUp(self):
        super(CinderESBTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class TestComputeActiveProtocols(testtools.TestCase):
    """Unit tests for CinderHelm._compute_active_protocols()."""

    def _make_helm(self, available_backends, backends_conf, volume_priority=None):
        """Create a CinderHelm instance with mocked attributes."""
        ch = cinder.CinderHelm(None)
        ch.available_backends = available_backends
        ch._backends_conf = backends_conf
        # By default every known backend participates in the priority list so
        # tests focus on protocol resolution; orphan-exclusion tests override.
        if volume_priority is None:
            volume_priority = list(available_backends.keys()) + list(backends_conf.keys())
        ch.VOLUME_PRIORITY_LIST = volume_priority
        return ch

    def test_ceph_only(self):
        """Ceph-only: active_protocols should contain only 'rbd'."""
        ch = self._make_helm(
            available_backends={'ceph': 'general',
                                'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': ''},
            backends_conf={}
        )
        result = ch._compute_active_protocols()
        self.assertEqual(result, ['rbd'])

    def test_netapp_nfs_only(self):
        """NetApp NFS only: active_protocols should contain 'nfs'."""
        ch = self._make_helm(
            available_backends={'ceph': '',
                                'netapp-nfs': 'netapp-nas-backend',
                                'netapp-iscsi': '', 'netapp-fc': ''},
            backends_conf={}
        )
        result = ch._compute_active_protocols()
        self.assertEqual(result, ['nfs'])

    def test_netapp_iscsi_only(self):
        """NetApp iSCSI only: active_protocols should contain 'iscsi'."""
        ch = self._make_helm(
            available_backends={'ceph': '',
                                'netapp-nfs': '',
                                'netapp-iscsi': 'netapp-san-backend',
                                'netapp-fc': ''},
            backends_conf={}
        )
        result = ch._compute_active_protocols()
        self.assertEqual(result, ['iscsi'])

    def test_netapp_fc_only(self):
        """NetApp FC only: active_protocols should contain 'fcp'."""
        ch = self._make_helm(
            available_backends={'ceph': '',
                                'netapp-nfs': '', 'netapp-iscsi': '',
                                'netapp-fc': 'netapp-fc-backend'},
            backends_conf={}
        )
        result = ch._compute_active_protocols()
        self.assertEqual(result, ['fcp'])

    def test_ceph_plus_netapp_iscsi(self):
        """Hybrid ceph + netapp-iscsi: active_protocols = ['iscsi', 'rbd']."""
        ch = self._make_helm(
            available_backends={'ceph': 'general',
                                'netapp-nfs': '',
                                'netapp-iscsi': 'netapp-san-backend',
                                'netapp-fc': ''},
            backends_conf={}
        )
        result = ch._compute_active_protocols()
        self.assertEqual(result, ['iscsi', 'rbd'])

    def test_esb_iscsi_only(self):
        """ESB iSCSI backend: active_protocols = ['iscsi']."""
        ch = self._make_helm(
            available_backends={
                'ceph': '', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': '',
                'dell-powerstore-iscsi': ''
            },
            backends_conf={
                'dell-powerstore-iscsi': {
                    'name': 'dell-powerstore-iscsi',
                    'protocol': 'iscsi',
                    'k8s_storage_class': 'none',
                    'volume_backend': {}
                }
            }
        )
        result = ch._compute_active_protocols()
        self.assertEqual(result, ['iscsi'])

    def test_esb_nfs_only(self):
        """ESB NFS backend: active_protocols = ['nfs']."""
        ch = self._make_helm(
            available_backends={
                'ceph': '', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': '',
                'dell-powerstore-nfs': 'dell-nfs'
            },
            backends_conf={
                'dell-powerstore-nfs': {
                    'name': 'dell-powerstore-nfs',
                    'protocol': 'nfs',
                    'k8s_storage_class': 'dell-nfs',
                    'volume_backend': {}
                }
            }
        )
        result = ch._compute_active_protocols()
        self.assertEqual(result, ['nfs'])

    def test_esb_fcp_only(self):
        """ESB FCP backend: active_protocols = ['fcp']."""
        ch = self._make_helm(
            available_backends={
                'ceph': '', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': '',
                'vendor-fc': ''
            },
            backends_conf={
                'vendor-fc': {
                    'name': 'vendor-fc',
                    'protocol': 'fcp',
                    'k8s_storage_class': 'none',
                    'volume_backend': {}
                }
            }
        )
        result = ch._compute_active_protocols()
        self.assertEqual(result, ['fcp'])

    def test_esb_local_only(self):
        """ESB local backend: active_protocols = ['local']."""
        ch = self._make_helm(
            available_backends={
                'ceph': '', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': '',
                'rakuten-cns': ''
            },
            backends_conf={
                'rakuten-cns': {
                    'name': 'rakuten-cns',
                    'protocol': 'local',
                    'k8s_storage_class': 'none',
                    'volume_backend': {}
                }
            }
        )
        result = ch._compute_active_protocols()
        self.assertEqual(result, ['local'])

    def test_hybrid_ceph_plus_esb_iscsi(self):
        """Hybrid: Ceph + ESB iSCSI -> active_protocols = ['iscsi', 'rbd']."""
        ch = self._make_helm(
            available_backends={
                'ceph': 'general', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': '',
                'dell-powerstore-iscsi': ''
            },
            backends_conf={
                'dell-powerstore-iscsi': {
                    'name': 'dell-powerstore-iscsi',
                    'protocol': 'iscsi',
                    'k8s_storage_class': 'none',
                    'volume_backend': {}
                }
            }
        )
        result = ch._compute_active_protocols()
        self.assertEqual(result, ['iscsi', 'rbd'])

    def test_esb_multi_protocol(self):
        """Multiple ESB backends with different protocols."""
        ch = self._make_helm(
            available_backends={
                'ceph': '', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': '',
                'dell-iscsi': '',
                'dell-nfs': 'dell-nfs-sc'
            },
            backends_conf={
                'dell-iscsi': {
                    'name': 'dell-iscsi',
                    'protocol': 'iscsi',
                    'k8s_storage_class': 'none',
                    'volume_backend': {}
                },
                'dell-nfs': {
                    'name': 'dell-nfs',
                    'protocol': 'nfs',
                    'k8s_storage_class': 'dell-nfs-sc',
                    'volume_backend': {}
                }
            }
        )
        result = ch._compute_active_protocols()
        self.assertEqual(result, ['iscsi', 'nfs'])

    def test_orphan_backends_conf_does_not_contribute(self):
        """Orphan backends_conf entry (not in available_backends) is excluded."""
        ch = self._make_helm(
            available_backends={
                'ceph': 'general', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': ''
            },
            backends_conf={
                'orphan-backend': {
                    'name': 'orphan-backend',
                    'protocol': 'iscsi',
                    'k8s_storage_class': 'none',
                    'volume_backend': {}
                }
            }
        )
        result = ch._compute_active_protocols()
        # Only ceph contributes (rbd), orphan is excluded
        self.assertEqual(result, ['rbd'])

    def test_invalid_protocol_skipped(self):
        """ESB backend with invalid protocol is skipped."""
        ch = self._make_helm(
            available_backends={
                'ceph': '', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': '',
                'bad-backend': ''
            },
            backends_conf={
                'bad-backend': {
                    'name': 'bad-backend',
                    'protocol': 'rbd',  # rbd is not valid for ESB
                    'k8s_storage_class': 'none',
                    'volume_backend': {}
                }
            }
        )
        result = ch._compute_active_protocols()
        self.assertEqual(result, [])

    def test_no_backends_active(self):
        """No backends available: empty active_protocols."""
        ch = self._make_helm(
            available_backends={
                'ceph': '', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': ''
            },
            backends_conf={}
        )
        result = ch._compute_active_protocols()
        self.assertEqual(result, [])


class TestIsBackendAvailable(testtools.TestCase):
    """Unit tests for CinderHelm._is_backend_available().

    Pod security context derivation from active_protocols is delivered and
    tested by the ESB foundation (OpenstackBaseHelm._get_protocol_pod_config,
    covered by test_openstack.py), so it is not re-tested here.
    """

    def _make_helm(self, available_backends, backends_conf):
        ch = cinder.CinderHelm(None)
        ch.available_backends = available_backends
        ch._backends_conf = backends_conf
        ch.VOLUME_PRIORITY_LIST = list(available_backends.keys())
        return ch

    def test_strict_backend_with_storage_class_available(self):
        """Strict backend with a truthy StorageClass is available."""
        ch = self._make_helm(
            available_backends={'ceph': 'general'},
            backends_conf={}
        )
        self.assertTrue(ch._is_backend_available('ceph'))

    def test_strict_backend_without_storage_class_unavailable(self):
        """Strict backend with empty StorageClass is not available."""
        ch = self._make_helm(
            available_backends={'ceph': '', 'netapp-nfs': ''},
            backends_conf={}
        )
        self.assertFalse(ch._is_backend_available('ceph'))
        self.assertFalse(ch._is_backend_available('netapp-nfs'))

    def test_esb_backend_with_none_storage_class_available(self):
        """ESB backend with k8s_storage_class: none (empty value) is still available.

        This is the key fix: an ESB iSCSI backend that manages storage directly
        over the network has no K8s StorageClass but IS a valid Cinder volume
        backend. A truthiness check on the value would wrongly skip it.
        """
        ch = self._make_helm(
            available_backends={'dell-iscsi': ''},
            backends_conf={
                'dell-iscsi': {
                    'name': 'dell-iscsi',
                    'protocol': 'iscsi',
                    'k8s_storage_class': 'none',
                    'volume_backend': {}
                }
            }
        )
        self.assertTrue(ch._is_backend_available('dell-iscsi'))

    def test_esb_backend_with_storage_class_available(self):
        """ESB backend with a real StorageClass is available."""
        ch = self._make_helm(
            available_backends={'dell-nfs': 'dell-nfs-sc'},
            backends_conf={
                'dell-nfs': {
                    'name': 'dell-nfs',
                    'protocol': 'nfs',
                    'k8s_storage_class': 'dell-nfs-sc',
                    'volume_backend': {}
                }
            }
        )
        self.assertTrue(ch._is_backend_available('dell-nfs'))

    def test_esb_backend_not_in_available_unavailable(self):
        """ESB backend not present in available_backends is unavailable."""
        ch = self._make_helm(
            available_backends={'ceph': 'general'},
            backends_conf={
                'dell-iscsi': {
                    'name': 'dell-iscsi',
                    'protocol': 'iscsi',
                    'k8s_storage_class': 'none',
                    'volume_backend': {}
                }
            }
        )
        self.assertFalse(ch._is_backend_available('dell-iscsi'))

    def test_esb_backend_without_conf_entry_unavailable(self):
        """ESB backend in available_backends but no conf entry is unavailable."""
        ch = self._make_helm(
            available_backends={'orphan-esb': ''},
            backends_conf={}
        )
        self.assertFalse(ch._is_backend_available('orphan-esb'))

    def test_esb_backend_invalid_protocol_unavailable(self):
        """ESB backend with invalid protocol is unavailable."""
        ch = self._make_helm(
            available_backends={'bad-backend': ''},
            backends_conf={
                'bad-backend': {
                    'name': 'bad-backend',
                    'protocol': 'invalid',
                    'k8s_storage_class': 'none',
                    'volume_backend': {}
                }
            }
        )
        self.assertFalse(ch._is_backend_available('bad-backend'))


class TestESBBackendEmission(testtools.TestCase):
    """Unit tests for CinderHelm._get_conf_esb_cinder_overrides()."""

    def _make_helm(self, available_backends, backends_conf, volume_priority):
        ch = cinder.CinderHelm(None)
        ch.available_backends = available_backends
        ch._backends_conf = backends_conf
        ch.VOLUME_PRIORITY_LIST = volume_priority
        return ch

    def test_esb_backend_emitted_in_enabled_backends(self):
        """ESB backend is added to enabled_backends."""
        ch = self._make_helm(
            available_backends={
                'ceph': '', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': '',
                'dell-iscsi': ''
            },
            backends_conf={
                'dell-iscsi': {
                    'name': 'dell-iscsi',
                    'protocol': 'iscsi',
                    'k8s_storage_class': 'none',
                    'volume_backend': {
                        'volume_backend_name': 'dell-iscsi',
                        'volume_driver': 'cinder.volume.drivers.dell_emc.powerstore.driver.PowerStoreDriver',
                        'san_ip': '10.0.0.1',
                        'san_login': 'admin',
                        'san_password': 'password',
                    }
                }
            },
            volume_priority=['dell-iscsi', 'ceph']
        )
        cinder_overrides = {'DEFAULT': {}}
        backend_overrides = {}

        cinder_overrides, backend_overrides = ch._get_conf_esb_cinder_overrides(
            cinder_overrides, backend_overrides)

        # Verify enabled_backends contains the ESB entry
        enabled = set(cinder_overrides['DEFAULT']['enabled_backends'].split(','))
        self.assertIn('dell-iscsi', enabled)

        # Verify volume_backend is emitted as-is
        self.assertIn('dell-iscsi', backend_overrides)
        self.assertEqual(backend_overrides['dell-iscsi']['volume_driver'],
                         'cinder.volume.drivers.dell_emc.powerstore.driver.PowerStoreDriver')
        self.assertEqual(backend_overrides['dell-iscsi']['san_ip'], '10.0.0.1')

    def test_esb_backend_empty_volume_backend(self):
        """ESB backend with empty volume_backend emits an empty section."""
        ch = self._make_helm(
            available_backends={
                'ceph': '', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': '',
                'my-backend': 'my-sc'
            },
            backends_conf={
                'my-backend': {
                    'name': 'my-backend',
                    'protocol': 'nfs',
                    'k8s_storage_class': 'my-sc',
                    'volume_backend': {}
                }
            },
            volume_priority=['my-backend']
        )
        cinder_overrides = {'DEFAULT': {}}
        backend_overrides = {}

        cinder_overrides, backend_overrides = ch._get_conf_esb_cinder_overrides(
            cinder_overrides, backend_overrides)

        self.assertIn('my-backend', backend_overrides)
        self.assertEqual(backend_overrides['my-backend'], {})

    def test_esb_backend_not_in_priority_list_skipped(self):
        """ESB backend available but not in priority list is not emitted."""
        ch = self._make_helm(
            available_backends={
                'ceph': 'general', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': '',
                'dell-iscsi': ''
            },
            backends_conf={
                'dell-iscsi': {
                    'name': 'dell-iscsi',
                    'protocol': 'iscsi',
                    'k8s_storage_class': 'none',
                    'volume_backend': {'san_ip': '10.0.0.1'}
                }
            },
            volume_priority=['ceph']  # dell-iscsi NOT in priority list
        )
        cinder_overrides = {'DEFAULT': {}}
        backend_overrides = {}

        cinder_overrides, backend_overrides = ch._get_conf_esb_cinder_overrides(
            cinder_overrides, backend_overrides)

        self.assertNotIn('dell-iscsi', backend_overrides)

    def test_strict_backend_in_priority_not_processed_as_esb(self):
        """Strict backends in priority list are not processed by ESB method."""
        ch = self._make_helm(
            available_backends={
                'ceph': 'general', 'netapp-nfs': 'netapp-nas',
                'netapp-iscsi': '', 'netapp-fc': ''
            },
            backends_conf={},
            volume_priority=['ceph', 'netapp-nfs']
        )
        cinder_overrides = {'DEFAULT': {'enabled_backends': 'ceph,netapp-nfs'}}
        backend_overrides = {'ceph': {}, 'netapp-nfs': {}}

        cinder_overrides, backend_overrides = ch._get_conf_esb_cinder_overrides(
            cinder_overrides, backend_overrides)

        # No new backends should be added
        self.assertEqual(set(cinder_overrides['DEFAULT']['enabled_backends'].split(',')),
                         {'ceph', 'netapp-nfs'})

    def test_esb_no_backends_conf_entry_skipped(self):
        """ESB backend without matching backends_conf entry is skipped."""
        ch = self._make_helm(
            available_backends={
                'ceph': '', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': '',
                'orphan-esb': ''
            },
            backends_conf={},  # No entry for orphan-esb
            volume_priority=['orphan-esb']
        )
        cinder_overrides = {'DEFAULT': {}}
        backend_overrides = {}

        cinder_overrides, backend_overrides = ch._get_conf_esb_cinder_overrides(
            cinder_overrides, backend_overrides)

        self.assertNotIn('orphan-esb', backend_overrides)

    def test_esb_invalid_protocol_skipped(self):
        """ESB backend with invalid protocol is skipped."""
        ch = self._make_helm(
            available_backends={
                'ceph': '', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': '',
                'bad-backend': ''
            },
            backends_conf={
                'bad-backend': {
                    'name': 'bad-backend',
                    'protocol': 'invalid',
                    'k8s_storage_class': 'none',
                    'volume_backend': {'key': 'val'}
                }
            },
            volume_priority=['bad-backend']
        )
        cinder_overrides = {'DEFAULT': {}}
        backend_overrides = {}

        cinder_overrides, backend_overrides = ch._get_conf_esb_cinder_overrides(
            cinder_overrides, backend_overrides)

        self.assertNotIn('bad-backend', backend_overrides)

    def test_multiple_esb_backends(self):
        """Multiple ESB backends are all emitted."""
        ch = self._make_helm(
            available_backends={
                'ceph': '', 'netapp-nfs': '', 'netapp-iscsi': '', 'netapp-fc': '',
                'dell-iscsi': '',
                'dell-nfs': 'dell-nfs-sc'
            },
            backends_conf={
                'dell-iscsi': {
                    'name': 'dell-iscsi',
                    'protocol': 'iscsi',
                    'k8s_storage_class': 'none',
                    'volume_backend': {'san_ip': '10.0.0.1'}
                },
                'dell-nfs': {
                    'name': 'dell-nfs',
                    'protocol': 'nfs',
                    'k8s_storage_class': 'dell-nfs-sc',
                    'volume_backend': {'nfs_shares_config': '/etc/cinder/nfs.shares'}
                }
            },
            volume_priority=['dell-iscsi', 'dell-nfs']
        )
        cinder_overrides = {'DEFAULT': {}}
        backend_overrides = {}

        cinder_overrides, backend_overrides = ch._get_conf_esb_cinder_overrides(
            cinder_overrides, backend_overrides)

        enabled = set(cinder_overrides['DEFAULT']['enabled_backends'].split(','))
        self.assertIn('dell-iscsi', enabled)
        self.assertIn('dell-nfs', enabled)
        self.assertIn('dell-iscsi', backend_overrides)
        self.assertIn('dell-nfs', backend_overrides)
        self.assertEqual(backend_overrides['dell-iscsi'], {'san_ip': '10.0.0.1'})
        self.assertEqual(backend_overrides['dell-nfs'],
                         {'nfs_shares_config': '/etc/cinder/nfs.shares'})


class TestCinderESBOverridesIntegration(CinderESBTestCase,
                                        dbbase.ControllerHostTestCase):
    """Integration tests for ESB in get_overrides()."""

    def setUp(self):
        super(TestCinderESBOverridesIntegration, self).setUp()
        # TLS helper functions read user overrides from the DB; mock them so
        # _get_mount_overrides() does not require a populated helm_override row.
        patchers = [
            mock.patch('k8sapp_openstack.helm.cinder.get_storage_tls_host_cert',
                       return_value=None),
            mock.patch('k8sapp_openstack.helm.cinder.get_storage_tls_container_certs',
                       return_value=[]),
            mock.patch('k8sapp_openstack.helm.cinder.is_storage_ca_cert_secret_available',
                       return_value=False),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_storage_backends_priority_list',
        return_value=['dell-iscsi']
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_storage_backup_priority_list',
        return_value=['dell-iscsi']
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_available_volume_backends',
        return_value={
            'ceph': '',
            app_constants.NETAPP_NFS_BACKEND_NAME: '',
            app_constants.NETAPP_ISCSI_BACKEND_NAME: '',
            app_constants.NETAPP_FC_BACKEND_NAME: '',
            'dell-iscsi': ''
        }
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_backends_conf',
        return_value={
            'dell-iscsi': {
                'name': 'dell-iscsi',
                'protocol': 'iscsi',
                'k8s_storage_class': 'none',
                'volume_backend': {
                    'volume_backend_name': 'dell-iscsi',
                    'volume_driver': 'cinder.volume.drivers.dell_emc.powerstore.driver.PowerStoreDriver',
                    'san_ip': '10.0.0.1',
                }
            }
        }
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.is_ceph_backend_available',
        return_value=(False, "")
    )
    def test_esb_iscsi_only_deployment(self, *_):
        """ESB-only iSCSI: correct pod security context and backend emission."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CINDER,
            cnamespace=common.HELM_NS_OPENSTACK)

        # active_protocols should contain 'iscsi'
        active_protocols = overrides['storage_conf']['active_protocols']
        self.assertIn('iscsi', active_protocols)
        self.assertNotIn('rbd', active_protocols)

        # Pod security: host network, privileged backup, not read-only
        self.assertTrue(overrides['pod']['useHostNetwork']['volume'])
        self.assertTrue(overrides['pod']['useHostNetwork']['backup'])
        sec_ctx = overrides['pod']['security_context']
        self.assertTrue(
            sec_ctx['cinder_backup']['container']['cinder_backup']['privileged'])
        self.assertFalse(
            sec_ctx['cinder_volume']['container']['cinder_volume']['readOnlyRootFilesystem'])

        # enable_iscsi = True
        self.assertTrue(overrides['conf']['enable_iscsi'])

        # Backend emission
        enabled = set(overrides['conf']['cinder']['DEFAULT']['enabled_backends'].split(','))
        self.assertIn('dell-iscsi', enabled)
        self.assertIn('dell-iscsi', overrides['conf']['backends'])
        self.assertEqual(overrides['conf']['backends']['dell-iscsi']['san_ip'], '10.0.0.1')

        # default_volume_type follows priority
        self.assertEqual(overrides['conf']['cinder']['DEFAULT']['default_volume_type'], 'dell-iscsi')

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_storage_backends_priority_list',
        return_value=['dell-local']
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_storage_backup_priority_list',
        return_value=['dell-local']
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_available_volume_backends',
        return_value={
            'ceph': '',
            app_constants.NETAPP_NFS_BACKEND_NAME: '',
            app_constants.NETAPP_ISCSI_BACKEND_NAME: '',
            app_constants.NETAPP_FC_BACKEND_NAME: '',
            'dell-local': ''
        }
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_backends_conf',
        return_value={
            'dell-local': {
                'name': 'dell-local',
                'protocol': 'local',
                'k8s_storage_class': 'none',
                'volume_backend': {
                    'volume_backend_name': 'dell-local',
                    'volume_driver': 'cinder.volume.drivers.rakuten.cns.driver.CNSDriver',
                }
            }
        }
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.is_ceph_backend_available',
        return_value=(False, "")
    )
    def test_esb_local_protocol_most_restrictive(self, *_):
        """ESB local protocol: most restrictive pod security profile."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CINDER,
            cnamespace=common.HELM_NS_OPENSTACK)

        active_protocols = overrides['storage_conf']['active_protocols']
        self.assertEqual(active_protocols, ['local'])

        # Most restrictive profile
        self.assertFalse(overrides['pod']['useHostNetwork']['volume'])
        self.assertFalse(overrides['pod']['useHostNetwork']['backup'])
        sec_ctx = overrides['pod']['security_context']
        self.assertFalse(
            sec_ctx['cinder_backup']['container']['cinder_backup']['privileged'])
        self.assertTrue(
            sec_ctx['cinder_volume']['container']['cinder_volume']['readOnlyRootFilesystem'])
        self.assertFalse(overrides['conf']['enable_iscsi'])

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_storage_backends_priority_list',
        return_value=['ceph']
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_storage_backup_priority_list',
        return_value=['ceph']
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_available_volume_backends',
        return_value={
            'ceph': 'general',
            app_constants.NETAPP_NFS_BACKEND_NAME: '',
            app_constants.NETAPP_ISCSI_BACKEND_NAME: '',
            app_constants.NETAPP_FC_BACKEND_NAME: '',
        }
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_backends_conf',
        return_value={}
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.is_ceph_backend_available',
        return_value=(False, "")
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_cinder_overrides',
        return_value={'DEFAULT': {'enabled_backends': 'ceph', 'default_volume_type': 'ceph'}}
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_overrides',
        return_value={'monitors': [], 'admin_keyring': 'null', 'pools': {}}
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_backends_overrides',
        return_value={'ceph': {'volume_backend_name': 'ceph'}}
    )
    def test_ceph_only_regression(self, *_):
        """Ceph-only: behavior preserved, active_protocols = ['rbd']."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CINDER,
            cnamespace=common.HELM_NS_OPENSTACK)

        # active_protocols is the only new addition
        active_protocols = overrides['storage_conf']['active_protocols']
        self.assertEqual(active_protocols, ['rbd'])

        # Pod security: most restrictive (no iSCSI/FCP/NFS)
        self.assertFalse(overrides['pod']['useHostNetwork']['volume'])
        self.assertFalse(overrides['pod']['useHostNetwork']['backup'])
        sec_ctx = overrides['pod']['security_context']
        self.assertFalse(
            sec_ctx['cinder_backup']['container']['cinder_backup']['privileged'])
        self.assertTrue(
            sec_ctx['cinder_volume']['container']['cinder_volume']['readOnlyRootFilesystem'])
        self.assertFalse(overrides['conf']['enable_iscsi'])
