#
# Copyright (c) 2020-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.common import exception
from sysinv.helm import common
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import glance
from k8sapp_openstack.tests import test_plugins


class GlanceHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                         base.HelmTestCaseMixin):
    def setUp(self):
        super(GlanceHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class GlanceGetOverrideTest(GlanceHelmTestCase,
                               dbbase.ControllerHostTestCase):
    @mock.patch(
        'k8sapp_openstack.helm.glance._get_value_from_application',
        return_value=["ceph"]
    )
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list', return_value=['ceph'])
    @mock.patch(
        'k8sapp_openstack.helm.glance.get_available_volume_backends',
        return_value={"ceph": "general",
                      app_constants.NETAPP_ISCSI_BACKEND_NAME: "",
                      app_constants.NETAPP_NFS_BACKEND_NAME: "",
                      app_constants.NETAPP_FC_BACKEND_NAME: ""}
    )
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_glance_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_GLANCE,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {},
            'endpoints': {
                'image': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            },
            'storage': {},
            'conf': {},
            'bootstrap': {},
            'ceph_client': {},
        })
        self.assertNotIn('volume', overrides)

    @mock.patch(
        'k8sapp_openstack.helm.glance._get_value_from_application',
        return_value=["ceph"]
    )
    @mock.patch(
        'k8sapp_openstack.helm.glance.get_available_volume_backends',
        return_value={"ceph": "general",
                      app_constants.NETAPP_ISCSI_BACKEND_NAME: "",
                      app_constants.NETAPP_NFS_BACKEND_NAME: "",
                      app_constants.NETAPP_FC_BACKEND_NAME: ""}
    )
    @mock.patch('os.path.exists', return_value=True)
    @mock.patch('six.moves.builtins.open', mock.mock_open(read_data="fake"))
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=True)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm.get_ca_file',
        return_value='/etc/ssl/private/openstack/ca-cert.pem'
    )
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list', return_value=['ceph'])
    @mock.patch(
        'k8sapp_openstack.utils.get_openstack_certificate_values',
        return_value={
            app_constants.OPENSTACK_CERT: 'fake',
            app_constants.OPENSTACK_CERT_KEY: 'fake',
            app_constants.OPENSTACK_CERT_CA: 'fake'
        }
    )
    def test_glance_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_GLANCE,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'conf': {
                'glance': {
                    'keystone_authtoken': {
                        'cafile': glance.GlanceHelm.get_ca_file()
                    },
                    'glance_store': {
                        'https_ca_certificates_file': glance.GlanceHelm.get_ca_file(),
                    },
                    'cinder': mock.ANY,
                    'file': {
                        'filesystem_store_datadir': mock.ANY,
                    },
                    'rbd': {
                        'chunk_size': mock.ANY,
                        'rbd_store_pool': mock.ANY,
                        'rbd_store_user': mock.ANY,
                        'rbd_store_replication': mock.ANY,
                        'rbd_store_crush_rule': mock.ANY,
                    },
                    'DEFAULT': mock.ANY
                },
                'glance_registry': {
                    'keystone_authtoken': {
                        'cafile': glance.GlanceHelm.get_ca_file()
                    },
                },
            },
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': glance.GlanceHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'glance': {
                            'cacert': glance.GlanceHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'test': {
                            'cacert': glance.GlanceHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                },
                'image': {
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

    @mock.patch(
        'k8sapp_openstack.helm.glance._get_value_from_application',
        return_value=["ceph"]
    )
    @mock.patch(
        'k8sapp_openstack.helm.glance.get_available_volume_backends',
        return_value={"ceph": "general",
                      app_constants.NETAPP_ISCSI_BACKEND_NAME: "",
                      app_constants.NETAPP_NFS_BACKEND_NAME: "",
                      app_constants.NETAPP_FC_BACKEND_NAME: ""}
    )
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends', return_value={})
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list', return_value=[])
    def test_glance_overrides_invalid_namespace(self, *_):
        """
        Asserts that an exception is raised if an invalid namespace
        is given when retrieving Helm override parameters.
        """
        self.assertRaises(exception.InvalidHelmNamespace,
                          self.operator.get_helm_chart_overrides,
                          app_constants.HELM_CHART_GLANCE,
                          cnamespace=common.HELM_NS_DEFAULT)

    @mock.patch(
        'k8sapp_openstack.helm.glance._get_value_from_application',
        return_value=["ceph"]
    )
    @mock.patch(
        'k8sapp_openstack.helm.glance.get_available_volume_backends',
        return_value={"ceph": "general",
                      app_constants.NETAPP_ISCSI_BACKEND_NAME: "",
                      app_constants.NETAPP_NFS_BACKEND_NAME: "",
                      app_constants.NETAPP_FC_BACKEND_NAME: ""}
    )
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list', return_value=['ceph'])
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_glance_overrides_missing_namespace(self, *_):
        """
        Tests that the default Helm override parameters
        are returned when no namespace is passed.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_GLANCE)
        self.assertIsInstance(overrides, dict)
        self.assertIn(common.HELM_NS_OPENSTACK, overrides)

    @mock.patch(
        'k8sapp_openstack.helm.glance._get_value_from_application',
        return_value=[app_constants.GLANCE_BACKEND_CINDER]
    )
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.helm.glance.get_backend_protocol', return_value='rbd')
    def test_glance_cinder_ceph_hostnetwork_disabled(self, mock_protocol, mock_https, mock_priority, *_):
        """
        Tests that hostNetwork is NOT enabled when Glance uses Cinder with Ceph backend.
        """
        mock_priority.side_effect = [
            [app_constants.GLANCE_BACKEND_CINDER],
            [app_constants.CEPH_BACKEND_NAME]
        ]
        with mock.patch(
            'k8sapp_openstack.helm.glance.get_available_volume_backends',
            return_value={
                app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
                app_constants.GLANCE_BACKEND_RBD: app_constants.GLANCE_BACKEND_RBD,
                app_constants.CEPH_BACKEND_NAME: app_constants.BACKEND_DEFAULT_BACKEND_NAME,
                app_constants.NETAPP_ISCSI_BACKEND_NAME: app_constants.NETAPP_ISCSI_BACKEND_NAME
            }
        ):
            overrides = self.operator.get_helm_chart_overrides(
                app_constants.HELM_CHART_GLANCE,
                cnamespace=common.HELM_NS_OPENSTACK)
            self.assertIn('pod', overrides)
            self.assertNotIn('useHostNetwork', overrides['pod'])
            self.assertNotIn('security_context', overrides['pod'])

    @mock.patch(
        'k8sapp_openstack.helm.glance._get_value_from_application',
        return_value=[app_constants.GLANCE_BACKEND_CINDER]
    )
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.helm.glance.get_backend_protocol', return_value='iscsi')
    def test_glance_cinder_iscsi_hostnetwork_enabled(self, mock_protocol, mock_https, mock_priority, *_):
        """
        Tests that hostNetwork is enabled when Glance uses Cinder with iSCSI backend.
        """
        mock_priority.side_effect = [
            [app_constants.GLANCE_BACKEND_CINDER],
            [app_constants.NETAPP_ISCSI_BACKEND_NAME]
        ]
        with mock.patch(
            'k8sapp_openstack.helm.glance.get_available_volume_backends',
            return_value={
                app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
                app_constants.GLANCE_BACKEND_RBD: app_constants.GLANCE_BACKEND_RBD,
                app_constants.NETAPP_ISCSI_BACKEND_NAME: app_constants.NETAPP_ISCSI_BACKEND_NAME,
                app_constants.NETAPP_FC_BACKEND_NAME: app_constants.NETAPP_FC_BACKEND_NAME
            }
        ):
            overrides = self.operator.get_helm_chart_overrides(
                app_constants.HELM_CHART_GLANCE,
                cnamespace=common.HELM_NS_OPENSTACK)
            self.assertIn('pod', overrides)
            self.assertIn('useHostNetwork', overrides['pod'])
            self.assertEqual(overrides['pod']['useHostNetwork']['api'], True)
            self.assertIn('security_context', overrides['pod'])


class GlancePodOverridesESBTest(GlanceHelmTestCase,
                                dbbase.ControllerHostTestCase):
    """Tests for _get_pod_overrides() with ESB backends."""

    @mock.patch(
        'k8sapp_openstack.helm.glance._get_value_from_application',
        return_value=[app_constants.GLANCE_BACKEND_CINDER]
    )
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.helm.glance.get_backend_protocol', return_value='iscsi')
    def test_esb_iscsi_enables_host_network(self, mock_protocol, mock_https, mock_priority, *_):
        """ESB iSCSI backend enables useHostNetwork and privileged for Glance API."""
        mock_priority.side_effect = [
            [app_constants.GLANCE_BACKEND_CINDER],
            ['dell-powerstore-iscsi']
        ]
        with mock.patch(
            'k8sapp_openstack.helm.glance.get_available_volume_backends',
            return_value={
                app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
                'dell-powerstore-iscsi': 'dell-powerstore-iscsi'
            }
        ):
            overrides = self.operator.get_helm_chart_overrides(
                app_constants.HELM_CHART_GLANCE,
                cnamespace=common.HELM_NS_OPENSTACK)
            self.assertIn('pod', overrides)
            self.assertIn('useHostNetwork', overrides['pod'])
            self.assertEqual(overrides['pod']['useHostNetwork'], {'api': True})
            self.assertIn('security_context', overrides['pod'])

    @mock.patch(
        'k8sapp_openstack.helm.glance._get_value_from_application',
        return_value=[app_constants.GLANCE_BACKEND_CINDER]
    )
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.helm.glance.get_backend_protocol', return_value='nfs')
    def test_esb_nfs_no_host_network(self, mock_protocol, mock_https, mock_priority, *_):
        """ESB NFS backend does not enable useHostNetwork or privileged."""
        mock_priority.side_effect = [
            [app_constants.GLANCE_BACKEND_CINDER],
            ['dell-powerstore-nfs']
        ]
        with mock.patch(
            'k8sapp_openstack.helm.glance.get_available_volume_backends',
            return_value={
                app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
                'dell-powerstore-nfs': 'dell-powerstore-nfs'
            }
        ):
            overrides = self.operator.get_helm_chart_overrides(
                app_constants.HELM_CHART_GLANCE,
                cnamespace=common.HELM_NS_OPENSTACK)
            self.assertIn('pod', overrides)
            self.assertNotIn('useHostNetwork', overrides['pod'])
            self.assertNotIn('security_context', overrides['pod'])

    @mock.patch(
        'k8sapp_openstack.helm.glance._get_value_from_application',
        return_value=[app_constants.GLANCE_BACKEND_CINDER]
    )
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.helm.glance.get_backend_protocol', return_value='iscsi')
    def test_esb_iscsi_k8s_storage_class_none(self, mock_protocol, mock_https, mock_priority, *_):
        """ESB iSCSI with k8s_storage_class: none still enables host networking."""
        mock_priority.side_effect = [
            [app_constants.GLANCE_BACKEND_CINDER],
            ['dell-powerstore-iscsi']
        ]
        with mock.patch(
            'k8sapp_openstack.helm.glance.get_available_volume_backends',
            return_value={
                app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
                'dell-powerstore-iscsi': ''
            }
        ):
            overrides = self.operator.get_helm_chart_overrides(
                app_constants.HELM_CHART_GLANCE,
                cnamespace=common.HELM_NS_OPENSTACK)
            self.assertIn('pod', overrides)
            self.assertIn('useHostNetwork', overrides['pod'])
            self.assertEqual(overrides['pod']['useHostNetwork'], {'api': True})
            self.assertIn('security_context', overrides['pod'])

    @mock.patch(
        'k8sapp_openstack.helm.glance._get_value_from_application',
        return_value=[app_constants.GLANCE_BACKEND_CINDER]
    )
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.helm.glance.get_backend_protocol', return_value='iscsi')
    def test_strict_netapp_iscsi_still_enables_host_network(self, mock_protocol, mock_https, mock_priority, *_):
        """Regression: strict NetApp iSCSI still enables useHostNetwork."""
        mock_priority.side_effect = [
            [app_constants.GLANCE_BACKEND_CINDER],
            [app_constants.NETAPP_ISCSI_BACKEND_NAME]
        ]
        with mock.patch(
            'k8sapp_openstack.helm.glance.get_available_volume_backends',
            return_value={
                app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
                app_constants.NETAPP_ISCSI_BACKEND_NAME: app_constants.NETAPP_ISCSI_BACKEND_NAME,
                app_constants.NETAPP_FC_BACKEND_NAME: app_constants.NETAPP_FC_BACKEND_NAME
            }
        ):
            overrides = self.operator.get_helm_chart_overrides(
                app_constants.HELM_CHART_GLANCE,
                cnamespace=common.HELM_NS_OPENSTACK)
            self.assertIn('pod', overrides)
            self.assertIn('useHostNetwork', overrides['pod'])
            self.assertEqual(overrides['pod']['useHostNetwork'], {'api': True})


class GlanceGenericPvcGetStorageTest(GlanceHelmTestCase,
                                     dbbase.ControllerHostTestCase):
    """Unit tests for _get_storage() and _resolve_glance_pvc_storage_class().

    Covers test plan items U-1 through U-8 and U-12, U-13, U-14, U-15, U-16.
    """

    def _make_helm_instance(self):
        """Create a GlanceHelm instance for direct method testing."""
        return glance.GlanceHelm(self.operator)

    # ------------------------------------------------------------------
    # U-1: _get_storage() with pvc entry + ESB backend in PVC priority
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.is_strict_backend')
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    def test_get_storage_pvc_with_esb_backend(
        self, mock_avail, mock_pvc_priority, mock_strict, mock_backends_conf
    ):
        """U-1: pvc entry resolves ESB backend via get_backends_conf()."""
        helm = self._make_helm_instance()
        helm._priority_list = [app_constants.GLANCE_BACKEND_PVC]
        helm._available_backends = {
            app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
        }
        helm._migrated_pvc_priority = None

        # _resolve_glance_pvc_storage_class mocks
        mock_avail.return_value = {}  # No strict backends in PVC resolution
        mock_pvc_priority.return_value = ['dell-nfs']
        mock_strict.return_value = False  # dell-nfs is ESB
        mock_backends_conf.return_value = {
            'dell-nfs': {'k8s_storage_class': 'dell-nfs'}
        }

        backend, storage_class = helm._get_storage()
        self.assertEqual(backend, app_constants.GLANCE_BACKEND_PVC)
        self.assertEqual(storage_class, 'dell-nfs')

    # ------------------------------------------------------------------
    # U-2: _get_storage() with pvc entry + strict backend in PVC priority
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.is_strict_backend')
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    def test_get_storage_pvc_with_strict_backend(
        self, mock_avail, mock_pvc_priority, mock_strict, mock_backends_conf
    ):
        """U-2: pvc entry resolves strict backend from pvc_available_backends."""
        helm = self._make_helm_instance()
        helm._priority_list = [app_constants.GLANCE_BACKEND_PVC]
        helm._available_backends = {
            app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
        }
        helm._migrated_pvc_priority = None

        mock_avail.return_value = {
            app_constants.NETAPP_NFS_BACKEND_NAME: 'netapp-nfs-sc'
        }
        mock_pvc_priority.return_value = [app_constants.NETAPP_NFS_BACKEND_NAME]
        mock_strict.return_value = True
        mock_backends_conf.return_value = {}

        backend, storage_class = helm._get_storage()
        self.assertEqual(backend, app_constants.GLANCE_BACKEND_PVC)
        self.assertEqual(storage_class, 'netapp-nfs-sc')

    # ------------------------------------------------------------------
    # U-3: _get_storage() with pvc entry but no backends in PVC priority
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.is_strict_backend')
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    def test_get_storage_pvc_no_backends_falls_through_when_alternatives_exist(
        self, mock_avail, mock_pvc_priority, mock_strict, mock_backends_conf
    ):
        """U-3a: pvc resolution fails with alternatives in list, falls through.

        When the priority list has entries after 'pvc', the operator declared
        acceptable fallbacks. If PVC resolution fails, _get_storage honors the
        priority-list fallback semantics and moves to the next entry.
        """
        helm = self._make_helm_instance()
        helm._priority_list = [app_constants.GLANCE_BACKEND_PVC, app_constants.GLANCE_BACKEND_CINDER]
        helm._available_backends = {
            app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
        }
        helm._migrated_pvc_priority = None

        # PVC resolution returns None when nothing resolves (fail-fast semantics)
        mock_avail.return_value = {}
        mock_pvc_priority.return_value = ['unavailable-backend']
        mock_strict.return_value = False
        mock_backends_conf.return_value = {}  # ESB backend not in backends_conf either

        backend, storage_class = helm._get_storage()
        # With alternatives declared, PVC resolution failure falls through
        # to the next priority entry (cinder).
        self.assertEqual(backend, app_constants.GLANCE_BACKEND_CINDER)
        self.assertEqual(storage_class, "")

    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.is_strict_backend')
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    def test_get_storage_pvc_only_entry_selects_pvc_with_empty_class(
        self, mock_avail, mock_pvc_priority, mock_strict, mock_backends_conf
    ):
        """U-3b: pvc is the only entry, resolution fails, selects pvc anyway.

        When 'pvc' is the sole entry in the priority list, the operator has
        no fallback intent. PVC is selected with empty storage_class so that
        get_overrides() logs an error and the pre-apply semantic check blocks
        deployment with a clear message.
        """
        helm = self._make_helm_instance()
        helm._priority_list = [app_constants.GLANCE_BACKEND_PVC]
        helm._available_backends = {}
        helm._migrated_pvc_priority = None

        # PVC resolution returns None
        mock_avail.return_value = {}
        mock_pvc_priority.return_value = ['unavailable-backend']
        mock_strict.return_value = False
        mock_backends_conf.return_value = {}

        backend, storage_class = helm._get_storage()
        # PVC is the only declared option — select it even if unresolved.
        self.assertEqual(backend, app_constants.GLANCE_BACKEND_PVC)
        self.assertEqual(storage_class, "")

    # ------------------------------------------------------------------
    # U-4: _get_storage() with legacy netapp-nfs via migration path
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.is_user_overrides_available',
                return_value=False)
    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf',
                return_value={})
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    def test_get_storage_legacy_netapp_nfs(self, mock_avail, *_):
        """U-4: Legacy netapp-nfs is migrated and resolves PVC."""
        helm = self._make_helm_instance()
        helm._priority_list = [app_constants.NETAPP_NFS_BACKEND_NAME]
        helm._migrated_pvc_priority = None
        helm._available_backends = {
            app_constants.NETAPP_NFS_BACKEND_NAME: 'netapp-nfs-sc',
            app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
        }

        # Run the migration (as get_overrides() would)
        helm._migrate_legacy_priority_list()

        # Verify migration rewrote priority list
        self.assertEqual(helm._priority_list, [app_constants.GLANCE_BACKEND_PVC])
        self.assertEqual(
            helm._migrated_pvc_priority,
            [app_constants.NETAPP_NFS_BACKEND_NAME]
        )

        # Mock PVC resolution for _get_storage()
        mock_avail.return_value = {
            app_constants.NETAPP_NFS_BACKEND_NAME: 'netapp-nfs-sc'
        }

        backend, storage_class = helm._get_storage()
        self.assertEqual(backend, app_constants.GLANCE_BACKEND_PVC)
        self.assertEqual(storage_class, 'netapp-nfs-sc')

    # ------------------------------------------------------------------
    # U-5: Ceph takes priority when available
    # ------------------------------------------------------------------
    def test_get_storage_ceph_priority(self):
        """U-5: Ceph is first priority and available — returns rbd."""
        helm = self._make_helm_instance()
        helm._priority_list = [
            app_constants.CEPH_BACKEND_NAME,
            app_constants.GLANCE_BACKEND_PVC,
            app_constants.GLANCE_BACKEND_CINDER
        ]
        helm._available_backends = {
            app_constants.CEPH_BACKEND_NAME: 'general',
            app_constants.NETAPP_NFS_BACKEND_NAME: 'netapp-nfs-sc',
            app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
        }
        helm._migrated_pvc_priority = None

        backend, storage_class = helm._get_storage()
        self.assertEqual(backend, app_constants.GLANCE_BACKEND_RBD)
        self.assertEqual(storage_class, '')

    # ------------------------------------------------------------------
    # U-6: Cinder store path
    # ------------------------------------------------------------------
    def test_get_storage_cinder(self):
        """U-6: Only cinder available — returns cinder backend."""
        helm = self._make_helm_instance()
        helm._priority_list = [app_constants.GLANCE_BACKEND_CINDER]
        helm._available_backends = {
            app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
        }
        helm._migrated_pvc_priority = None

        backend, storage_class = helm._get_storage()
        self.assertEqual(backend, app_constants.GLANCE_BACKEND_CINDER)
        self.assertEqual(storage_class, '')

    # ------------------------------------------------------------------
    # U-12: Legacy netapp-iscsi via migration path
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.is_user_overrides_available',
                return_value=False)
    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf',
                return_value={})
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    def test_get_storage_legacy_netapp_iscsi(self, mock_avail, *_):
        """U-12: Legacy netapp-iscsi is migrated and resolves PVC."""
        helm = self._make_helm_instance()
        helm._priority_list = [app_constants.NETAPP_ISCSI_BACKEND_NAME]
        helm._migrated_pvc_priority = None
        helm._available_backends = {
            app_constants.NETAPP_ISCSI_BACKEND_NAME: 'netapp-iscsi-sc',
            app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
        }

        # Run the migration
        helm._migrate_legacy_priority_list()

        self.assertEqual(helm._priority_list, [app_constants.GLANCE_BACKEND_PVC])
        self.assertEqual(
            helm._migrated_pvc_priority,
            [app_constants.NETAPP_ISCSI_BACKEND_NAME]
        )

        # Mock PVC resolution
        mock_avail.return_value = {
            app_constants.NETAPP_ISCSI_BACKEND_NAME: 'netapp-iscsi-sc'
        }

        backend, storage_class = helm._get_storage()
        self.assertEqual(backend, app_constants.GLANCE_BACKEND_PVC)
        self.assertEqual(storage_class, 'netapp-iscsi-sc')

    # ------------------------------------------------------------------
    # U-13: Legacy netapp-fc via migration path
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.is_user_overrides_available',
                return_value=False)
    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf',
                return_value={})
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    def test_get_storage_legacy_netapp_fc(self, mock_avail, *_):
        """U-13: Legacy netapp-fc is migrated and resolves PVC."""
        helm = self._make_helm_instance()
        helm._priority_list = [app_constants.NETAPP_FC_BACKEND_NAME]
        helm._migrated_pvc_priority = None
        helm._available_backends = {
            app_constants.NETAPP_FC_BACKEND_NAME: 'netapp-fc-sc',
            app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
        }

        # Run the migration
        helm._migrate_legacy_priority_list()

        self.assertEqual(helm._priority_list, [app_constants.GLANCE_BACKEND_PVC])
        self.assertEqual(
            helm._migrated_pvc_priority,
            [app_constants.NETAPP_FC_BACKEND_NAME]
        )

        # Mock PVC resolution
        mock_avail.return_value = {
            app_constants.NETAPP_FC_BACKEND_NAME: 'netapp-fc-sc'
        }

        backend, storage_class = helm._get_storage()
        self.assertEqual(backend, app_constants.GLANCE_BACKEND_PVC)
        self.assertEqual(storage_class, 'netapp-fc-sc')

    # ------------------------------------------------------------------
    # U-7: _resolve_glance_pvc_storage_class() — first not available,
    #       second available (strict backend)
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.is_strict_backend')
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    def test_resolve_pvc_storage_class_second_entry_available(
        self, mock_avail, mock_pvc_priority, mock_strict, mock_backends_conf
    ):
        """U-7: First entry not available, second strict backend resolves."""
        helm = self._make_helm_instance()
        helm._migrated_pvc_priority = None

        mock_avail.return_value = {
            app_constants.NETAPP_ISCSI_BACKEND_NAME: 'netapp-iscsi-sc',
        }
        mock_pvc_priority.return_value = [
            app_constants.NETAPP_NFS_BACKEND_NAME,
            app_constants.NETAPP_ISCSI_BACKEND_NAME,
        ]
        mock_strict.return_value = True  # All strict
        mock_backends_conf.return_value = {}

        result = helm._resolve_glance_pvc_storage_class()
        self.assertEqual(result, 'netapp-iscsi-sc')

    # ------------------------------------------------------------------
    # U-8: _resolve_glance_pvc_storage_class() — no entries available
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.is_strict_backend')
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    def test_resolve_pvc_storage_class_no_entries_returns_default(
        self, mock_avail, mock_pvc_priority, mock_strict, mock_backends_conf
    ):
        """U-8: No backends available — returns None (fail-fast semantics)."""
        helm = self._make_helm_instance()
        helm._migrated_pvc_priority = None

        mock_avail.return_value = {}
        mock_pvc_priority.return_value = [
            app_constants.NETAPP_NFS_BACKEND_NAME,
        ]
        mock_strict.return_value = True
        mock_backends_conf.return_value = {}

        result = helm._resolve_glance_pvc_storage_class()
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # U-14: _resolve_glance_pvc_storage_class() — ESB backend via
    #        get_backends_conf() fallback
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.is_strict_backend')
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    def test_resolve_pvc_storage_class_esb_via_backends_conf(
        self, mock_avail, mock_pvc_priority, mock_strict, mock_backends_conf
    ):
        """U-14: ESB backend resolves k8s_storage_class from backends_conf."""
        helm = self._make_helm_instance()
        helm._migrated_pvc_priority = None

        mock_avail.return_value = {}  # No strict backends available
        mock_pvc_priority.return_value = ['dell-powerstore-nfs']
        mock_strict.return_value = False  # ESB backend
        mock_backends_conf.return_value = {
            'dell-powerstore-nfs': {
                'k8s_storage_class': 'dell-nfs-sc',
                'protocol': 'nfs',
            }
        }

        result = helm._resolve_glance_pvc_storage_class()
        self.assertEqual(result, 'dell-nfs-sc')

    # ------------------------------------------------------------------
    # U-15: _resolve_glance_pvc_storage_class() — ESB with
    #        k8s_storage_class: none is skipped
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.is_strict_backend')
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    def test_resolve_pvc_storage_class_esb_none_skipped(
        self, mock_avail, mock_pvc_priority, mock_strict, mock_backends_conf
    ):
        """U-15: ESB backend with k8s_storage_class: none is skipped."""
        helm = self._make_helm_instance()
        helm._migrated_pvc_priority = None

        mock_avail.return_value = {}
        mock_pvc_priority.return_value = ['dell-powerstore-iscsi']
        mock_strict.return_value = False
        mock_backends_conf.return_value = {
            'dell-powerstore-iscsi': {
                'k8s_storage_class': 'none',
                'protocol': 'iscsi',
            }
        }

        result = helm._resolve_glance_pvc_storage_class()
        # Skipped because k8s_storage_class is 'none', returns None (fail-fast)
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # U-16: _resolve_glance_pvc_storage_class() — mix of strict and ESB,
    #        strict not available, ESB available
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.is_strict_backend')
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    def test_resolve_pvc_storage_class_strict_unavail_esb_available(
        self, mock_avail, mock_pvc_priority, mock_strict, mock_backends_conf
    ):
        """U-16: Strict backend not available, ESB backend resolves."""
        helm = self._make_helm_instance()
        helm._migrated_pvc_priority = None

        mock_avail.return_value = {}  # netapp-nfs not available
        mock_pvc_priority.return_value = [
            app_constants.NETAPP_NFS_BACKEND_NAME,
            'dell-powerstore-nfs',
        ]

        def strict_side_effect(name):
            return name in app_constants.STRICT_BACKEND_NAMES

        mock_strict.side_effect = strict_side_effect
        mock_backends_conf.return_value = {
            'dell-powerstore-nfs': {
                'k8s_storage_class': 'dell-nfs-sc',
                'protocol': 'nfs',
            }
        }

        result = helm._resolve_glance_pvc_storage_class()
        # netapp-nfs is strict, not in pvc_available_backends → skipped
        # dell-powerstore-nfs is ESB → resolved via backends_conf
        self.assertEqual(result, 'dell-nfs-sc')


class GlanceGenericPvcPodOverridesTest(GlanceHelmTestCase,
                                       dbbase.ControllerHostTestCase):
    """Unit tests for _get_pod_overrides() with generic PVC backend.

    Covers test plan items U-9 and U-10.
    """

    def _make_helm_instance(self):
        """Create a GlanceHelm instance for direct method testing."""
        return glance.GlanceHelm(self.operator)

    # ------------------------------------------------------------------
    # U-9: PVC backend with ReadWriteMany → normal replicas
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance._get_value_from_application')
    def test_pod_overrides_pvc_rwx_multi_replica(self, mock_get_value):
        """U-9: Generic PVC + ReadWriteMany → replicas = controllers."""
        helm = self._make_helm_instance()
        helm._backend = app_constants.GLANCE_BACKEND_PVC
        helm._storage_class = 'dell-nfs-sc'
        helm._image_store = 'file'
        helm._cinder_default_backend = None

        mock_get_value.return_value = ["ReadWriteMany"]

        overrides = helm._get_pod_overrides()
        expected_replicas = helm._num_provisioned_controllers()
        self.assertEqual(overrides['replicas']['api'], expected_replicas)

    # ------------------------------------------------------------------
    # U-10: PVC backend with ReadWriteOnce → replicas = 1
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance._get_value_from_application')
    def test_pod_overrides_pvc_rwo_single_replica(self, mock_get_value):
        """U-10: Generic PVC + ReadWriteOnce → replicas = 1."""
        helm = self._make_helm_instance()
        helm._backend = app_constants.GLANCE_BACKEND_PVC
        helm._storage_class = 'dell-iscsi-sc'
        helm._image_store = 'file'
        helm._cinder_default_backend = None

        mock_get_value.return_value = ["ReadWriteOnce"]

        overrides = helm._get_pod_overrides()
        self.assertEqual(overrides['replicas']['api'], 1)

    @mock.patch('k8sapp_openstack.helm.glance._get_value_from_application')
    def test_legacy_nfs_defaults_to_rwx(self, mock_get_value):
        """A migrated 26.03 NFS configuration preserves RWX and HA."""
        helm = self._make_helm_instance()
        helm._backend = app_constants.GLANCE_BACKEND_PVC
        helm._storage_class = 'netapp-nfs-sc'
        helm._available_backends = {
            app_constants.NETAPP_NFS_BACKEND_NAME: 'netapp-nfs-sc',
        }
        helm._migrated_pvc_priority = [
            app_constants.NETAPP_NFS_BACKEND_NAME
        ]
        helm._image_store = 'file'
        helm._cinder_default_backend = None
        mock_get_value.side_effect = (
            lambda chart_name, override_name, default_value: default_value
        )

        self.assertEqual(
            helm._get_pvc_access_modes(),
            ['ReadWriteMany'],
        )
        overrides = helm._get_pod_overrides()
        self.assertEqual(
            overrides['replicas']['api'],
            helm._num_provisioned_controllers(),
        )

    @mock.patch('k8sapp_openstack.helm.glance._get_value_from_application')
    def test_new_pvc_nfs_keeps_rwo_default(self, mock_get_value):
        """A new generic PVC configuration retains the documented default."""
        helm = self._make_helm_instance()
        helm._backend = app_constants.GLANCE_BACKEND_PVC
        helm._storage_class = 'netapp-nfs-sc'
        helm._available_backends = {
            app_constants.NETAPP_NFS_BACKEND_NAME: 'netapp-nfs-sc',
        }
        helm._migrated_pvc_priority = None
        helm._image_store = 'file'
        helm._cinder_default_backend = None
        mock_get_value.side_effect = (
            lambda chart_name, override_name, default_value: default_value
        )

        self.assertEqual(
            helm._get_pvc_access_modes(),
            ['ReadWriteOnce'],
        )
        overrides = helm._get_pod_overrides()
        self.assertEqual(overrides['replicas']['api'], 1)

    @mock.patch('k8sapp_openstack.helm.glance._get_value_from_application')
    def test_legacy_nfs_unavailable_keeps_rwo_default(self, mock_get_value):
        """A missing legacy NFS class cannot accidentally select RWX."""
        helm = self._make_helm_instance()
        helm._storage_class = None
        helm._available_backends = {
            app_constants.NETAPP_NFS_BACKEND_NAME: None,
        }
        helm._migrated_pvc_priority = [
            app_constants.NETAPP_NFS_BACKEND_NAME
        ]
        mock_get_value.side_effect = (
            lambda chart_name, override_name, default_value: default_value
        )

        self.assertEqual(
            helm._get_pvc_access_modes(),
            ['ReadWriteOnce'],
        )

    @mock.patch('k8sapp_openstack.helm.glance._get_value_from_application')
    def test_legacy_nfs_explicit_access_modes_take_precedence(
            self, mock_get_value):
        """An explicit operator access mode wins over migration defaults."""
        helm = self._make_helm_instance()
        helm._storage_class = 'netapp-nfs-sc'
        helm._available_backends = {
            app_constants.NETAPP_NFS_BACKEND_NAME: 'netapp-nfs-sc',
        }
        helm._migrated_pvc_priority = [
            app_constants.NETAPP_NFS_BACKEND_NAME
        ]
        mock_get_value.return_value = ['ReadWriteOnce']

        self.assertEqual(
            helm._get_pvc_access_modes(),
            ['ReadWriteOnce'],
        )


class GlanceGenericPvcOverridesIntegrationTest(GlanceHelmTestCase,
                                               dbbase.ControllerHostTestCase):
    """Integration test for get_overrides() with generic PVC backend.

    Covers test plan item U-11 and integration tests I-1, I-2.
    """

    # ------------------------------------------------------------------
    # U-11: get_overrides() with PVC backend — volume block has size
    #        and access_modes from overrides
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.is_user_overrides_available',
                return_value=False)
    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.is_strict_backend')
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    @mock.patch('k8sapp_openstack.helm.glance._get_value_from_application')
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_get_overrides_pvc_volume_block(
        self, mock_https, mock_get_value, mock_avail,
        mock_pvc_priority, mock_strict, mock_backends_conf,
        mock_user_overrides
    ):
        """U-11: Volume block contains correct size and access modes."""
        # Mock _get_value_from_application to return different values based on
        # the override_name parameter
        def get_value_side_effect(chart_name, override_name, default_value):
            if override_name == app_constants.OVERRIDE_STORAGE_PRIORITY:
                return [app_constants.GLANCE_BACKEND_PVC]
            elif override_name == app_constants.OVERRIDE_GLANCE_PVC_VOLUME_SIZE:
                return "5Gi"
            elif override_name == app_constants.OVERRIDE_GLANCE_PVC_VOLUME_ACCESS_MODES:
                return ["ReadWriteMany"]
            return default_value

        mock_get_value.side_effect = get_value_side_effect

        # Mock get_available_volume_backends — called twice:
        # 1. In get_overrides() for OVERRIDE_STORAGE_BACKENDS
        # 2. In _resolve_glance_pvc_storage_class() for OVERRIDE_GLANCE_PVC_STORAGE_BACKENDS
        def avail_side_effect(chart_name, override_name, **kwargs):
            if override_name == app_constants.OVERRIDE_GLANCE_PVC_STORAGE_BACKENDS:
                return {}  # No strict backends in PVC resolution
            # Main call: only cinder available at top level
            return {
                app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
            }

        mock_avail.side_effect = avail_side_effect

        mock_pvc_priority.return_value = ['dell-powerstore-nfs']
        mock_strict.return_value = False
        mock_backends_conf.return_value = {
            'dell-powerstore-nfs': {
                'k8s_storage_class': 'dell-nfs-sc',
                'protocol': 'nfs',
            }
        }

        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_GLANCE,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertIn('volume', overrides)
        self.assertEqual(overrides['volume']['class_name'], 'dell-nfs-sc')
        self.assertEqual(overrides['volume']['size'], '5Gi')
        self.assertEqual(overrides['volume']['accessModes'], ['ReadWriteMany'])
        self.assertEqual(overrides['storage'], app_constants.GLANCE_BACKEND_PVC)

    # ------------------------------------------------------------------
    # I-2: Full override generation with legacy netapp-nfs (upgrade)
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.is_user_overrides_available',
                return_value=False)
    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf',
                return_value={})
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list',
                return_value=[app_constants.NETAPP_NFS_BACKEND_NAME])
    @mock.patch('k8sapp_openstack.helm.glance._get_value_from_application')
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_get_overrides_legacy_netapp_nfs_upgrade(
        self, mock_https, mock_avail, mock_get_value, *_
    ):
        """I-2: Legacy netapp-nfs config produces PVC overrides with RWX."""
        def get_value_side_effect(chart_name, override_name, default_value):
            if override_name == app_constants.OVERRIDE_STORAGE_PRIORITY:
                return [app_constants.NETAPP_NFS_BACKEND_NAME]
            elif override_name == app_constants.OVERRIDE_GLANCE_PVC_VOLUME_SIZE:
                return app_constants.DEFAULT_GLANCE_PVC_VOLUME_SIZE
            return default_value

        mock_get_value.side_effect = get_value_side_effect
        mock_avail.return_value = {
            app_constants.NETAPP_NFS_BACKEND_NAME: 'netapp-nfs-sc',
            app_constants.NETAPP_ISCSI_BACKEND_NAME: '',
            app_constants.NETAPP_FC_BACKEND_NAME: '',
            app_constants.GLANCE_BACKEND_CINDER: app_constants.GLANCE_BACKEND_CINDER,
        }

        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_GLANCE,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertEqual(overrides['storage'], app_constants.GLANCE_BACKEND_PVC)
        self.assertIn('volume', overrides)
        self.assertEqual(overrides['volume']['class_name'], 'netapp-nfs-sc')
        # Migration preserves the legacy NFS RWX default without a new
        # operator override.
        self.assertEqual(overrides['volume']['accessModes'], ['ReadWriteMany'])
        self.assertEqual(
            overrides['pod']['replicas']['api'],
            self.operator.chart_operators[
                app_constants.HELM_CHART_GLANCE
            ]._num_provisioned_controllers(),
        )


class GlanceMigrationTest(GlanceHelmTestCase,
                          dbbase.ControllerHostTestCase):
    """Unit tests for _migrate_legacy_priority_list() edge cases.

    Covers test plan items U-17 through U-20.
    """

    def _make_helm_instance(self):
        """Create a GlanceHelm instance for direct method testing."""
        return glance.GlanceHelm(self.operator)

    # ------------------------------------------------------------------
    # U-17: Full multi-entry migration
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.is_user_overrides_available',
                return_value=False)
    def test_migrate_legacy_full_priority_list(self, *_):
        """U-17: [ceph, netapp-nfs, netapp-iscsi, netapp-fc, cinder] migrates
        to [ceph, pvc, cinder] with all three as PVC sub-priority."""
        helm = self._make_helm_instance()
        helm._priority_list = [
            app_constants.CEPH_BACKEND_NAME,
            app_constants.NETAPP_NFS_BACKEND_NAME,
            app_constants.NETAPP_ISCSI_BACKEND_NAME,
            app_constants.NETAPP_FC_BACKEND_NAME,
            app_constants.GLANCE_BACKEND_CINDER,
        ]
        helm._migrated_pvc_priority = None

        helm._migrate_legacy_priority_list()

        self.assertEqual(helm._priority_list, [
            app_constants.CEPH_BACKEND_NAME,
            app_constants.GLANCE_BACKEND_PVC,
            app_constants.GLANCE_BACKEND_CINDER,
        ])
        self.assertEqual(helm._migrated_pvc_priority, [
            app_constants.NETAPP_NFS_BACKEND_NAME,
            app_constants.NETAPP_ISCSI_BACKEND_NAME,
            app_constants.NETAPP_FC_BACKEND_NAME,
        ])

    # ------------------------------------------------------------------
    # U-18: Migration respects explicit operator PVC priority
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.is_user_overrides_available',
                return_value=True)
    def test_migrate_legacy_respects_explicit_pvc_priority(self, *_):
        """U-18: When operator explicitly sets pvc.storage_class_priority,
        migration rewrites the top-level list but does NOT override
        _migrated_pvc_priority — operator's explicit config wins."""
        helm = self._make_helm_instance()
        helm._priority_list = [
            app_constants.NETAPP_NFS_BACKEND_NAME,
            app_constants.GLANCE_BACKEND_CINDER,
        ]
        helm._migrated_pvc_priority = None

        helm._migrate_legacy_priority_list()

        # Top-level list IS rewritten
        self.assertEqual(helm._priority_list, [
            app_constants.GLANCE_BACKEND_PVC,
            app_constants.GLANCE_BACKEND_CINDER,
        ])
        # But _migrated_pvc_priority is NOT set — operator's config wins
        self.assertIsNone(helm._migrated_pvc_priority)

    # ------------------------------------------------------------------
    # U-19: No migration for new schema
    # ------------------------------------------------------------------
    def test_migrate_legacy_no_op_for_new_schema(self):
        """U-19: [ceph, pvc, cinder] triggers no migration."""
        helm = self._make_helm_instance()
        helm._priority_list = [
            app_constants.CEPH_BACKEND_NAME,
            app_constants.GLANCE_BACKEND_PVC,
            app_constants.GLANCE_BACKEND_CINDER,
        ]
        helm._migrated_pvc_priority = None

        helm._migrate_legacy_priority_list()

        # Unchanged
        self.assertEqual(helm._priority_list, [
            app_constants.CEPH_BACKEND_NAME,
            app_constants.GLANCE_BACKEND_PVC,
            app_constants.GLANCE_BACKEND_CINDER,
        ])
        self.assertIsNone(helm._migrated_pvc_priority)

    # ------------------------------------------------------------------
    # U-20: _resolve_glance_pvc_storage_class uses migrated priority
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.helm.glance.get_backends_conf',
                return_value={})
    @mock.patch('k8sapp_openstack.utils.is_strict_backend',
                return_value=True)
    @mock.patch('k8sapp_openstack.helm.glance.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.helm.glance.get_available_volume_backends')
    def test_resolve_pvc_uses_migrated_priority_list(
        self, mock_avail, mock_pvc_priority, *_
    ):
        """U-20: When _migrated_pvc_priority is set, resolution uses it
        directly and does NOT call get_storage_backends_priority_list."""
        helm = self._make_helm_instance()
        helm._migrated_pvc_priority = [
            app_constants.NETAPP_NFS_BACKEND_NAME,
            app_constants.NETAPP_ISCSI_BACKEND_NAME,
        ]

        mock_avail.return_value = {
            app_constants.NETAPP_NFS_BACKEND_NAME: 'netapp-nfs-sc',
            app_constants.NETAPP_ISCSI_BACKEND_NAME: 'netapp-iscsi-sc',
        }

        result = helm._resolve_glance_pvc_storage_class()

        self.assertEqual(result, 'netapp-nfs-sc')
        # get_storage_backends_priority_list must NOT have been called
        mock_pvc_priority.assert_not_called()
