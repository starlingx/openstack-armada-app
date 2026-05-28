#
# Copyright (c) 2022-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import os
import shutil
import tempfile

import mock
from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm import common
from sysinv.helm.lifecycle_constants import LifecycleConstants
from sysinv.tests import base
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.lifecycle import lifecycle_openstack


EXTENDED_VSWITCH_ALLOWED_COMBINATIONS = (app_constants.VSWITCH_ALLOWED_COMBINATIONS +
                                        [{"other-vswitch=enabled"}])

# Side effects post_apply triggers that are irrelevant to playbook delivery.
_LIFECYCLE_MOD = 'k8sapp_openstack.lifecycle.lifecycle_openstack'
_DEX_REDIRECT = _LIFECYCLE_MOD + '.post_apply_update_dex_redirect_uri'
_RECOVER_SERVERS = _LIFECYCLE_MOD + '.app_utils.recover_error_servers'


class OpenstackAppLifecycleOperatorTest(dbbase.BaseHostTestCase):
    def setUp(self):
        super(OpenstackAppLifecycleOperatorTest, self).setUp()
        self.lifecycle = lifecycle_openstack.OpenstackAppLifecycleOperator()

    def _rook_ceph_backend_available(self, ceph_type: str =
                                     constants.SB_TYPE_CEPH):
        return ceph_type == constants.SB_TYPE_CEPH_ROOK, ""

    def _ceph_backend_available(self, ceph_type: str =
                                     constants.SB_TYPE_CEPH):
        return ceph_type == constants.SB_TYPE_CEPH, ""

    @mock.patch('k8sapp_openstack.utils.check_netapp_backends',
                return_value={app_constants.NETAPP_NFS_BACKEND_NAME: False,
                              app_constants.NETAPP_ISCSI_BACKEND_NAME: False,
                              app_constants.NETAPP_FC_BACKEND_NAME: False})
    @mock.patch('k8sapp_openstack.utils.is_rook_ceph_api_available',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils.get_ceph_fsid',
                return_value='aa8c8da0-47de-4fad-8b5d-2c06be236fc8')
    @mock.patch('k8sapp_openstack.utils.is_ceph_backend_available')
    def test_is_strict_backend_available_rook(
        self,
        mock_is_ceph_backend_available,
        mock_get_ceph_fsid,
        mock_is_rook_ceph_api_available,
        mock_check_netapp_backends
    ):
        """ Test _is_strict_backend_available for rook ceph backend, api and
        fsid available.
        """
        mock_is_ceph_backend_available.side_effect = \
            self._rook_ceph_backend_available
        available, _ = self.lifecycle._is_strict_backend_available()
        self.assertTrue(available)
        mock_is_ceph_backend_available.assert_called()
        mock_check_netapp_backends.assert_called()
        mock_get_ceph_fsid.assert_called()
        mock_is_rook_ceph_api_available.assert_called()

    @mock.patch('k8sapp_openstack.utils.check_netapp_backends',
                return_value={app_constants.NETAPP_NFS_BACKEND_NAME: False,
                              app_constants.NETAPP_ISCSI_BACKEND_NAME: False,
                              app_constants.NETAPP_FC_BACKEND_NAME: False})
    @mock.patch('k8sapp_openstack.utils.get_ceph_fsid',
                return_value='aa8c8da0-47de-4fad-8b5d-2c06be236fc8')
    @mock.patch('k8sapp_openstack.utils.is_ceph_backend_available')
    def test_is_strict_backend_available_ceph(
        self,
        mock_is_ceph_backend_available,
        mock_get_ceph_fsid,
        mock_check_netapp_backends
    ):
        """ Test _is_strict_backend_available for host ceph backend and fsid
        available.
        """
        mock_is_ceph_backend_available.side_effect = \
            self._ceph_backend_available
        available, _ = self.lifecycle._is_strict_backend_available()
        self.assertTrue(available)
        mock_is_ceph_backend_available.assert_called()
        mock_check_netapp_backends.assert_called()
        mock_get_ceph_fsid.assert_called()

    @mock.patch('k8sapp_openstack.utils.check_netapp_backends',
                return_value={app_constants.NETAPP_NFS_BACKEND_NAME: True,
                              app_constants.NETAPP_ISCSI_BACKEND_NAME: False,
                              app_constants.NETAPP_FC_BACKEND_NAME: False})
    @mock.patch('k8sapp_openstack.utils.get_ceph_fsid', return_value=None)
    @mock.patch('k8sapp_openstack.utils.is_ceph_backend_available')
    def test_is_strict_backend_available_netapp_nfs(
        self,
        mock_is_ceph_backend_available,
        mock_get_ceph_fsid,
        mock_check_netapp_backends,
    ):
        """ Test _is_strict_backend_available for netapp nfs backend available.
        """
        mock_is_ceph_backend_available.side_effect = \
            self._ceph_backend_available
        available, _ = self.lifecycle._is_strict_backend_available()
        self.assertTrue(available)
        mock_is_ceph_backend_available.assert_called()
        mock_check_netapp_backends.assert_called()
        mock_get_ceph_fsid.assert_called()

    @mock.patch('k8sapp_openstack.utils.get_backends_conf', return_value={})
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override',
                return_value=[])
    @mock.patch('k8sapp_openstack.utils.check_netapp_backends',
                return_value={app_constants.NETAPP_NFS_BACKEND_NAME: False,
                              app_constants.NETAPP_ISCSI_BACKEND_NAME: False,
                              app_constants.NETAPP_FC_BACKEND_NAME: False})
    @mock.patch('k8sapp_openstack.utils.get_ceph_fsid', return_value=None)
    @mock.patch('k8sapp_openstack.utils.is_ceph_backend_available')
    def test_semantic_check_storage_backend_available_fsid_unavailable(
        self,
        mock_is_ceph_backend_available,
        mock_get_ceph_fsid,
        mock_check_netapp_backends,
        mock_get_enabled_backends,
        mock_get_backends_conf,
    ):
        """ Test that apply is blocked when host ceph is available but fsid is
        unavailable and there is no ESB backend.
        """
        mock_is_ceph_backend_available.side_effect = \
            self._ceph_backend_available
        strict_available, status = \
            self.lifecycle._is_strict_backend_available()
        self.assertFalse(strict_available)
        self.assertRaises(
            exception.LifecycleSemanticCheckException,
            self.lifecycle._semantic_check_storage_backend_available,
            strict_available, status)
        mock_get_ceph_fsid.assert_called()
        mock_check_netapp_backends.assert_called()

    @mock.patch('k8sapp_openstack.utils.get_backends_conf', return_value={})
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override',
                return_value=[])
    @mock.patch('k8sapp_openstack.utils.check_netapp_backends',
                return_value={app_constants.NETAPP_NFS_BACKEND_NAME: False,
                              app_constants.NETAPP_ISCSI_BACKEND_NAME: False,
                              app_constants.NETAPP_FC_BACKEND_NAME: False})
    @mock.patch('k8sapp_openstack.utils.get_ceph_fsid', return_value=None)
    @mock.patch('k8sapp_openstack.utils.is_ceph_backend_available',
                side_effect=[(False, ""), (False, "")])
    def test_semantic_check_storage_backend_available_no_backends(
        self,
        mock_is_ceph_backend_available,
        mock_get_ceph_fsid,
        mock_check_netapp_backends,
        mock_get_enabled_backends,
        mock_get_backends_conf,
    ):
        """ Test that apply is blocked when no strict backend and no ESB
        backend are available.
        """
        strict_available, status = \
            self.lifecycle._is_strict_backend_available()
        self.assertFalse(strict_available)
        self.assertRaises(
            exception.LifecycleSemanticCheckException,
            self.lifecycle._semantic_check_storage_backend_available,
            strict_available, status)

    @mock.patch("k8sapp_openstack.utils.get_server_list")
    def test_semantic_check_openstack_vms_created_no_servers(self, mock_get_server_list):
        """ Test _semantic_check_openstack_vms_created for no servers
        """
        mock_get_server_list.return_value = []

        try:
            self.lifecycle._semantic_check_openstack_vms_created()
        except exception.LifecycleSemanticCheckException as e:
            self.fail(f"Unexpected LifecycleSemanticCheckException raised: {e}")

        mock_get_server_list.assert_called_once()

    @mock.patch("k8sapp_openstack.utils.get_server_list")
    def test_semantic_check_openstack_vms_created_with_servers(self, mock_get_server_list):
        """ Test _semantic_check_openstack_vms_created for with servers
        """
        mock_get_server_list.return_value = ["server1"]

        self.assertRaises(
            exception.LifecycleSemanticCheckException,
            self.lifecycle._semantic_check_openstack_vms_created
        )

        mock_get_server_list.assert_called_once()

    _MARIADB_CHART_VERSION_BY_APP = {
        '25.03-0': '0.2.43',
        '25.09-0': '2025.1.0',
    }

    @staticmethod
    def _make_recovery_app(from_version='25.03-0', to_version='25.09-0'):
        app = mock.MagicMock()
        app.name = 'stx-openstack'
        app.version = to_version
        app.sync_imgfile = (
            f"/opt/platform/fluxcd/<stx version>/{app.name}/"
            f"{from_version}/{app.name}-images.yaml"
        )
        return app

    @mock.patch('k8sapp_openstack.utils.force_app_reconciliation')
    @mock.patch('k8sapp_openstack.utils.delete_kubernetes_resource')
    @mock.patch('k8sapp_openstack.utils.get_mariadb_chart_version')
    @mock.patch('k8sapp_openstack.utils.get_app_version_list',
                return_value=['25.03-0', '25.09-0'])
    def test__recover_app_resources_failed_update_version_changed(
        self,
        mock_get_app_version_list,
        mock_get_mariadb_chart_version,
        mock_delete_kubernetes_resource,
        mock_force_app_reconciliation
    ):
        """Chart version changed: MariaDB HelmRelease is deleted and excluded
        from the forced reconciliation.
        """
        mock_get_mariadb_chart_version.side_effect = (
            lambda name, version: self._MARIADB_CHART_VERSION_BY_APP[version]
        )

        app_op = mock.MagicMock()
        app = self._make_recovery_app()

        self.lifecycle._recover_app_resources_failed_update(app_op, app)

        app_op._deregister_app_abort.assert_called_once_with(app.name)
        mock_get_app_version_list.assert_called_once()
        mock_delete_kubernetes_resource.assert_called_once_with(
            resource_type='helmrelease',
            resource_name='mariadb'
        )
        mock_force_app_reconciliation.assert_called_once_with(
            app_op, app, exclude_charts=['mariadb']
        )

    @mock.patch('k8sapp_openstack.utils.force_app_reconciliation')
    @mock.patch('k8sapp_openstack.utils.delete_kubernetes_resource')
    @mock.patch('k8sapp_openstack.utils.get_mariadb_chart_version')
    @mock.patch('k8sapp_openstack.utils.get_app_version_list',
                return_value=['25.03-0', '25.09-0'])
    def test__recover_app_resources_failed_update_version_unchanged(
        self,
        mock_get_app_version_list,
        mock_get_mariadb_chart_version,
        mock_delete_kubernetes_resource,
        mock_force_app_reconciliation
    ):
        """Chart version unchanged: MariaDB HelmRelease is not deleted."""
        mock_get_mariadb_chart_version.return_value = '2025.1.0'

        app_op = mock.MagicMock()
        app = self._make_recovery_app()

        self.lifecycle._recover_app_resources_failed_update(app_op, app)

        app_op._deregister_app_abort.assert_called_once_with(app.name)
        mock_get_app_version_list.assert_called_once()
        mock_delete_kubernetes_resource.assert_not_called()
        mock_force_app_reconciliation.assert_called_once_with(
            app_op, app, exclude_charts=None
        )

    @mock.patch('k8sapp_openstack.utils.force_app_reconciliation')
    @mock.patch('k8sapp_openstack.utils.delete_kubernetes_resource')
    @mock.patch('k8sapp_openstack.utils.get_mariadb_chart_version')
    @mock.patch('k8sapp_openstack.utils.get_app_version_list',
                return_value=['25.03-0', '25.09-0'])
    def test__recover_app_resources_failed_update_version_unknown(
        self,
        mock_get_app_version_list,
        mock_get_mariadb_chart_version,
        mock_delete_kubernetes_resource,
        mock_force_app_reconciliation
    ):
        """Chart version undeterminable: MariaDB HelmRelease is not deleted."""
        mock_get_mariadb_chart_version.side_effect = (
            lambda name, version: None if version == '25.03-0' else '2025.1.0'
        )

        app_op = mock.MagicMock()
        app = self._make_recovery_app()

        self.lifecycle._recover_app_resources_failed_update(app_op, app)

        mock_delete_kubernetes_resource.assert_not_called()
        mock_force_app_reconciliation.assert_called_once_with(
            app_op, app, exclude_charts=None
        )

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.post_apply_update_dex_redirect_uri')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.app_utils')
    def test__post_apply(self, mock_app_utils, mock_post_apply_dex, *_):
        context = mock.Mock()
        conductor_obj = mock.Mock()
        hook_info = {
            LifecycleConstants.EXTRA: {
                LifecycleConstants.APP_APPLIED: True,
                self.lifecycle.WAS_APPLIED: False,
            }
        }

        PVC_PREFIX = 'mysql-data-mariadb-server'
        SNAPSHOT_NAME_PREFIX = 'snapshot-of'

        number_of_controllers = 2
        calls = []
        for i in range(0, number_of_controllers):
            pvc_name = f"{PVC_PREFIX}-{i}"
            snapshot_name = f"{SNAPSHOT_NAME_PREFIX}-{pvc_name}"
            calls.append(mock.call(snapshot_name, ignore_not_found=True))

        mock_app_utils.get_number_of_controllers.return_value = number_of_controllers

        self.lifecycle.post_apply(context, conductor_obj, None, hook_info)

        conductor_obj._update_config_for_stx_openstack.assert_called_once_with(context)
        conductor_obj._update_radosgw_config.assert_called_once_with(context)
        mock_post_apply_dex.assert_called_once_with(
            context, conductor_obj
        )

        mock_app_utils.delete_snapshot.assert_has_calls(calls)

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.post_apply_update_dex_redirect_uri')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.app_utils')
    def test__post_apply_dex_redirect_failure_does_not_fail_apply(
            self, mock_app_utils, mock_post_apply_dex, *_):
        """Test that post_apply continues even if DEX redirect URI update fails."""
        context = mock.Mock()
        conductor_obj = mock.Mock()
        hook_info = {
            LifecycleConstants.EXTRA: {
                LifecycleConstants.APP_APPLIED: True,
                self.lifecycle.WAS_APPLIED: False,
            }
        }

        mock_app_utils.get_number_of_controllers.return_value = 1
        mock_post_apply_dex.side_effect = Exception("DEX error")

        # Should not raise exception
        self.lifecycle.post_apply(context, conductor_obj, None, hook_info)

        conductor_obj._update_config_for_stx_openstack.assert_called_once_with(context)
        conductor_obj._update_radosgw_config.assert_called_once_with(context)

    @mock.patch('k8sapp_openstack.utils.get_app_version_list',
                return_value=['25.03-0', '25.09-0'])
    def test__pre_update_actions_update_op(self, *_):
        """Test __pre_update_actions for the app update operation
        """
        app = mock.MagicMock()
        app.name = 'stx-openstack'
        app.sync_imgfile = ("/opt/platform/fluxcd/<stx version>/stx-openstack/"
                            "25.03-0/stx-openstack-images.yaml")
        self.lifecycle._pre_update_backup_actions = mock.Mock()
        self.lifecycle._pre_update_cleanup_actions = mock.Mock()

        self.lifecycle._pre_update_actions(app)

        self.lifecycle._pre_update_backup_actions.assert_called_once_with(app)
        self.lifecycle._pre_update_cleanup_actions.assert_called_once()

    @mock.patch('k8sapp_openstack.utils.get_app_version_list',
                return_value=['25.03-0'])
    def test__pre_update_actions_apply_op(self, *_):
        """Test __pre_update_actions for the app apply operation
        """
        app = mock.MagicMock()
        app.name = 'stx-openstack'
        app.sync_imgfile = ("/opt/platform/fluxcd/<stx version>/stx-openstack/"
                            "25.03-0/stx-openstack-images.yaml")
        self.lifecycle._pre_update_backup_actions = mock.Mock()
        self.lifecycle._pre_update_cleanup_actions = mock.Mock()

        self.lifecycle._pre_update_actions(app)

        self.lifecycle._pre_update_backup_actions.assert_not_called()
        self.lifecycle._pre_update_cleanup_actions.assert_not_called()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.app_utils')
    def test__pre_update_backup_actions(self, mock_app_utils, *_):
        app = mock.Mock(inst_path='test_path')

        number_of_controllers = 2

        PVC_PREFIX = 'mysql-data-mariadb-server'
        SNAPSHOT_NAME_PREFIX = 'snapshot-of'
        SNAPSHOT_CLASS_NAME = "rbd-snapshot"

        calls = []
        for i in range(0, number_of_controllers):
            pvc_name = f"{PVC_PREFIX}-{i}"
            snapshot_name = f"{SNAPSHOT_NAME_PREFIX}-{pvc_name}"
            calls.append(mock.call(snapshot_name, pvc_name, SNAPSHOT_CLASS_NAME, path=app.inst_path))

        mock_app_utils.get_number_of_controllers.return_value = number_of_controllers

        self.lifecycle._pre_update_backup_actions(app)

        mock_app_utils.create_pvc_snapshot.assert_has_calls(calls)

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.app_utils')
    def test__recover_backup_snapshot(self, mock_app_utils, *_):
        app = mock.Mock(inst_path='test_path')

        number_of_controllers = 2

        PVC_PREFIX = 'mysql-data-mariadb-server'
        SNAPSHOT_NAME_PREFIX = 'snapshot-of'
        STATEFULSET_NAME = 'mariadb-server'

        calls = []
        for i in range(0, number_of_controllers):
            pvc_name = f"{PVC_PREFIX}-{i}"
            snapshot_name = f"{SNAPSHOT_NAME_PREFIX}-{pvc_name}"
            calls.append(mock.call(snapshot_name, pvc_name, STATEFULSET_NAME, path=app.inst_path))

        mock_app_utils.get_number_of_controllers.return_value = number_of_controllers

        self.lifecycle._recover_backup_snapshot(app)

        mock_app_utils.restore_pvc_snapshot.assert_has_calls(calls)

    def test__recover_actions(self, *_):
        """Test _recover_actions
        """
        app = mock.Mock()
        app.version = 'FAILED_VERSION'
        app_op = mock.Mock()

        hook_info = {
            LifecycleConstants.EXTRA: {
                LifecycleConstants.FROM_APP_VERSION: 'FAILED_VERSION',
            }
        }

        self.lifecycle._recover_backup_snapshot = mock.Mock()
        self.lifecycle._recover_app_resources_failed_update = mock.Mock()
        self.lifecycle._undeploy_ansible = mock.Mock()

        self.lifecycle._recover_actions(app_op, app, hook_info)

        self.lifecycle._recover_backup_snapshot.assert_called_once_with(app)
        self.lifecycle._recover_app_resources_failed_update.\
            assert_called_once_with(app_op, app)

    def test__recover_actions_undeploys_failed_version(self, *_):
        """The dispatch carrying the failed version retires its playbooks."""
        app = mock.Mock()
        app.name = 'stx-openstack'
        app.version = 'FAILED_VERSION'
        app_op = mock.Mock()

        hook_info = {
            LifecycleConstants.EXTRA: {
                LifecycleConstants.FROM_APP_VERSION: 'FAILED_VERSION',
            }
        }

        self.lifecycle._recover_backup_snapshot = mock.Mock()
        self.lifecycle._recover_app_resources_failed_update = mock.Mock()
        self.lifecycle._undeploy_ansible = mock.Mock()

        self.lifecycle._recover_actions(app_op, app, hook_info)

        self.lifecycle._undeploy_ansible.assert_called_once_with(app)

    def test__recover_actions_skips_undeploy_for_recovered_version(self, *_):
        """The second dispatch must not retire the recovered version.

        sysinv raises the recover hook again once recovery has completed, that
        time carrying the version that was restored. Undeploying then would
        delete the tree that was just recovered to.
        """
        app = mock.Mock()
        app.name = 'stx-openstack'
        app.version = 'RECOVERED_VERSION'
        app_op = mock.Mock()

        hook_info = {
            LifecycleConstants.EXTRA: {
                LifecycleConstants.FROM_APP_VERSION: 'FAILED_VERSION',
            }
        }

        self.lifecycle._recover_backup_snapshot = mock.Mock()
        self.lifecycle._recover_app_resources_failed_update = mock.Mock()
        self.lifecycle._undeploy_ansible = mock.Mock()

        self.lifecycle._recover_actions(app_op, app, hook_info)

        self.lifecycle._undeploy_ansible.assert_not_called()

    def test__is_failed_update_version_missing_payload(self, *_):
        """A hook with no FROM_APP_VERSION is treated as the failed version."""
        app = mock.Mock()
        app.version = 'SOME_VERSION'

        self.assertTrue(
            self.lifecycle._is_failed_update_version(app, {}))
        self.assertTrue(
            self.lifecycle._is_failed_update_version(
                app, {LifecycleConstants.EXTRA: {}}))
        self.assertTrue(
            self.lifecycle._is_failed_update_version(app, None))

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.lifecycle_utils')
    def test__app_lifecycle_actions(self, mock_lifecycle_utils, *_):
        app = mock.Mock()
        app.name = 'test'

        self.lifecycle.pre_apply = mock.Mock()
        self.lifecycle.post_apply = mock.Mock()
        self.lifecycle.pre_remove = mock.Mock()
        self.lifecycle.post_remove = mock.Mock()

        self.lifecycle._create_app_specific_resources_pre_apply = mock.Mock()
        self.lifecycle._delete_app_specific_resources_post_remove = mock.Mock()
        self.lifecycle._recover_actions = mock.Mock()

        self.lifecycle._semantic_check_evaluate_app_reapply = mock.Mock()
        self.lifecycle._pre_apply_check = mock.Mock()
        self.lifecycle._pre_remove_check = mock.Mock()

        self.lifecycle._pre_update_actions = mock.Mock()
        self.lifecycle._post_update_image_actions = mock.Mock()
        self.lifecycle.post_apply_manifest = mock.Mock()

        mocked_methods = [
            self.lifecycle.pre_apply,
            self.lifecycle.post_apply,
            self.lifecycle.post_apply_manifest,
            self.lifecycle.pre_remove,
            self.lifecycle.post_remove,
            self.lifecycle._create_app_specific_resources_pre_apply,
            self.lifecycle._delete_app_specific_resources_post_remove,
            self.lifecycle._recover_actions,
            self.lifecycle._semantic_check_evaluate_app_reapply,
            self.lifecycle._pre_apply_check,
            self.lifecycle._pre_remove_check,
            self.lifecycle._pre_update_actions,
            self.lifecycle._post_update_image_actions,
        ]

        operation_cases = [
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_OPERATION,
                    operation=constants.APP_APPLY_OP,
                    relative_timing=LifecycleConstants.APP_LIFECYCLE_TIMING_PRE,
                ),
                'assertions': [
                    self.lifecycle.pre_apply.assert_called_once,
                    self.lifecycle.post_apply.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_OPERATION,
                    operation=constants.APP_APPLY_OP,
                    relative_timing=LifecycleConstants.APP_LIFECYCLE_TIMING_POST,
                ),
                'assertions': [
                    self.lifecycle.pre_apply.assert_not_called,
                    self.lifecycle.post_apply.assert_called_once,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_OPERATION,
                    operation=constants.APP_REMOVE_OP,
                    relative_timing=LifecycleConstants.APP_LIFECYCLE_TIMING_PRE,
                ),
                'assertions': [
                    self.lifecycle.pre_remove.assert_called,
                    self.lifecycle.post_remove.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_OPERATION,
                    operation=constants.APP_REMOVE_OP,
                    relative_timing=LifecycleConstants.APP_LIFECYCLE_TIMING_POST,
                ),
                'assertions': [
                    self.lifecycle.pre_remove.assert_not_called,
                    self.lifecycle.post_remove.assert_called_once,
                ]
            },
        ]

        resource_cases = [
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_RESOURCE,
                    operation=constants.APP_APPLY_OP,
                    relative_timing=LifecycleConstants.APP_LIFECYCLE_TIMING_PRE,
                ),
                'assertions': [
                    self.lifecycle._create_app_specific_resources_pre_apply.assert_called_once,
                    self.lifecycle._delete_app_specific_resources_post_remove.assert_not_called,
                    self.lifecycle._recover_actions.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_RESOURCE,
                    operation=constants.APP_REMOVE_OP,
                    relative_timing=LifecycleConstants.APP_LIFECYCLE_TIMING_POST,
                ),
                'assertions': [
                    self.lifecycle._create_app_specific_resources_pre_apply.assert_not_called,
                    self.lifecycle._delete_app_specific_resources_post_remove.assert_called_once,
                    self.lifecycle._recover_actions.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_RESOURCE,
                    operation=constants.APP_RECOVER_OP,
                ),
                'assertions': [
                    self.lifecycle._create_app_specific_resources_pre_apply.assert_not_called,
                    self.lifecycle._delete_app_specific_resources_post_remove.assert_not_called,
                    self.lifecycle._recover_actions.assert_called_once,
                ]
            },
        ]

        semantic_cases = [
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_SEMANTIC_CHECK,
                    operation=constants.APP_EVALUATE_REAPPLY_OP,
                    mode=LifecycleConstants.APP_LIFECYCLE_MODE_AUTO,
                ),
                'assertions': [
                    self.lifecycle._semantic_check_evaluate_app_reapply.assert_called_once,
                    self.lifecycle._pre_apply_check.assert_not_called,
                    self.lifecycle._pre_remove_check.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_SEMANTIC_CHECK,
                    operation=constants.APP_APPLY_OP,
                    mode=LifecycleConstants.APP_LIFECYCLE_MODE_AUTO,
                    relative_timing=LifecycleConstants.APP_LIFECYCLE_TIMING_PRE,
                ),
                'assertions': [
                    self.lifecycle._semantic_check_evaluate_app_reapply.assert_not_called,
                    self.lifecycle._pre_apply_check.assert_called_once,
                    self.lifecycle._pre_remove_check.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_SEMANTIC_CHECK,
                    operation=constants.APP_APPLY_OP,
                    mode=LifecycleConstants.APP_LIFECYCLE_MODE_MANUAL,
                    relative_timing=LifecycleConstants.APP_LIFECYCLE_TIMING_PRE,
                ),
                'assertions': [
                    self.lifecycle._semantic_check_evaluate_app_reapply.assert_not_called,
                    self.lifecycle._pre_apply_check.assert_called_once,
                    self.lifecycle._pre_remove_check.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_SEMANTIC_CHECK,
                    operation=constants.APP_REMOVE_OP,
                    mode=LifecycleConstants.APP_LIFECYCLE_MODE_MANUAL,
                    relative_timing=LifecycleConstants.APP_LIFECYCLE_TIMING_PRE,
                ),
                'assertions': [
                    self.lifecycle._semantic_check_evaluate_app_reapply.assert_not_called,
                    self.lifecycle._pre_apply_check.assert_not_called,
                    self.lifecycle._pre_remove_check.assert_called_once,
                ]
            },
        ]

        manifest_cases = [
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_MANIFEST,
                    operation=constants.APP_APPLY_OP,
                    relative_timing=LifecycleConstants.APP_LIFECYCLE_TIMING_PRE,
                ),
                'assertions': [
                    self.lifecycle._pre_update_actions.assert_called,
                    self.lifecycle.post_apply_manifest.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_MANIFEST,
                    operation=constants.APP_APPLY_OP,
                    relative_timing=LifecycleConstants.APP_LIFECYCLE_TIMING_POST,
                ),
                'assertions': [
                    self.lifecycle._pre_update_actions.assert_not_called,
                    self.lifecycle.post_apply_manifest.assert_called,
                ]
            },
        ]

        cases = operation_cases + resource_cases + semantic_cases + manifest_cases

        for case in cases:
            hook_info = case['hook_info']
            self.lifecycle.app_lifecycle_actions(None, 'conductor_obj_test', None, app, hook_info)

            for assertion in case['assertions']:
                assertion()

            for mocked_method in mocked_methods:
                mocked_method.reset_mock()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.app_utils')
    def test__post_update_image_actions(self, mock_app_utils, *_):
        app = mock.Mock(
            sync_imgfile='sample_name_test',
        )
        app.name = 'name'

        mocked_methods = [
            mock_app_utils.get_residual_images,
            mock_app_utils.delete_residual_images,
        ]

        cases = [
            {
                'version_list': [],
                'residual_images': [],
                'assertions': [
                    mock_app_utils.get_residual_images.assert_not_called,
                    mock_app_utils.delete_residual_images.assert_not_called,
                ]
            },
            {
                'version_list': ['1.1', '2.0'],
                'residual_images': [],
                'assertions': [
                    mock_app_utils.get_residual_images.assert_called_once,
                    mock_app_utils.delete_residual_images.assert_not_called,
                ]
            },
            {
                'version_list': ['1.1', '2.0'],
                'residual_images': ['test'],
                'assertions': [
                    mock_app_utils.get_residual_images.assert_called_once,
                    mock_app_utils.delete_residual_images.assert_called_once
                ]
            },
        ]

        for case in cases:
            mock_app_utils.get_app_version_list.return_value = case['version_list']
            mock_app_utils.get_residual_images.return_value = case['residual_images']

            self.lifecycle._post_update_image_actions(app)

            for assertion in case['assertions']:
                assertion()

            for mocked_method in mocked_methods:
                mocked_method.reset_mock()

    def _create_hosts_and_labels(self, host_cfgs):
        last_octet = 0
        for name, config in host_cfgs.items():
            subfunctions = [config["personality"]]
            if subfunction := config.get("subfunction", None):  # noqa: E225,E231,E701,E999
                subfunctions.append(subfunction)
            host = dbutils.create_test_ihost(
                uuid=None,
                forisystemid=self.system.id,
                hostname=name,
                personality=config["personality"],
                subfunctions=','.join(subfunctions),
                invprovision=config.get("invprovision", constants.PROVISIONED),
                mgmt_mac=f"1E:AA:03:4F:C0:{last_octet:02x}"
            )
            for label_key, label_value in config.get("labels", dict()).items():
                self.dbapi.label_create(host.uuid, {"host_id": host.id,
                                                    "label_key": label_key,
                                                    "label_value": label_value})
            last_octet += 1

    def _test_semantic_check_vswitch_config(self, host_cfgs, exception_msg_regex=None):
        self._create_hosts_and_labels(host_cfgs)
        if exception_msg_regex:
            self.assertRaisesRegex(
                exception.LifecycleSemanticCheckException,
                exception_msg_regex,
                self.lifecycle._semantic_check_vswitch_config,
                self.dbapi
            )
        else:
            self.lifecycle._semantic_check_vswitch_config(self.dbapi)

    def test_semantic_check_vswitch_config_pass_aio_sx(self):
        self._test_semantic_check_vswitch_config({
            "controller-0": {
                "personality": constants.CONTROLLER,
                "subfunction": constants.WORKER,
                "labels": {
                    "openstack-compute-node": "enabled",
                    "openvswitch": "enabled",
                }
            },
        })

    @mock.patch.object(lifecycle_openstack.OpenstackAppLifecycleOperator,
                       '_get_vswitch_label_combinations',
                       return_value=EXTENDED_VSWITCH_ALLOWED_COMBINATIONS)
    def test_semantic_check_vswitch_config_fail_aio_sx_conflicting(self, *_):
        self._test_semantic_check_vswitch_config(
            {
                "controller-0": {
                    "personality": constants.CONTROLLER,
                    "subfunction": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "enabled",
                        "other-vswitch": "enabled",
                    }
                },
            },
            "^There are conflicting vswitch configurations: "
            "openvswitch=enabled, other-vswitch=enabled$"
        )

    def test_semantic_check_vswitch_config_fail_aio_sx_dpdk_only(self, *_):
        self._test_semantic_check_vswitch_config(
            {
                "controller-0": {
                    "personality": constants.CONTROLLER,
                    "subfunction": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "dpdk": "enabled",
                    }
                },
            },
            "^There are conflicting vswitch configurations: "
            "dpdk=enabled$"
        )

    def test_semantic_check_vswitch_config_fail_aio_sx_no_label(self):
        self._test_semantic_check_vswitch_config(
            {
                "controller-0": {
                    "personality": constants.CONTROLLER,
                    "subfunction": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                    }
                },
            },
            "^None of the openstack-enabled compute nodes have vswitch configured$"
        )

    @mock.patch.object(lifecycle_openstack.OpenstackAppLifecycleOperator,
                       '_get_vswitch_label_combinations',
                       return_value=EXTENDED_VSWITCH_ALLOWED_COMBINATIONS)
    def test_semantic_check_vswitch_config_pass_standard(self, *_):
        self._test_semantic_check_vswitch_config({
            "controller-0": {
                "personality": constants.CONTROLLER,
                "labels": {
                    "openstack-compute-node": "enabled",
                    "openvswitch": "enabled",
                    "other-vswitch": "enabled",
                }
            },
            "controller-1": {
                "personality": constants.CONTROLLER,
                "labels": {
                    "openstack-compute-node": "enabled",
                }
            },
            "worker-0": {
                "personality": constants.WORKER,
                "labels": {
                    "openstack-compute-node": "enabled",
                    "openvswitch": "enabled",
                }
            },
            "worker-1": {
                "personality": constants.WORKER,
                "labels": {
                    "openstack-compute-node": "enabled",
                    "openvswitch": "enabled",
                }
            },
            "worker-2": {
                "personality": constants.WORKER,
                "invprovision": constants.UNPROVISIONED,
                "labels": {
                    "openstack-compute-node": "enabled",
                    "openvswitch": "enabled",
                    "other-vswitch": "enabled",
                }
            },
            "worker-3": {
                "personality": constants.WORKER,
                "labels": {
                    "openvswitch": "enabled",
                    "other-vswitch": "enabled",
                }
            },
            "worker-4": {
                "personality": constants.WORKER,
                "labels": {
                    "not-a-vswitch-label": "enabled",
                }
            },
        })

    @mock.patch.object(lifecycle_openstack.OpenstackAppLifecycleOperator,
                       '_get_vswitch_label_combinations',
                       return_value=EXTENDED_VSWITCH_ALLOWED_COMBINATIONS)
    def test_semantic_check_vswitch_config_fail_standard_conflicting(self, *_):
        self._test_semantic_check_vswitch_config(
            {
                "controller-0": {
                    "personality": constants.CONTROLLER,
                },
                "worker-0": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "enabled",
                        "other-vswitch": "enabled",
                    }
                },
                "worker-1": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "enabled",
                        "dpdk": "enabled",
                        "other-vswitch": "enabled",
                    }
                },
                "worker-2": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "enabled",
                        "other-vswitch": "enabled",
                    }
                },
                "worker-3": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "enabled",
                        "dpdk": "enabled",
                        "other-vswitch": "enabled",
                    }
                },
                "worker-4": {
                    "personality": constants.WORKER,
                    "invprovision": constants.UNPROVISIONED,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "enabled",
                        "other-vswitch": "enabled",
                        "other-vswitch": "enabled",
                    }
                },
                "worker-5": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openvswitch": "enabled",
                        "dpdk": "enabled",
                        "other-vswitch": "enabled",
                    }
                },
            },
            "^There are conflicting vswitch configurations: "
            "dpdk=enabled, openvswitch=enabled, other-vswitch=enabled$"
        )

    def test_semantic_check_vswitch_config_fail_standard_no_labels(self):
        self._test_semantic_check_vswitch_config(
            {
                "controller-0": {
                    "personality": constants.CONTROLLER,
                },
                "worker-0": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "not-a-vswitch-label": "enabled",
                    }
                },
                "worker-1": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "disabled",
                    }
                },
                "worker-2": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                    }
                },
                "worker-3": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "enabled",
                    }
                },
                "worker-4": {
                    "personality": constants.WORKER,
                    "invprovision": constants.UNPROVISIONED,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "enabled",
                    }
                },
                "worker-5": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openvswitch": "enabled",
                        "dpdk": "enabled",
                    }
                },
            },
            "^There are openstack-enabled compute nodes with no vswitch configuration$"
        )

    @mock.patch.object(lifecycle_openstack.OpenstackAppLifecycleOperator,
                       '_get_vswitch_label_combinations',
                       return_value=EXTENDED_VSWITCH_ALLOWED_COMBINATIONS)
    def test_semantic_check_vswitch_config_fail_standard_misconfigured(self, *_):
        self._test_semantic_check_vswitch_config(
            {
                "controller-0": {
                    "personality": constants.CONTROLLER,
                },
                "worker-0": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "other-vswitch": "enabled",
                    }
                },
                "worker-1": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "other-vswitch": "enabled",
                    }
                },
                "worker-2": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "enabled",
                    }
                },
                "worker-3": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "other-vswitch": "enabled",
                    }
                },
                "worker-4": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "enabled",
                        "dpdk": "enabled",
                    }
                },
                "worker-5": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "enabled",
                    }
                },
                "worker-6": {
                    "personality": constants.WORKER,
                    "invprovision": constants.UNPROVISIONED,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "other-vswitch": "enabled",
                        "openvswitch": "enabled",
                        "dpdk": "enabled",
                    }
                },
                "worker-7": {
                    "personality": constants.WORKER,
                    "labels": {
                        "other-vswitch": "enabled",
                        "openvswitch": "enabled",
                        "dpdk": "enabled",
                    }
                },
            },
            "^There are conflicting vswitch configurations: "
            "dpdk=enabled, openvswitch=enabled, other-vswitch=enabled$"
        )

    @mock.patch.object(lifecycle_openstack.OpenstackAppLifecycleOperator,
                       '_get_vswitch_label_combinations',
                       return_value=EXTENDED_VSWITCH_ALLOWED_COMBINATIONS)
    def test_semantic_check_vswitch_config_fail_standard_no_labels_conflicting(self, *_):
        self._test_semantic_check_vswitch_config(
            {
                "controller-0": {
                    "personality": constants.CONTROLLER,
                },
                "worker-0": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "other-vswitch": "enabled",
                    }
                },
                "worker-1": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "enabled",
                        "dpdk": "enabled",
                        "other-vswitch": "enabled"
                    }
                },
                "worker-2": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                    }
                },
                "worker-3": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "enabled",
                    }
                },
                "worker-4": {
                    "personality": constants.WORKER,
                    "invprovision": constants.UNPROVISIONED,
                    "labels": {
                        "openstack-compute-node": "enabled",
                        "openvswitch": "enabled",
                    }
                },
                "worker-5": {
                    "personality": constants.WORKER,
                    "labels": {
                        "openvswitch": "enabled",
                        "dpdk": "enabled",
                    }
                },
            },
            "^There are openstack-enabled compute nodes with no vswitch configuration and "
            "there are conflicting vswitch configurations: "
            "dpdk=enabled, openvswitch=enabled, other-vswitch=enabled$"
        )

    @mock.patch(
        'k8sapp_openstack.lifecycle.lifecycle_openstack.get_available_volume_backends',
        return_value={
            "ceph": "general",
            app_constants.NETAPP_ISCSI_BACKEND_NAME: "",
            app_constants.NETAPP_NFS_BACKEND_NAME: "",
            app_constants.NETAPP_FC_BACKEND_NAME: ""
        }
    )
    @mock.patch('k8sapp_openstack.utils.create_aodh_rest_notifier_ca_cert_secret')
    @mock.patch('k8sapp_openstack.helpers.ldap.check_group', return_value=False)
    @mock.patch('k8sapp_openstack.helpers.ldap.add_group', return_value=True)
    @mock.patch('k8sapp_openstack.utils.create_clients_working_directory', return_value=True)
    @mock.patch('k8sapp_openstack.utils.get_clients_working_directory', return_value='/custom/path')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.lifecycle_utils.create_local_registry_secrets')
    @mock.patch('k8sapp_openstack.utils.create_storage_ca_cert_secret')
    @mock.patch('k8sapp_openstack.utils.migrate_legacy_netapp_ca_cert_secret')
    @mock.patch('k8sapp_openstack.utils.pre_apply_create_dex_resources_secret')
    @mock.patch('sysinv.common.kubernetes.KubeOperator')
    def test_create_app_specific_resources_pre_apply_success(
        self,
        mock_kube_operator,
        mock_create_dex_credentials_secret,
        mock_migrate_legacy_netapp_ca_cert_secret,
        mock_create_storage_ca_cert_secret,
        mock_create_local_registry_secrets,
        mock_get_working_dir,
        mock_create_dir,
        mock_add_group,
        mock_check_group,
        mock_create_aodh_rest_notifier_ca_cert_secret,
        *_
    ):
        """ Test the pre-apply actions for creating app-specific resources. """

        app_op = mock.Mock()
        app = mock.Mock(name='test_app', version='1.0')
        hook_info = mock.Mock()

        mock_kube = mock_kube_operator.return_value
        mock_kube.kube_get_config_map.return_value = True

        self.lifecycle._create_app_specific_resources_pre_apply(app_op, app, hook_info)

        mock_create_dex_credentials_secret.assert_called_once()
        mock_migrate_legacy_netapp_ca_cert_secret.assert_called_once()
        mock_create_storage_ca_cert_secret.assert_called_once()
        mock_create_aodh_rest_notifier_ca_cert_secret.assert_called_once()
        mock_create_local_registry_secrets.assert_called_once()
        mock_kube.kube_delete_config_map.assert_called_once()
        mock_check_group.assert_called_once()
        mock_add_group.assert_called_once()
        mock_create_dir.assert_called_once_with(path='/custom/path')

    @mock.patch('k8sapp_openstack.utils.create_aodh_rest_notifier_ca_cert_secret')
    @mock.patch('k8sapp_openstack.helpers.ldap.check_group', return_value=False)
    @mock.patch('k8sapp_openstack.helpers.ldap.add_group', return_value=True)
    @mock.patch('k8sapp_openstack.utils.create_clients_working_directory', return_value=True)
    @mock.patch('k8sapp_openstack.utils.get_clients_working_directory', return_value='/custom/path')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.lifecycle_utils.create_local_registry_secrets')
    @mock.patch('sysinv.common.kubernetes.KubeOperator')
    def test_create_app_specific_resources_pre_apply_failed(
            self,
            mock_kube_operator,
            mock_create_local_registry_secrets,
            mock_get_working_dir,
            mock_create_dir,
            mock_add_group,
            mock_check_group,
            mock_create_aodh_rest_notifier_ca_cert_secret):
        """ Test the pre-apply actions for creating app-specific resources with a failure. """

        mock_kube = mock_kube_operator.return_value
        mock_kube.kube_get_config_map.side_effect = RuntimeError("Simulated kube failure")

        app_op = mock.Mock()
        app = mock.Mock(name='test_app', version='1.0')
        hook_info = mock.Mock()

        self.assertRaises(
            RuntimeError,
            self.lifecycle._create_app_specific_resources_pre_apply,
            app_op,
            app,
            hook_info
        )

    @mock.patch(
        'k8sapp_openstack.lifecycle.lifecycle_openstack.get_available_volume_backends',
        return_value={
            "ceph": "general",
            app_constants.NETAPP_ISCSI_BACKEND_NAME: "",
            app_constants.NETAPP_NFS_BACKEND_NAME: "",
            app_constants.NETAPP_FC_BACKEND_NAME: ""
        }
    )
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.is_ceph_backend_available')
    def test_pre_apply_copy_storage_backend_config_rook_ceph_success(
        self,
        mock_is_ceph_backend_available,
        *_
    ):
        """Test when rook-ceph backend is available."""

        mock_kube = mock.Mock()
        fake_configmap = mock.Mock()
        fake_configmap.metadata.resource_version = "1.0"
        fake_configmap.metadata.namespace = "rook-ceph"
        fake_configmap.metadata.name = "rook-ceph"

        mock_is_ceph_backend_available.return_value = (True, "")
        mock_kube.kube_read_config_map.return_value = fake_configmap

        self.lifecycle._pre_apply_copy_storage_backend_config(mock_kube)

        mock_kube.kube_read_config_map.assert_called_once_with(
            self.lifecycle.APP_OPENSTACK_RESOURCE_CONFIG_MAP,
            app_constants.HELM_NS_ROOK_CEPH
        )
        mock_kube.kube_create_config_map.assert_called_once_with(
            common.HELM_NS_OPENSTACK,
            fake_configmap
        )
        assert fake_configmap.metadata.resource_version is None
        assert fake_configmap.metadata.namespace == common.HELM_NS_OPENSTACK
        assert fake_configmap.metadata.name == self.lifecycle.APP_OPENSTACK_RESOURCE_CONFIG_MAP

    @mock.patch(
        'k8sapp_openstack.lifecycle.lifecycle_openstack.get_available_volume_backends',
        return_value={
            "ceph": "general",
            app_constants.NETAPP_ISCSI_BACKEND_NAME: "",
            app_constants.NETAPP_NFS_BACKEND_NAME: "",
            app_constants.NETAPP_FC_BACKEND_NAME: ""
        }
    )
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.is_ceph_backend_available')
    def test_pre_apply_copy_storage_backend_config_rook_ceph_missing_configmap(
        self,
        mock_is_ceph_backend_available,
        *_
    ):
        """Test when rook-ceph backend is available but configmap is missing."""

        mock_kube = mock.Mock()

        mock_is_ceph_backend_available.return_value = (True, "")
        mock_kube.kube_read_config_map.return_value = None

        self.assertRaises(
            exception.LifecycleMissingInfo,
            self.lifecycle._pre_apply_copy_storage_backend_config,
            mock_kube
        )

    @mock.patch(
        'k8sapp_openstack.lifecycle.lifecycle_openstack.get_available_volume_backends',
        return_value={
            "ceph": "",
            app_constants.NETAPP_ISCSI_BACKEND_NAME: "",
            app_constants.NETAPP_NFS_BACKEND_NAME: "",
            app_constants.NETAPP_FC_BACKEND_NAME: ""
        }
    )
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.is_ceph_backend_available',
                return_value=(False, "Other reason"))
    def test_pre_apply_copy_storage_backend_config_backend_not_configured(
        self,
        *_
    ):
        """Test when Host Ceph and Rook-ceph are not available."""

        mock_kube = mock.Mock()
        mock_kube.kube_read_config_map.return_value = None

        self.lifecycle._pre_apply_copy_storage_backend_config(mock_kube)

        mock_kube.kube_read_config_map.assert_not_called()

    @mock.patch(
        'k8sapp_openstack.lifecycle.lifecycle_openstack.get_available_volume_backends',
        return_value={
            "ceph": "general",
            app_constants.NETAPP_ISCSI_BACKEND_NAME: "",
            app_constants.NETAPP_NFS_BACKEND_NAME: "",
            app_constants.NETAPP_FC_BACKEND_NAME: ""
        }
    )
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.is_ceph_backend_available')
    def test_pre_apply_copy_storage_backend_config_rbd_storage_backend_success(
        self,
        mock_is_ceph_backend_available,
        *_
    ):
        """Test host-ceph config map when rook-ceph is not available."""
        mock_kube = mock.Mock()
        fake_configmap = mock.Mock()
        fake_configmap.metadata.resource_version = "1.0"
        fake_configmap.metadata.namespace = "kube-system"
        fake_configmap.metadata.name = "rbd-storage-init"

        def ceph_backend_availability(ceph_type):
            if ceph_type == constants.SB_TYPE_CEPH_ROOK:
                return False, "Other reason"
            return True, ""

        mock_is_ceph_backend_available.side_effect = ceph_backend_availability
        mock_kube.kube_read_config_map.return_value = fake_configmap

        self.lifecycle._pre_apply_copy_storage_backend_config(mock_kube)

        mock_kube.kube_read_config_map.assert_called_once_with(
            self.lifecycle.APP_KUBESYSTEM_RESOURCE_CONFIG_MAP,
            common.HELM_NS_RBD_PROVISIONER
        )
        mock_kube.kube_create_config_map.assert_called_once_with(
            common.HELM_NS_OPENSTACK,
            fake_configmap
        )
        assert fake_configmap.metadata.namespace == common.HELM_NS_OPENSTACK
        assert fake_configmap.metadata.name == self.lifecycle.APP_OPENSTACK_RESOURCE_CONFIG_MAP

    @mock.patch('k8sapp_openstack.utils.delete_aodh_rest_notifier_ca_cert_secret')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.lifecycle_utils')
    @mock.patch('k8sapp_openstack.utils.delete_storage_ca_cert_secret')
    @mock.patch('k8sapp_openstack.utils.delete_dex_secret')
    @mock.patch(
        'k8sapp_openstack.lifecycle.lifecycle_openstack.OpenstackAppLifecycleOperator._post_remove_ldap_actions'
    )
    def test_delete_app_specific_resources_post_remove(
            self,
            mock_post_remove_ldap_actions,
            mock_delete_dex_secret,
            mock_delete_storage_ca_cert_secret,
            mock_lifecycle_utils,
            mock_delete_aodh_rest_notifier_ca_cert_secret):
        """ Test the post-remove actions for deleting app-specific resources. """

        app_op = mock.Mock()
        app = mock.Mock()
        hook_info = mock.Mock()

        self.lifecycle._delete_app_specific_resources_post_remove(app_op, app, hook_info)

        mock_lifecycle_utils.delete_local_registry_secrets.assert_called_once()
        mock_lifecycle_utils.delete_persistent_volume_claim.assert_called_once()
        mock_lifecycle_utils.delete_configmap.assert_called_once()
        mock_delete_dex_secret.assert_called_once()
        mock_delete_storage_ca_cert_secret.assert_called_once()
        mock_delete_aodh_rest_notifier_ca_cert_secret.assert_called_once()
        mock_lifecycle_utils.delete_namespace.assert_called_once()
        mock_post_remove_ldap_actions.assert_called_once()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.utils.HostHelper.get_active_controller')
    @mock.patch(
        'k8sapp_openstack.lifecycle.lifecycle_openstack.utils.is_host_simplex_controller',
        return_value=True
    )
    def test_pre_apply_check_fail_vim_services(self, mock_simplex, mock_get_active_controller):
        """ Test the pre-apply check for VIM services when they are not enabled. """

        active_controller = mock.Mock(vim_progress_status="not-enabled")
        active_controller.hostname = 'controller-0'
        mock_get_active_controller.return_value = active_controller

        self.assertRaises(
            exception.LifecycleSemanticCheckException,
            self.lifecycle._pre_apply_check,
            mock.Mock(),
            mock.Mock(name='test_app'),
            mock.Mock()
        )

    @mock.patch('k8sapp_openstack.helpers.ldap.check_group', return_value=False)
    @mock.patch('k8sapp_openstack.helpers.ldap.add_group', return_value=True)
    @mock.patch('k8sapp_openstack.utils.create_clients_working_directory', return_value=True)
    @mock.patch('k8sapp_openstack.utils.get_clients_working_directory', return_value='/custom/path')
    def test_pre_apply_ldap_actions_success(
            self,
            mock_get_dir,
            mock_create_dir,
            mock_add_group,
            mock_check_group):
        """ Test the pre-apply LDAP actions for creating a group and directory. """

        app = mock.Mock(name='test_app', version='1.0')

        self.lifecycle._pre_apply_ldap_actions(app)

        mock_check_group.assert_called_once()
        mock_add_group.assert_called_once()
        mock_create_dir.assert_called_once_with(path='/custom/path')

    @mock.patch('k8sapp_openstack.helpers.ldap.check_group', return_value=True)
    @mock.patch('k8sapp_openstack.helpers.ldap.delete_group')
    @mock.patch('k8sapp_openstack.utils.delete_clients_working_directory', return_value=True)
    def test_post_remove_ldap_actions_success(self, mock_delete_dir, mock_delete_group, mock_check_group):
        """ Test the post-remove LDAP actions for deleting a group and directory. """

        self.lifecycle._post_remove_ldap_actions()

        mock_delete_dir.assert_called_once()
        mock_check_group.assert_called_once()
        mock_delete_group.assert_called_once()

    def test__post_remove_missing_extra(self):
        """ Test post_remove with missing extra information. """

        context = mock.Mock()
        conductor_obj = mock.Mock()
        hook_info = {}

        self.assertRaises(
            exception.LifecycleMissingInfo,
            self.lifecycle.post_remove,
            context,
            conductor_obj,
            hook_info
        )

    def test__post_remove_missing_app_removed(self):
        """ Test post_remove with missing app_removed information. """

        context = mock.Mock()
        conductor_obj = mock.Mock()
        hook_info = {
            LifecycleConstants.EXTRA: {}
        }

        self.assertRaises(
            exception.LifecycleMissingInfo,
            self.lifecycle.post_remove,
            context,
            conductor_obj,
            hook_info
        )

    def test__post_remove_app_removed_true(self):
        """ Test post_remove with app_removed set to True. """

        context = mock.Mock()
        conductor_obj = mock.Mock()
        hook_info = {
            LifecycleConstants.EXTRA: {
                LifecycleConstants.APP_REMOVED: True
            }
        }

        self.lifecycle.post_remove(context, conductor_obj, hook_info)

        conductor_obj._update_vim_config.assert_called_once_with(context)
        conductor_obj._update_radosgw_config.assert_called_once_with(context)

    def test__post_remove_app_removed_false(self):
        """ Test post_remove with app_removed set to False. """

        context = mock.Mock()
        conductor_obj = mock.Mock()
        hook_info = {
            LifecycleConstants.EXTRA: {
                LifecycleConstants.APP_REMOVED: False
            }
        }

        self.lifecycle.post_remove(context, conductor_obj, hook_info)

        conductor_obj._update_vim_config.assert_not_called()
        conductor_obj._update_radosgw_config.assert_not_called()

    def test_semantic_check_datanet_config_fail_multiple_datanets_in_same_interface(self):
        """
        Simulates configurations where multiple data networks are associated with the same
        interface, in multiple openstack-enabled worker nodes, to assert that the semantic check
        fails with the proper messages.
        """

        datanetworks = []
        for dn_id in range(3):
            datanetworks.append(dbutils.create_test_datanetwork(
                name=f"dn{dn_id}",
                network_type=constants.DATANETWORK_TYPE_VLAN,
                mtu=1500))

        def create_host_and_iface(index):
            host = dbutils.create_test_ihost(
                uuid=None,
                forisystemid=self.system.id,
                hostname=f"compute-{index}",
                personality=constants.WORKER,
                subfunctions=constants.WORKER,
                invprovision=constants.PROVISIONED,
                mgmt_mac=f"1E:AA:03:4F:C0:{index:02x}"
            )

            self.dbapi.label_create(host.uuid, {"host_id": host.id,
                                                "label_key": "openstack-compute-node",
                                                "label_value": "enabled"})

            iface = dbutils.create_test_interface(
                ifname=f"data{index}",
                ifclass=constants.INTERFACE_CLASS_DATA,
                forihostid=host.id,
                ihost_uuid=host.uuid)

            for dn in datanetworks:
                dbutils.create_test_interface_datanetwork(interface_id=iface.id,
                                                          datanetwork_id=dn.id)

        for index in range(3):
            create_host_and_iface(index)

        # When host count is MAX_HOSTS_FOR_DETAILED_MSG or less, throws detailed message
        self.assertRaisesRegex(
            exception.LifecycleSemanticCheckException,
            r"^Interfaces cannot have multiple associated data networks: data0 in compute-0 "
            r"\(dn0, dn1, dn2\), data1 in compute-1 \(dn0, dn1, dn2\), "
            r"data2 in compute-2 \(dn0, dn1, dn2\)$",
            self.lifecycle._semantic_check_datanetwork_config,
            self.dbapi
        )

        for index in range(3, 6):
            create_host_and_iface(index)

        # When host count is greater than MAX_HOSTS_FOR_DETAILED_MSG, throws generic message
        self.assertRaisesRegex(
            exception.LifecycleSemanticCheckException,
            r"^There are 6 hosts in which multiple data networks are associated with the same "
            r"interface$",
            self.lifecycle._semantic_check_datanetwork_config,
            self.dbapi
        )

    def test_semantic_check_datanet_config_fail_hosts_with_no_datanets(self):
        """
        Simulates configurations where openstack-enabled worker nodes have no data networks
        associated with interfaces, to assert that the semantic check fails with the proper
        messages.
        """

        def create_host(index):
            host = dbutils.create_test_ihost(
                uuid=None,
                forisystemid=self.system.id,
                hostname=f"compute-{index}",
                personality=constants.WORKER,
                subfunctions=constants.WORKER,
                invprovision=constants.PROVISIONED,
                mgmt_mac=f"1E:AA:03:4F:C0:{index:02x}"
            )

            self.dbapi.label_create(host.uuid, {"host_id": host.id,
                                                "label_key": "openstack-compute-node",
                                                "label_value": "enabled"})

        for index in range(3):
            create_host(index)

        # When host count is MAX_HOSTS_FOR_DETAILED_MSG or less, throws detailed message
        self.assertRaisesRegex(
            exception.LifecycleSemanticCheckException,
            r"^The following hosts have no data networks associated with interfaces: compute-0, "
            r"compute-1, compute-2$",
            self.lifecycle._semantic_check_datanetwork_config,
            self.dbapi
        )

        for index in range(3, 6):
            create_host(index)

        # When host count is greater than MAX_HOSTS_FOR_DETAILED_MSG, throws generic message
        self.assertRaisesRegex(
            exception.LifecycleSemanticCheckException,
            r"^There are 6 hosts in which no data network is associated with an interface$",
            self.lifecycle._semantic_check_datanetwork_config,
            self.dbapi
        )

    def test_semantic_check_datanet_config_pass(self):
        """
        Simulates a valid configuration for data networks to validate that the semantic check
        passes and no exception is thrown.
        """

        datanets = []
        for dn_id in range(2):
            datanet = dbutils.create_test_datanetwork(
                name=f"dn{dn_id}",
                network_type=constants.DATANETWORK_TYPE_VLAN,
                mtu=1500)
            datanets.append(datanet)

        for index in range(2):
            host = dbutils.create_test_ihost(
                uuid=None,
                forisystemid=self.system.id,
                hostname=f"compute-{index}",
                personality=constants.WORKER,
                subfunctions=constants.WORKER,
                invprovision=constants.PROVISIONED,
                mgmt_mac=f"1E:AA:03:4F:C0:{index:02x}"
            )

            self.dbapi.label_create(host.uuid, {"host_id": host.id,
                                                "label_key": "openstack-compute-node",
                                                "label_value": "enabled"})

            if_id = 0
            for datanet in datanets:
                iface = dbutils.create_test_interface(
                    ifname=f"data-{index}-{if_id}",
                    ifclass=constants.INTERFACE_CLASS_DATA,
                    forihostid=host.id,
                    ihost_uuid=host.uuid)
                dbutils.create_test_interface_datanetwork(
                    interface_id=iface.id, datanetwork_id=datanet.id)
                if_id += 1

        compute_2 = dbutils.create_test_ihost(
            uuid=None,
            forisystemid=self.system.id,
            hostname="compute-2",
            personality=constants.WORKER,
            subfunctions=constants.WORKER,
            invprovision=constants.UNPROVISIONED,
            mgmt_mac="1E:AA:03:4F:C0:02"
        )

        self.dbapi.label_create(host.uuid, {"host_id": compute_2.id,
                                            "label_key": "openstack-compute-node",
                                            "label_value": "enabled"})

        # compute-2 does not have datanets associated to interfaces, but it is not provisioned,
        # so the config is still valid.

        compute_3 = dbutils.create_test_ihost(
            uuid=None,
            forisystemid=self.system.id,
            hostname="compute-3",
            personality=constants.WORKER,
            subfunctions=constants.WORKER,
            invprovision=constants.PROVISIONED,
            mgmt_mac="1E:AA:03:4F:C0:03"
        )

        data_3_0 = dbutils.create_test_interface(
            ifname="data-3-0",
            ifclass=constants.INTERFACE_CLASS_DATA,
            forihostid=compute_3.id,
            ihost_uuid=compute_3.uuid)

        for datanet in datanets:
            dbutils.create_test_interface_datanetwork(
                interface_id=data_3_0.id, datanetwork_id=datanet.id)

        # compute-3 has two datanets associated to the same interface but it is not
        # openstack-enabled, so the config is still valid.

        self.lifecycle._semantic_check_datanetwork_config(self.dbapi)

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.app_utils')
    def test__semantic_check_dc_system_type_rejects_central(self, mock_app_utils):
        """Verify that application apply is rejected on Central Cloud (SystemController)."""
        app = mock.Mock()

        # Simulate Central Cloud
        mock_app_utils.is_central_cloud.return_value = True

        exc = self.assertRaises(
            exception.LifecycleSemanticCheckException,
            self.lifecycle._semantic_check_dc_system_type,
            app
        )
        self.assertIn("cannot be applied on Central Controller", str(exc))
        mock_app_utils.is_central_cloud.assert_called()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.app_utils')
    def test__semantic_check_dc_system_type_allows_subcloud(self, mock_app_utils):
        """Verify that application apply is allowed on Subcloud (not SystemController)."""
        app = mock.Mock()

        # Simulate Subcloud
        mock_app_utils.is_central_cloud.return_value = False
        self.lifecycle._semantic_check_dc_system_type(app)
        mock_app_utils.is_central_cloud.assert_called()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.is_dex_enabled', return_value=True)
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.get_endpoint_domain')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.oidc_parameters_exist')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_dex_healthy')
    def test_semantic_check_oidc_config_get_endpoint_domain_fail(
        self, mock_check_dex_healthy, mock_oidc_parameters_exist, mock_get_endpoint_domain,
        mock_is_dex_enabled
    ):
        """Ensure OIDC check fails when Endpoint Domain, should not verify
        parameters and Dex healthy"""
        mock_get_endpoint_domain.return_value = False
        fake_db = mock.MagicMock()

        with self.assertRaisesRegex(
            exception.LifecycleSemanticCheckException,
            "Missing the endpoint_domain configuration for OpenStack,"
            " mandatory for DEX integration."
        ):
            self.lifecycle._semantic_check_oidc_config(fake_db)

        mock_is_dex_enabled.assert_called_once()
        mock_get_endpoint_domain.assert_called_once_with(fake_db)
        mock_oidc_parameters_exist.assert_not_called()
        mock_check_dex_healthy.assert_not_called()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.is_dex_enabled', return_value=True)
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.get_endpoint_domain')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.oidc_parameters_exist')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_dex_healthy')
    def test_semantic_check_oidc_config_parameters_missing(
        self, mock_check_dex_healthy, mock_oidc_parameters_exist, mock_get_endpoint_domain,
        mock_is_dex_enabled
    ):
        """Ensure OIDC check fails when mandatory parameters are missing."""
        mock_get_endpoint_domain.return_value = True
        mock_oidc_parameters_exist.return_value = False

        with self.assertRaisesRegex(
            exception.LifecycleSemanticCheckException, "Missing OIDC parameters"
        ):
            self.lifecycle._semantic_check_oidc_config(mock.MagicMock())

        mock_is_dex_enabled.assert_called_once()
        mock_get_endpoint_domain.assert_called_once()
        mock_oidc_parameters_exist.assert_called_once()
        mock_check_dex_healthy.assert_not_called()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.is_dex_enabled', return_value=True)
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.get_endpoint_domain')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.oidc_parameters_exist')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_dex_healthy')
    def test_semantic_check_oidc_config_dex_health_fail(
        self, mock_check_dex_healthy, mock_oidc_parameters_exist, mock_get_endpoint_domain,
        mock_is_dex_enabled
    ):
        """Ensure OIDC check fails when Dex health check reports unhealthy."""
        mock_get_endpoint_domain.return_value = True
        mock_oidc_parameters_exist.return_value = True
        mock_check_dex_healthy.return_value = False
        fake_db = mock.MagicMock()

        with self.assertRaisesRegex(
            exception.LifecycleSemanticCheckException, "Dex health check failed"
        ):
            self.lifecycle._semantic_check_oidc_config(fake_db)

        mock_is_dex_enabled.assert_called_once()
        mock_get_endpoint_domain.assert_called_once()
        mock_oidc_parameters_exist.assert_called_once_with(fake_db)
        mock_check_dex_healthy.assert_called_once_with(fake_db, True)

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.is_dex_enabled', return_value=True)
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.get_endpoint_domain')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.oidc_parameters_exist')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_dex_healthy')
    def test_semantic_check_oidc_config_success(
        self, mock_check_dex_healthy, mock_oidc_parameters_exist, mock_get_endpoint_domain,
        mock_is_dex_enabled
    ):
        """Verify OIDC semantic check passes when parameters, Dex and Endpoint Domain are OK."""
        mock_get_endpoint_domain.return_value = True
        mock_oidc_parameters_exist.return_value = True
        mock_check_dex_healthy.return_value = True
        fake_db = mock.MagicMock()

        self.lifecycle._semantic_check_oidc_config(fake_db)

        mock_is_dex_enabled.assert_called_once()
        mock_get_endpoint_domain.assert_called_once_with(fake_db)
        mock_oidc_parameters_exist.assert_called_once_with(fake_db)
        mock_check_dex_healthy.assert_called_once_with(fake_db, True)

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_if_namespace_exists')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_if_pvc_exists_in_a_namespace')
    def test_semantic_check_backend_storageclass_no_namespace(
        self,
        mock_check_if_pvc_exists,
        mock_check_if_namespace_exists,
    ):
        """Test if _check_storageclass_immutability returns when there is no namespace"""
        mock_check_if_namespace_exists.return_value = False

        self.lifecycle._check_storageclass_immutability()

        mock_check_if_pvc_exists.assert_not_called()

    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.LOG")
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.check_if_pvc_exists_in_a_namespace")
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_if_namespace_exists')
    def test_semantic_check_backend_storageclass_no_pvc(
        self,
        mock_check_if_namespace_exists,
        mock_check_if_pvc_exists_in_a_namespace,
        mock_log,
    ):
        """Test if _check_storageclass_immutability returns when there is no pvc in the namespace"""
        mock_check_if_namespace_exists.return_value = True
        mock_check_if_pvc_exists_in_a_namespace.return_value = False

        self.assertIsNone(self.lifecycle._check_storageclass_immutability())
        msg = mock_log.info.call_args[0][0]
        mock_log.info.assert_called_once()
        self.assertIn("no PVCs", msg)

    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.get_pvc_storageclass")
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.get_storage_backends_priority_list")
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.get_available_volume_backends")
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.check_if_pvc_exists_in_a_namespace", return_value=True)
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.check_if_namespace_exists", return_value=True)
    def test_semantic_check_backend_storageclass_uses_chart_specific_backends(
        self,
        mock_check_if_namespace_exists,
        mock_check_if_pvc_exists_in_a_namespace,
        mock_get_available_volume_backends,
        mock_get_storage_backends_priority_list,
        mock_get_pvc_storageclass,
    ):
        """Test chart-specific backend lookup for StatefulSet PVC semantic check."""
        mock_get_available_volume_backends.side_effect = [
            {
                app_constants.CEPH_BACKEND_NAME: "general",
                app_constants.NETAPP_NFS_BACKEND_NAME: "netapp-nas-backend",
            },
            {
                app_constants.CEPH_BACKEND_NAME: "general",
                app_constants.NETAPP_NFS_BACKEND_NAME: "netapp-nas-backend",
            },
        ]
        mock_get_storage_backends_priority_list.side_effect = [
            [app_constants.CEPH_BACKEND_NAME, app_constants.NETAPP_NFS_BACKEND_NAME],
            [app_constants.CEPH_BACKEND_NAME, app_constants.NETAPP_NFS_BACKEND_NAME],
        ]
        mock_get_pvc_storageclass.side_effect = [
            "general",
            "general",
        ]

        self.assertIsNone(self.lifecycle._check_storageclass_immutability())
        self.assertEqual(
            [
                mock.call(chart_name=app_constants.HELM_CHART_MARIADB),
                mock.call(chart_name=app_constants.HELM_CHART_RABBITMQ),
            ],
            mock_get_available_volume_backends.call_args_list,
        )

    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.check_storageclass_change")
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.get_pvc_storageclass")
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.get_storage_backends_priority_list")
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.get_available_volume_backends")
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.check_if_pvc_exists_in_a_namespace", return_value=True)
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.check_if_namespace_exists", return_value=True)
    def test_semantic_check_backend_storageclass_mariadb_failed(
        self,
        mock_check_if_namespace_exists,
        mock_check_if_pvc_exists_in_a_namespace,
        mock_get_available_volume_backends,
        mock_get_storage_backends_priority_list,
        mock_get_pvc_storageclass,
        mock_check_storageclass_change,
    ):
        """Test if _semantic_check_backend_storageclass fails in case a storage class is detected for mariadb"""
        mock_get_available_volume_backends.return_value = ["storageclass"]
        mock_get_storage_backends_priority_list.side_effect = [
            ["storageclass"],  # mariadb priority list
            ["storageclass"],  # rabbitmq priority list
        ]

        mock_get_pvc_storageclass.side_effect = [
            "storageclass",
            "storageclass",
        ]
        mock_check_storageclass_change.side_effect = [
            (True, "new"),
            (False, None),
        ]

        try:
            self.lifecycle._check_storageclass_immutability()
        except exception.LifecycleSemanticCheckException as e:
            self.assertIn("mariadb", str(e).lower())

    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.check_storageclass_change")
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.get_pvc_storageclass")
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.get_storage_backends_priority_list")
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.get_available_volume_backends")
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.check_if_pvc_exists_in_a_namespace", return_value=True)
    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.check_if_namespace_exists", return_value=True)
    def test_semantic_check_backend_storageclass_rabbitmq_failed(
        self,
        mock_check_if_namespace_exists,
        mock_check_if_pvc_exists_in_a_namespace,
        mock_get_available_volume_backends,
        mock_get_storage_backends_priority_list,
        mock_get_pvc_storageclass,
        mock_check_storageclass_change,
    ):
        """Test if _semantic_check_backend_storageclass raises in case a storage class is detected for rabbitmq"""
        mock_get_available_volume_backends.return_value = ["storageclass"]
        mock_get_storage_backends_priority_list.side_effect = [
            ["storageclass"],
            ["storageclass"],
        ]

        mock_get_pvc_storageclass.side_effect = [
            "storageclass",
            "storageclass",
        ]
        mock_check_storageclass_change.side_effect = [
            (False, None),
            (True, "new"),
        ]

        try:
            self.lifecycle._check_storageclass_immutability()
        except exception.LifecycleSemanticCheckException as e:
            self.assertIn("rabbitmq", str(e).lower())

    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.get_pvc_storageclass_requirements")
    def test_check_storageclass_resolution_pass(
        self,
        mock_get_requirements,
    ):
        """Resolution check passes when every requirement resolves a StorageClass."""
        mock_get_requirements.return_value = [
            {'chart': 'mariadb', 'priority_list': ['ceph'], 'storage_class': 'general'},
            {'chart': 'rabbitmq', 'priority_list': ['ceph'], 'storage_class': 'general'},
        ]
        self.assertIsNone(self.lifecycle._check_storageclass_resolution())

    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.get_pvc_storageclass_requirements")
    def test_check_storageclass_resolution_mariadb_unresolved_raises(
        self,
        mock_get_requirements,
    ):
        """Resolution check blocks apply and names the chart + priority list."""
        mock_get_requirements.return_value = [
            {
                'chart': 'mariadb',
                'priority_list': ['unknown-backend'],
                'storage_class': None,
            },
        ]
        try:
            self.lifecycle._check_storageclass_resolution()
            self.fail("Expected LifecycleSemanticCheckException")
        except exception.LifecycleSemanticCheckException as e:
            msg = str(e).lower()
            self.assertIn("mariadb", msg)
            self.assertIn("unknown-backend", msg)

    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.get_pvc_storageclass_requirements")
    def test_check_storageclass_resolution_glance_pvc_unresolved_raises(
        self,
        mock_get_requirements,
    ):
        """Glance PVC-mode with an unresolvable priority list blocks apply."""
        mock_get_requirements.return_value = [
            {'chart': 'mariadb', 'priority_list': ['ceph'], 'storage_class': 'general'},
            {'chart': 'rabbitmq', 'priority_list': ['ceph'], 'storage_class': 'general'},
            {
                'chart': 'glance (PVC image store)',
                'priority_list': ['dell-nfs'],
                'storage_class': None,
            },
        ]
        try:
            self.lifecycle._check_storageclass_resolution()
            self.fail("Expected LifecycleSemanticCheckException")
        except exception.LifecycleSemanticCheckException as e:
            self.assertIn("glance", str(e).lower())

    @mock.patch("k8sapp_openstack.lifecycle.lifecycle_openstack.get_pvc_storageclass_requirements")
    def test_check_storageclass_resolution_cinder_backup_unresolved_raises(
        self,
        mock_get_requirements,
    ):
        """Cinder backup requiring a PVC with no resolution blocks apply."""
        mock_get_requirements.return_value = [
            {'chart': 'mariadb', 'priority_list': ['ceph'], 'storage_class': 'general'},
            {'chart': 'rabbitmq', 'priority_list': ['ceph'], 'storage_class': 'general'},
            {
                'chart': 'cinder (backup)',
                'priority_list': ['dell-iscsi'],
                'storage_class': None,
            },
        ]
        try:
            self.lifecycle._check_storageclass_resolution()
            self.fail("Expected LifecycleSemanticCheckException")
        except exception.LifecycleSemanticCheckException as e:
            self.assertIn("cinder", str(e).lower())

    @mock.patch(
        "k8sapp_openstack.lifecycle.lifecycle_openstack.OpenstackAppLifecycleOperator."
        "_check_storageclass_immutability"
    )
    @mock.patch(
        "k8sapp_openstack.lifecycle.lifecycle_openstack.OpenstackAppLifecycleOperator."
        "_check_storageclass_resolution"
    )
    def test_semantic_check_backend_storageclass_orchestrates_both(
        self,
        mock_resolution,
        mock_immutability,
    ):
        """The orchestrator runs resolution first, then immutability."""
        self.lifecycle._semantic_check_backend_storageclass()
        mock_resolution.assert_called_once()
        mock_immutability.assert_called_once()

    @mock.patch('k8sapp_openstack.helpers.ldap.add_group', return_value=True)
    @mock.patch('k8sapp_openstack.helpers.ldap.check_group', return_value=False)
    @mock.patch('k8sapp_openstack.utils.is_central_cloud', return_value=True)
    def test_post_upload_creates_ldap_group_on_central_cloud(
        self,
        mock_is_central_cloud,
        mock_check_group,
        mock_add_group
    ):
        """Test that LDAP group is created on central cloud during post upload."""
        app = mock.Mock()
        self.lifecycle._post_upload_ldap_actions(app)
        mock_is_central_cloud.assert_called_once()
        mock_check_group.assert_called_once_with(
            app_constants.CLIENTS_WORKING_DIR_GROUP
        )
        mock_add_group.assert_called_once_with(
            app_constants.CLIENTS_WORKING_DIR_GROUP
        )

    @mock.patch('k8sapp_openstack.helpers.ldap.add_group')
    @mock.patch('k8sapp_openstack.helpers.ldap.check_group')
    @mock.patch('k8sapp_openstack.utils.is_central_cloud', return_value=False)
    def test_post_upload_skips_on_non_central_cloud(
        self,
        mock_is_central_cloud,
        mock_check_group,
        mock_add_group
    ):
        """Test that LDAP actions are skipped on non-central cloud."""
        app = mock.Mock()
        self.lifecycle._post_upload_ldap_actions(app)
        mock_is_central_cloud.assert_called_once()
        mock_check_group.assert_not_called()
        mock_add_group.assert_not_called()

    @mock.patch('k8sapp_openstack.helpers.ldap.add_group')
    @mock.patch('k8sapp_openstack.helpers.ldap.check_group', return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_central_cloud', return_value=True)
    def test_post_upload_skips_if_group_exists(
        self,
        mock_is_central_cloud,
        mock_check_group,
        mock_add_group
    ):
        """Test that LDAP group creation is skipped if group already exists."""
        app = mock.Mock()
        self.lifecycle._post_upload_ldap_actions(app)
        mock_check_group.assert_called_once_with(
            app_constants.CLIENTS_WORKING_DIR_GROUP
        )
        mock_add_group.assert_not_called()

    @mock.patch('k8sapp_openstack.helpers.ldap.add_group', return_value=False)
    @mock.patch('k8sapp_openstack.helpers.ldap.check_group', return_value=False)
    @mock.patch('k8sapp_openstack.utils.is_central_cloud', return_value=True)
    def test_post_upload_logs_error_on_failure(
        self,
        mock_is_central_cloud,
        mock_check_group,
        mock_add_group
    ):
        """Test that LDAP group creation failure logs error but does not raise."""
        app = mock.Mock()
        self.lifecycle._post_upload_ldap_actions(app)
        mock_add_group.assert_called_once_with(
            app_constants.CLIENTS_WORKING_DIR_GROUP
        )


class OpenstackAppLifecycleEsbSemanticCheckTest(dbbase.BaseHostTestCase):
    """Unit tests for the ESB pre-apply semantic checks"""

    def setUp(self):
        super(OpenstackAppLifecycleEsbSemanticCheckTest, self).setUp()
        self.lifecycle = lifecycle_openstack.OpenstackAppLifecycleOperator()

    # ------------------------------------------------------------------
    # _validate_esb_entry (required-field validation for a single entry)
    # ------------------------------------------------------------------
    def test_validate_esb_entry_valid_iscsi_none(self):
        """A valid iSCSI entry with k8s_storage_class 'none' produces no error."""
        entry = {"name": "dell-iscsi", "protocol": "iscsi",
                 "k8s_storage_class": "none", "volume_backend": {}}
        self.assertEqual(
            self.lifecycle._validate_esb_entry("dell-iscsi", entry), [])

    def test_validate_esb_entry_valid_local(self):
        """protocol 'local' is accepted (experimental/internal)."""
        entry = {"name": "cns", "protocol": "local", "k8s_storage_class": "none"}
        self.assertEqual(self.lifecycle._validate_esb_entry("cns", entry), [])

    def test_validate_esb_entry_missing_protocol(self):
        """Missing protocol is reported with the backend name and field."""
        entry = {"name": "dell-iscsi", "k8s_storage_class": "none"}
        errors = self.lifecycle._validate_esb_entry("dell-iscsi", entry)
        self.assertEqual(len(errors), 1)
        self.assertIn("dell-iscsi", errors[0])
        self.assertIn("protocol", errors[0])

    def test_validate_esb_entry_invalid_protocol_fc(self):
        """An invalid protocol value (fc) is reported with the invalid value."""
        entry = {"name": "dell-fc", "protocol": "fc",
                 "k8s_storage_class": "none"}
        errors = self.lifecycle._validate_esb_entry("dell-fc", entry)
        self.assertEqual(len(errors), 1)
        self.assertIn("dell-fc", errors[0])
        self.assertIn("fc", errors[0])

    def test_validate_esb_entry_rbd_rejected(self):
        """protocol 'rbd' is rejected as internal-only."""
        entry = {"name": "myrbd", "protocol": "rbd",
                 "k8s_storage_class": "none"}
        errors = self.lifecycle._validate_esb_entry("myrbd", entry)
        self.assertEqual(len(errors), 1)
        self.assertIn("rbd", errors[0])
        self.assertIn("internal-only", errors[0])

    def test_validate_esb_entry_missing_k8s_storage_class_not_required(self):
        """Missing k8s_storage_class is NOT an entry error (only protocol is
        required). Necessity is enforced by the resolution/backup checks."""
        entry = {"name": "dell-iscsi", "protocol": "iscsi"}
        self.assertEqual(
            self.lifecycle._validate_esb_entry("dell-iscsi", entry), [])

    def test_validate_esb_entry_volume_backend_not_validated(self):
        """volume_backend contents are not validated (opaque pass-through)."""
        entry = {"name": "dell-iscsi", "protocol": "iscsi",
                 "k8s_storage_class": "dell-sc", "volume_backend": {}}
        self.assertEqual(
            self.lifecycle._validate_esb_entry("dell-iscsi", entry), [])

    # ------------------------------------------------------------------
    # _validate_esb_backend_configs (enabled non-strict entries)
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.utils.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    def test_validate_esb_backend_configs_strict_ignored(
        self, mock_enabled, mock_backends_conf
    ):
        """Strict names are skipped; a matching backends_conf entry is ignored."""
        mock_enabled.return_value = [app_constants.CEPH_BACKEND_NAME,
                                     "dell-iscsi"]
        mock_backends_conf.return_value = {
            # A backends_conf entry matching a strict name is silently ignored.
            app_constants.CEPH_BACKEND_NAME: {"name": "ceph",
                                              "protocol": "rbd"},
            "dell-iscsi": {"name": "dell-iscsi", "protocol": "iscsi",
                           "k8s_storage_class": "none"},
        }
        available, errors = self.lifecycle._validate_esb_backend_configs()
        self.assertTrue(available)
        self.assertEqual(errors, [])

    @mock.patch('k8sapp_openstack.utils.get_backends_conf', return_value={})
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    def test_validate_esb_backend_configs_orphan_name(
        self, mock_enabled, mock_backends_conf
    ):
        """An enabled ESB name with no backends_conf entry is an error."""
        mock_enabled.return_value = ["dell-iscsi"]
        available, errors = self.lifecycle._validate_esb_backend_configs()
        self.assertFalse(available)
        self.assertEqual(len(errors), 1)
        self.assertIn("dell-iscsi", errors[0])
        self.assertIn("no matching", errors[0])

    @mock.patch('k8sapp_openstack.utils.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    def test_validate_esb_backend_configs_only_strict_conf_ignored(
        self, mock_enabled, mock_backends_conf
    ):
        """Only strict backends enabled: no ESB availability, no errors."""
        mock_enabled.return_value = [app_constants.CEPH_BACKEND_NAME]
        mock_backends_conf.return_value = {
            app_constants.CEPH_BACKEND_NAME: {"name": "ceph",
                                              "protocol": "rbd"},
        }
        available, errors = self.lifecycle._validate_esb_backend_configs()
        self.assertFalse(available)
        self.assertEqual(errors, [])

    # ------------------------------------------------------------------
    # _semantic_check_storage_backend_available (ESB-only + hybrid)
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.utils.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    def test_storage_backend_available_esb_only_valid_proceeds(
        self, mock_enabled, mock_backends_conf
    ):
        """A valid ESB backend satisfies availability when no strict backend."""
        mock_enabled.return_value = ["dell-iscsi"]
        mock_backends_conf.return_value = {
            "dell-iscsi": {"name": "dell-iscsi", "protocol": "iscsi",
                           "k8s_storage_class": "none"},
        }
        # strict_available=False, but a valid ESB entry is present -> no raise.
        self.lifecycle._semantic_check_storage_backend_available(False, "")

    @mock.patch('k8sapp_openstack.utils.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    def test_storage_backend_available_esb_only_invalid_blocked(
        self, mock_enabled, mock_backends_conf
    ):
        """An invalid ESB backend with no strict backend blocks apply."""
        mock_enabled.return_value = ["dell-iscsi"]
        mock_backends_conf.return_value = {
            "dell-iscsi": {"name": "dell-iscsi",
                           "k8s_storage_class": "none"},  # missing protocol
        }
        try:
            self.lifecycle._semantic_check_storage_backend_available(False, "")
        except exception.LifecycleSemanticCheckException as e:
            self.assertIn("protocol", str(e))
            self.assertIn("dell-iscsi", str(e))
        else:
            self.fail("LifecycleSemanticCheckException was not raised")

    @mock.patch('k8sapp_openstack.utils.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    def test_storage_backend_available_invalid_esb_logged_when_strict_available(
        self, mock_enabled, mock_backends_conf
    ):
        """Invalid ESB entries are logged (not blocking) when strict is up."""
        mock_enabled.return_value = ["dell-iscsi"]
        mock_backends_conf.return_value = {
            "dell-iscsi": {"name": "dell-iscsi",
                           "k8s_storage_class": "none"},  # missing protocol
        }
        # strict_available=True -> invalid ESB entry logged, no raise.
        self.lifecycle._semantic_check_storage_backend_available(True, "")

    # ------------------------------------------------------------------
    # _semantic_check_secretref
    # ------------------------------------------------------------------
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.kubernetes.KubeOperator')
    @mock.patch('k8sapp_openstack.utils.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    def test_secretref_valid(self, mock_enabled, mock_backends_conf, mock_kube):
        """A secretRef whose Secret exists with all declared keys passes."""
        mock_enabled.return_value = ["dell-iscsi"]
        mock_backends_conf.return_value = {
            "dell-iscsi": {"name": "dell-iscsi", "protocol": "iscsi",
                           "k8s_storage_class": "none",
                           "secretRef": {"name": "esb-creds",
                                         "keys": {"san_login": "username",
                                                  "san_password": "password"}}},
        }
        secret = mock.Mock()
        secret.data = {"username": "YWRtaW4=", "password": "czNjcmV0"}
        mock_kube.return_value.kube_get_secret.return_value = secret
        # Should not raise.
        self.lifecycle._semantic_check_secretref()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.kubernetes.KubeOperator')
    @mock.patch('k8sapp_openstack.utils.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    def test_secretref_no_secretref_skipped(
        self, mock_enabled, mock_backends_conf, mock_kube
    ):
        """A backend without secretRef requires no Secret lookup."""
        mock_enabled.return_value = ["dell-iscsi"]
        mock_backends_conf.return_value = {
            "dell-iscsi": {"name": "dell-iscsi", "protocol": "iscsi",
                           "k8s_storage_class": "none"},
        }
        self.lifecycle._semantic_check_secretref()
        mock_kube.return_value.kube_get_secret.assert_not_called()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.kubernetes.KubeOperator')
    @mock.patch('k8sapp_openstack.utils.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    def test_secretref_missing_secret_blocked(
        self, mock_enabled, mock_backends_conf, mock_kube
    ):
        """A secretRef to a non-existent Secret blocks (ESB-only)."""
        mock_enabled.return_value = ["dell-iscsi"]
        mock_backends_conf.return_value = {
            "dell-iscsi": {"name": "dell-iscsi", "protocol": "iscsi",
                           "k8s_storage_class": "none",
                           "secretRef": {"name": "does-not-exist",
                                         "keys": {"san_login": "username"}}},
        }
        mock_kube.return_value.kube_get_secret.return_value = None
        try:
            self.lifecycle._semantic_check_secretref()
        except exception.LifecycleSemanticCheckException as e:
            self.assertIn("does-not-exist", str(e))
            self.assertIn("not found", str(e))
        else:
            self.fail("LifecycleSemanticCheckException was not raised")

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.kubernetes.KubeOperator')
    @mock.patch('k8sapp_openstack.utils.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    def test_secretref_missing_key_blocked(
        self, mock_enabled, mock_backends_conf, mock_kube
    ):
        """A secretRef whose Secret lacks a declared key blocks (ESB-only)."""
        mock_enabled.return_value = ["dell-iscsi"]
        mock_backends_conf.return_value = {
            "dell-iscsi": {"name": "dell-iscsi", "protocol": "iscsi",
                           "k8s_storage_class": "none",
                           "secretRef": {"name": "esb-creds",
                                         "keys": {"san_login": "username",
                                                  "san_password": "password"}}},
        }
        secret = mock.Mock()
        secret.data = {"username": "YWRtaW4="}  # missing 'password'
        mock_kube.return_value.kube_get_secret.return_value = secret
        try:
            self.lifecycle._semantic_check_secretref()
        except exception.LifecycleSemanticCheckException as e:
            self.assertIn("password", str(e))
        else:
            self.fail("LifecycleSemanticCheckException was not raised")

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.kubernetes.KubeOperator')
    @mock.patch('k8sapp_openstack.utils.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    def test_secretref_empty_secret_reports_missing_keys(
        self, mock_enabled, mock_backends_conf, mock_kube
    ):
        """An existing but empty Secret (data is None) reports the missing
        keys instead of misreporting the Secret as 'not found'."""
        mock_enabled.return_value = ["dell-iscsi"]
        mock_backends_conf.return_value = {
            "dell-iscsi": {"name": "dell-iscsi", "protocol": "iscsi",
                           "k8s_storage_class": "none",
                           "secretRef": {"name": "my-secret",
                                         "keys": {"san_login": "username",
                                                  "san_password": "password"}}},
        }
        secret = mock.Mock()
        secret.data = None  # Secret exists but has no data.
        mock_kube.return_value.kube_get_secret.return_value = secret
        try:
            self.lifecycle._semantic_check_secretref()
        except exception.LifecycleSemanticCheckException as e:
            msg = str(e)
            self.assertNotIn("not found", msg)
            self.assertIn("missing required key(s)", msg)
            self.assertIn("password", msg)
            self.assertIn("username", msg)
        else:
            self.fail("LifecycleSemanticCheckException was not raised")

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.kubernetes.KubeOperator')
    @mock.patch('k8sapp_openstack.utils.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    def test_secretref_custom_namespace(
        self, mock_enabled, mock_backends_conf, mock_kube
    ):
        """A custom secretRef.namespace is honored on the Secret lookup."""
        mock_enabled.return_value = ["dell-iscsi"]
        mock_backends_conf.return_value = {
            "dell-iscsi": {"name": "dell-iscsi", "protocol": "iscsi",
                           "k8s_storage_class": "none",
                           "secretRef": {"name": "esb-creds",
                                         "namespace": "custom-ns",
                                         "keys": {"san_login": "username"}}},
        }
        secret = mock.Mock()
        secret.data = {"username": "YWRtaW4="}
        mock_kube.return_value.kube_get_secret.return_value = secret
        self.lifecycle._semantic_check_secretref()
        mock_kube.return_value.kube_get_secret.assert_called_once_with(
            "esb-creds", "custom-ns")

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.kubernetes.KubeOperator')
    @mock.patch('k8sapp_openstack.utils.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    def test_secretref_missing_name_blocked(
        self, mock_enabled, mock_backends_conf, mock_kube
    ):
        """A secretRef without a 'name' field blocks (ESB-only)."""
        mock_enabled.return_value = ["dell-iscsi"]
        mock_backends_conf.return_value = {
            "dell-iscsi": {"name": "dell-iscsi", "protocol": "iscsi",
                           "k8s_storage_class": "none",
                           "secretRef": {"keys": {"san_login": "username"}}},
        }
        try:
            self.lifecycle._semantic_check_secretref()
        except exception.LifecycleSemanticCheckException as e:
            self.assertIn("name", str(e))
        else:
            self.fail("LifecycleSemanticCheckException was not raised")

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.kubernetes.KubeOperator')
    @mock.patch('k8sapp_openstack.utils.get_backends_conf')
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    def test_secretref_blocks_even_with_strict_available(
        self, mock_enabled, mock_backends_conf, mock_kube
    ):
        """secretRef failures always block, regardless of strict availability
        (the check no longer takes a strict flag)."""
        mock_enabled.return_value = ["dell-iscsi"]
        mock_backends_conf.return_value = {
            "dell-iscsi": {"name": "dell-iscsi", "protocol": "iscsi",
                           "k8s_storage_class": "none",
                           "secretRef": {"name": "does-not-exist",
                                         "keys": {"san_login": "username"}}},
        }
        mock_kube.return_value.kube_get_secret.return_value = None
        self.assertRaises(
            exception.LifecycleSemanticCheckException,
            self.lifecycle._semantic_check_secretref)

    # ------------------------------------------------------------------
    # _semantic_check_storage_backends (generic orchestrator)
    # ------------------------------------------------------------------
    @mock.patch.object(lifecycle_openstack.OpenstackAppLifecycleOperator,
                       '_semantic_check_backend_storageclass')
    @mock.patch.object(lifecycle_openstack.OpenstackAppLifecycleOperator,
                       '_semantic_check_secretref')
    @mock.patch.object(lifecycle_openstack.OpenstackAppLifecycleOperator,
                       '_semantic_check_storage_backend_available')
    @mock.patch.object(lifecycle_openstack.OpenstackAppLifecycleOperator,
                       '_is_strict_backend_available')
    def test_storage_backends_orchestrates_all_subchecks(
        self, mock_probe, mock_available, mock_secretref,
        mock_storageclass
    ):
        """The generic orchestrator probes strict availability once, shares it
        with the availability check, and runs every storage-backend sub-check
        (including StorageClass resolution/immutability)."""
        mock_probe.return_value = (True, "status-str")
        self.lifecycle._semantic_check_storage_backends()
        mock_probe.assert_called_once_with()
        mock_available.assert_called_once_with(True, "status-str")
        mock_secretref.assert_called_once_with()
        mock_storageclass.assert_called_once_with()


class TestSemanticCheckNetappSanStorageclasses(
        OpenstackAppLifecycleOperatorTest):
    """Tests for _semantic_check_netapp_san_storageclasses."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _both_san_enabled(self):
        return {
            app_constants.NETAPP_NFS_BACKEND_NAME: False,
            app_constants.NETAPP_ISCSI_BACKEND_NAME: True,
            app_constants.NETAPP_FC_BACKEND_NAME: True,
        }

    def _iscsi_only(self):
        return {
            app_constants.NETAPP_NFS_BACKEND_NAME: False,
            app_constants.NETAPP_ISCSI_BACKEND_NAME: True,
            app_constants.NETAPP_FC_BACKEND_NAME: False,
        }

    def _fc_only(self):
        return {
            app_constants.NETAPP_NFS_BACKEND_NAME: False,
            app_constants.NETAPP_ISCSI_BACKEND_NAME: False,
            app_constants.NETAPP_FC_BACKEND_NAME: True,
        }

    def _no_san(self):
        return {
            app_constants.NETAPP_NFS_BACKEND_NAME: True,
            app_constants.NETAPP_ISCSI_BACKEND_NAME: False,
            app_constants.NETAPP_FC_BACKEND_NAME: False,
        }

    # ------------------------------------------------------------------
    # Short-circuit cases (check should pass without kubectl)
    # ------------------------------------------------------------------

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_netapp_backends')
    def test_only_iscsi_enabled_skips_check(self, mock_backends):
        """Single iSCSI backend — sanType not required, no kubectl call."""
        mock_backends.return_value = self._iscsi_only()
        with mock.patch(
            'k8sapp_openstack.utils.send_cmd_read_response'
        ) as mock_cmd:
            self.lifecycle._semantic_check_netapp_san_storageclasses()
            mock_cmd.assert_not_called()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_netapp_backends')
    def test_only_fc_enabled_skips_check(self, mock_backends):
        """Single FC backend — sanType not required, no kubectl call."""
        mock_backends.return_value = self._fc_only()
        with mock.patch(
            'k8sapp_openstack.utils.send_cmd_read_response'
        ) as mock_cmd:
            self.lifecycle._semantic_check_netapp_san_storageclasses()
            mock_cmd.assert_not_called()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_netapp_backends')
    def test_no_san_backends_skips_check(self, mock_backends):
        """No SAN backends enabled — check is skipped entirely."""
        mock_backends.return_value = self._no_san()
        with mock.patch(
            'k8sapp_openstack.utils.send_cmd_read_response'
        ) as mock_cmd:
            self.lifecycle._semantic_check_netapp_san_storageclasses()
            mock_cmd.assert_not_called()

    # ------------------------------------------------------------------
    # Both SAN enabled — kubectl output variations
    # ------------------------------------------------------------------

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_netapp_backends')
    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response', return_value='')
    def test_no_ontap_san_storageclasses_passes(self, mock_cmd, mock_backends):
        """Both SAN enabled but no ontap-san StorageClasses — check passes."""
        mock_backends.return_value = self._both_san_enabled()
        self.lifecycle._semantic_check_netapp_san_storageclasses()
        mock_cmd.assert_called_once()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_netapp_backends')
    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response',
                return_value='netapp-iscsi\tiscsi\nnetapp-fc\tfcp\n')
    def test_both_san_with_san_type_passes(self, mock_cmd, mock_backends):
        """Both SAN enabled and StorageClasses have sanType — check passes."""
        mock_backends.return_value = self._both_san_enabled()
        self.lifecycle._semantic_check_netapp_san_storageclasses()
        mock_cmd.assert_called_once()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_netapp_backends')
    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response',
                return_value='netapp-iscsi\tiscsi\n')
    def test_only_iscsi_san_type_missing_fc_raises(self, mock_cmd, mock_backends):
        """FC sanType absent — both must be present, so raises."""
        mock_backends.return_value = self._both_san_enabled()
        self.assertRaises(
            exception.LifecycleSemanticCheckException,
            self.lifecycle._semantic_check_netapp_san_storageclasses,
        )
        mock_cmd.assert_called_once()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_netapp_backends')
    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response',
                return_value='netapp-fc\tfcp\n')
    def test_only_fc_san_type_missing_iscsi_raises(self, mock_cmd, mock_backends):
        """iSCSI sanType absent — both must be present, so raises."""
        mock_backends.return_value = self._both_san_enabled()
        self.assertRaises(
            exception.LifecycleSemanticCheckException,
            self.lifecycle._semantic_check_netapp_san_storageclasses,
        )
        mock_cmd.assert_called_once()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_netapp_backends')
    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response',
                return_value='netapp-san\t\n')
    def test_both_san_no_san_type_raises(self, mock_cmd, mock_backends):
        """Both SAN enabled and no StorageClass defines sanType — raises."""
        mock_backends.return_value = self._both_san_enabled()
        self.assertRaises(
            exception.LifecycleSemanticCheckException,
            self.lifecycle._semantic_check_netapp_san_storageclasses,
        )
        mock_cmd.assert_called_once()

    # ------------------------------------------------------------------
    # kubectl failure — should warn and pass gracefully
    # ------------------------------------------------------------------

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.check_netapp_backends')
    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response',
                side_effect=Exception("kubectl unavailable"))
    def test_kubectl_failure_skips_gracefully(self, mock_cmd, mock_backends):
        """kubectl failure logs a warning and does not raise."""
        mock_backends.return_value = self._both_san_enabled()
        # Should not raise
        self.lifecycle._semantic_check_netapp_san_storageclasses()
        mock_cmd.assert_called_once()


class OpenstackAppAnsibleDeliveryTest(base.TestCase):
    """Unit tests for application-owned ansible playbook delivery.

    Covers the post_upload deploy hook, the single-generation retention cap,
    the rollback promote used by the update-recover path, and the full purge
    performed on application-delete.

    These exercise the real filesystem: ANSIBLE_DEPLOY_BASE is redirected to a
    temporary directory so the symlink rotation and directory pruning are
    verified as actually performed on disk rather than mocked away.
    """

    APP_NAME = 'stx-openstack'
    RELEASE = '26.10'
    PLAYBOOK = 'backup-restore/restore_openstack.yml'

    def setUp(self):
        super(OpenstackAppAnsibleDeliveryTest, self).setUp()
        self.lifecycle = lifecycle_openstack.OpenstackAppLifecycleOperator()

        self.tmp = tempfile.mkdtemp(prefix='ansible-delivery-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.deploy_base = os.path.join(self.tmp, 'opt-platform-ansible')
        self.scratch = os.path.join(self.tmp, 'scratch')
        os.makedirs(self.deploy_base)
        os.makedirs(self.scratch)

        base_patch = mock.patch.object(
            lifecycle_openstack.app_constants, 'ANSIBLE_DEPLOY_BASE',
            self.deploy_base)
        base_patch.start()
        self.addCleanup(base_patch.stop)

        version_patch = mock.patch.object(
            lifecycle_openstack.tsc, 'SW_VERSION', self.RELEASE)
        version_patch.start()
        self.addCleanup(version_patch.stop)

        self.app_base = os.path.join(
            self.deploy_base, self.RELEASE, self.APP_NAME)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _make_app(self, version, with_ansible=True):
        """Build an app whose inst_path mimics an extracted tarball."""
        inst_path = os.path.join(self.scratch, version)
        if with_ansible:
            playbook = os.path.join(
                inst_path, lifecycle_openstack.app_constants.
                ANSIBLE_TARBALL_SUBDIR, self.PLAYBOOK)
            os.makedirs(os.path.dirname(playbook), exist_ok=True)
            with open(playbook, 'w') as f:
                f.write('# playbook for {}\n'.format(version))
        else:
            os.makedirs(inst_path, exist_ok=True)

        app = mock.MagicMock()
        app.name = self.APP_NAME
        app.version = version
        app.inst_path = inst_path
        return app

    def _link(self, name):
        return os.path.join(self.app_base, name)

    def _link_target(self, name):
        return os.path.basename(os.readlink(self._link(name)))

    def _version_dirs(self):
        """Real version directories present, excluding tracking symlinks."""
        if not os.path.isdir(self.app_base):
            return []
        return sorted(
            e for e in os.listdir(self.app_base)
            if os.path.isdir(os.path.join(self.app_base, e))
            and not os.path.islink(os.path.join(self.app_base, e)))

    def _deploy(self, version):
        app = self._make_app(version)
        self.lifecycle._deploy_ansible(app)
        return app

    # ------------------------------------------------------------------
    # deploy
    # ------------------------------------------------------------------
    def test_deploy_ansible_success(self):
        """Playbooks land under <release>/<app>/<version>/ and current points
        at the deployed version.
        """
        self._deploy('1.0-1')

        deployed = os.path.join(self.app_base, '1.0-1', self.PLAYBOOK)
        self.assertTrue(os.path.isfile(deployed))
        self.assertTrue(os.path.islink(self._link('current')))
        self.assertEqual('1.0-1', self._link_target('current'))
        # Resolvable through the symlink, which is how the platform
        # delegation check reaches it.
        self.assertTrue(os.path.isfile(
            os.path.join(self._link('current'), self.PLAYBOOK)))
        # No rollback generation exists yet on a first deploy.
        self.assertFalse(os.path.lexists(self._link('previous')))

    def test_deploy_ansible_no_source(self):
        """A tarball without ansible/ is skipped without error and without
        creating any tree.
        """
        app = self._make_app('1.0-1', with_ansible=False)

        self.lifecycle._deploy_ansible(app)

        self.assertFalse(os.path.exists(self.app_base))

    def test_deploy_ansible_replaces_existing_version(self):
        """Re-deploying the same version succeeds and refreshes the content."""
        self._deploy('1.0-1')

        # Rewrite the source so the replacement is detectable.
        app = self._make_app('1.0-1')
        playbook = os.path.join(
            app.inst_path,
            lifecycle_openstack.app_constants.ANSIBLE_TARBALL_SUBDIR,
            self.PLAYBOOK)
        with open(playbook, 'w') as f:
            f.write('# redeployed\n')

        self.lifecycle._deploy_ansible(app)

        with open(os.path.join(self.app_base, '1.0-1', self.PLAYBOOK)) as f:
            self.assertEqual('# redeployed\n', f.read())
        self.assertEqual('1.0-1', self._link_target('current'))
        self.assertEqual(['1.0-1'], self._version_dirs())

    def test_deploy_ansible_atomic_on_copy_failure(self):
        """A copy failure leaves the previously deployed version and current
        untouched, and cleans the staging directory.
        """
        self._deploy('1.0-1')

        app = self._make_app('2.0-1')
        with mock.patch.object(lifecycle_openstack.shutil, 'copytree',
                               side_effect=OSError('disk full')):
            self.assertRaises(OSError, self.lifecycle._deploy_ansible, app)

        self.assertEqual('1.0-1', self._link_target('current'))
        self.assertEqual(['1.0-1'], self._version_dirs())
        # No staging directory left behind.
        self.assertEqual(
            [], [e for e in os.listdir(self.app_base)
                 if e.startswith('.2.0-1-')])

    def test_deploy_ansible_atomic_on_rename_failure(self):
        """A failed publish of 'current' cleans the staging pointer rather
        than leaving a stray current.new behind.
        """
        self._deploy('1.0-1')

        real_rename = os.rename

        def fail_link_swap(src, dst):
            if str(src).endswith('.new'):
                raise OSError('rename failed')
            return real_rename(src, dst)

        app = self._make_app('2.0-1')
        with mock.patch.object(lifecycle_openstack.os, 'rename',
                               side_effect=fail_link_swap):
            self.assertRaises(OSError, self.lifecycle._deploy_ansible, app)

        self.assertFalse(os.path.lexists(self._link('current.new')))
        # The prior version's tree survives, so a rollback target remains.
        self.assertIn('1.0-1', self._version_dirs())

    def test_post_upload_calls_deploy_ansible(self):
        """post_upload wires through to the playbook deploy."""
        app = self._make_app('1.0-1')

        with mock.patch.object(self.lifecycle,
                               '_post_upload_ldap_actions') as mock_ldap, \
                mock.patch.object(self.lifecycle,
                                  '_deploy_ansible') as mock_deploy:
            self.lifecycle.post_upload(mock.Mock(), mock.Mock(), app,
                                       mock.Mock())

        mock_ldap.assert_called_once_with(app)
        mock_deploy.assert_called_once_with(app)

    # ------------------------------------------------------------------
    # retention cap (one prior generation)
    # ------------------------------------------------------------------
    def test_deploy_ansible_rotates_current_to_previous(self):
        """The version being replaced becomes the rollback target."""
        self._deploy('1.0-1')
        self._deploy('2.0-1')

        self.assertEqual('2.0-1', self._link_target('current'))
        self.assertEqual('1.0-1', self._link_target('previous'))
        self.assertEqual(['1.0-1', '2.0-1'], self._version_dirs())

    def test_deploy_ansible_retention_capped_at_one_generation(self):
        """Repeated deploys never accumulate a third generation.

        The deploy hook keeps the version being replaced as the rollback
        target and prunes anything older, so even without the post-apply
        cleanup the tree never grows past two generations.
        """
        for version in ('1.0-1', '2.0-1', '3.0-1', '4.0-1'):
            self._deploy(version)

        self.assertEqual('4.0-1', self._link_target('current'))
        self.assertEqual('3.0-1', self._link_target('previous'))
        # Two directories, never three: 1.0-1 and 2.0-1 were pruned.
        self.assertEqual(['3.0-1', '4.0-1'], self._version_dirs())
        self.assertFalse(os.path.lexists(self._link('previous_previous')))

    # ------------------------------------------------------------------
    # post-apply cleanup: at rest only the running version remains
    # ------------------------------------------------------------------
    def _applied_hook_info(self, applied=True):
        hook_info = {LifecycleConstants.EXTRA: {
            LifecycleConstants.APP_APPLIED: applied,
            self.lifecycle.WAS_APPLIED: True,
        }}
        return hook_info

    def test_prune_previous_ansible_leaves_only_current(self):
        """REQ-3: after a successful apply no prior version remains on disk."""
        self._deploy('1.0-1')
        app = self._deploy('2.0-1')
        # Mid-update state: the replaced version is the rollback target.
        self.assertEqual('1.0-1', self._link_target('previous'))

        self.lifecycle._prune_previous_ansible(app)

        self.assertEqual('2.0-1', self._link_target('current'))
        self.assertFalse(os.path.lexists(self._link('previous')))
        self.assertEqual(['2.0-1'], self._version_dirs())
        # The running version stays resolvable through 'current'.
        self.assertTrue(os.path.isfile(
            os.path.join(self._link('current'), self.PLAYBOOK)))

    def test_prune_previous_ansible_no_previous_is_noop(self):
        """Nothing to drop after a first deploy."""
        app = self._deploy('1.0-1')

        self.lifecycle._prune_previous_ansible(app)

        self.assertEqual('1.0-1', self._link_target('current'))
        self.assertEqual(['1.0-1'], self._version_dirs())

    def test_prune_previous_ansible_never_deletes_running_version(self):
        """A pointer aliasing the running version must not delete its tree."""
        self._deploy('1.0-1')
        app = self._deploy('2.0-1')
        # Repoint 'previous' at the running version to model a bad state.
        os.unlink(self._link('previous'))
        os.symlink('2.0-1', self._link('previous'))

        self.lifecycle._prune_previous_ansible(app)

        self.assertFalse(os.path.lexists(self._link('previous')))
        self.assertEqual('2.0-1', self._link_target('current'))
        # Protected: the running version's tree survives.
        self.assertIn('2.0-1', self._version_dirs())
        self.assertTrue(os.path.isfile(
            os.path.join(self._link('current'), self.PLAYBOOK)))

    def test_post_apply_prunes_on_success(self):
        """A successful apply drops the retained generation."""
        app = self._deploy('1.0-1')

        with mock.patch.object(self.lifecycle,
                               '_prune_previous_ansible') as mock_prune, \
                mock.patch.object(self.lifecycle,
                                  '_delete_maridb_pvc_snapshots_if_exists'), \
                mock.patch(_DEX_REDIRECT), \
                mock.patch(_RECOVER_SERVERS):
            self.lifecycle.post_apply(mock.Mock(), mock.Mock(), app,
                                      self._applied_hook_info(applied=True))

        mock_prune.assert_called_once_with(app)

    def test_post_apply_does_not_prune_on_failure(self):
        """A failed apply leaves the rollback target in place."""
        app = self._deploy('1.0-1')

        with mock.patch.object(self.lifecycle,
                               '_prune_previous_ansible') as mock_prune, \
                mock.patch.object(self.lifecycle,
                                  '_delete_maridb_pvc_snapshots_if_exists'), \
                mock.patch(_DEX_REDIRECT), \
                mock.patch(_RECOVER_SERVERS):
            self.lifecycle.post_apply(mock.Mock(), mock.Mock(), app,
                                      self._applied_hook_info(applied=False))

        mock_prune.assert_not_called()

    def _manifest_hook_info(self, applied=True):
        return {LifecycleConstants.EXTRA: {
            LifecycleConstants.MANIFEST_APPLIED: applied,
        }}

    def test_post_apply_manifest_prunes_on_success(self):
        """The manifest hook prunes too: it is the only one of the two that
        fires on an application-update, which is the only path that creates a
        retained generation.
        """
        app = self._deploy('1.0-1')

        with mock.patch.object(self.lifecycle,
                               '_prune_previous_ansible') as mock_prune, \
                mock.patch.object(self.lifecycle,
                                  '_post_update_image_actions') as mock_img:
            self.lifecycle.post_apply_manifest(
                app, self._manifest_hook_info(applied=True))

        mock_prune.assert_called_once_with(app)
        mock_img.assert_called_once_with(app)

    def test_post_apply_manifest_does_not_prune_on_failure(self):
        """Unlike post_apply, this hook also fires when the manifest failed;
        a failed update must keep its rollback target.
        """
        app = self._deploy('1.0-1')

        with mock.patch.object(self.lifecycle,
                               '_prune_previous_ansible') as mock_prune, \
                mock.patch.object(self.lifecycle,
                                  '_post_update_image_actions'):
            self.lifecycle.post_apply_manifest(
                app, self._manifest_hook_info(applied=False))

        mock_prune.assert_not_called()

    def test_post_apply_manifest_prune_failure_does_not_raise(self):
        """Cleanup failure must not fail an otherwise successful apply."""
        app = self._deploy('1.0-1')

        with mock.patch.object(self.lifecycle, '_prune_previous_ansible',
                               side_effect=OSError('boom')), \
                mock.patch.object(self.lifecycle,
                                  '_post_update_image_actions'):
            # Must not raise.
            self.lifecycle.post_apply_manifest(
                app, self._manifest_hook_info(applied=True))

    def test_prune_previous_ansible_is_idempotent(self):
        """Both post_apply and post_apply_manifest fire on a plain apply, so
        the prune runs twice; the second call must be a no-op.
        """
        self._deploy('1.0-1')
        app = self._deploy('2.0-1')

        self.lifecycle._prune_previous_ansible(app)
        # Second call, as happens when both post hooks fire.
        self.lifecycle._prune_previous_ansible(app)

        self.assertEqual('2.0-1', self._link_target('current'))
        self.assertFalse(os.path.lexists(self._link('previous')))
        self.assertEqual(['2.0-1'], self._version_dirs())

    def test_prune_previous_failure_does_not_break_apply(self):
        """Cleanup failure must not fail an otherwise successful apply."""
        app = self._deploy('1.0-1')

        with mock.patch.object(self.lifecycle, '_prune_previous_ansible',
                               side_effect=OSError('boom')), \
                mock.patch.object(self.lifecycle,
                                  '_delete_maridb_pvc_snapshots_if_exists'), \
                mock.patch(_DEX_REDIRECT), \
                mock.patch(_RECOVER_SERVERS):
            # Must not raise.
            self.lifecycle.post_apply(mock.Mock(), mock.Mock(), app,
                                      self._applied_hook_info(applied=True))

    def test_deploy_ansible_prunes_dangling_previous(self):
        """A previous pointer whose tree is already gone is dropped without
        error and does not block the rotation.
        """
        self._deploy('1.0-1')
        self._deploy('2.0-1')
        # Simulate the retained tree having been removed out from under us.
        shutil.rmtree(os.path.join(self.app_base, '1.0-1'))

        self._deploy('3.0-1')

        self.assertEqual('3.0-1', self._link_target('current'))
        self.assertEqual('2.0-1', self._link_target('previous'))
        self.assertEqual(['2.0-1', '3.0-1'], self._version_dirs())

    # ------------------------------------------------------------------
    # undeploy / rollback promote
    # ------------------------------------------------------------------
    def test_undeploy_ansible_promotes_previous(self):
        """Removing the active version promotes the rollback target.

        This is the update-recover path: sysinv applies the old version
        through FluxCD without re-running the upload hook, so this promote is
        what leaves the recovered version with playbooks on disk.
        """
        self._deploy('1.0-1')
        failed_app = self._deploy('2.0-1')

        self.lifecycle._undeploy_ansible(failed_app)

        self.assertEqual('1.0-1', self._link_target('current'))
        self.assertEqual(['1.0-1'], self._version_dirs())
        self.assertTrue(os.path.isfile(
            os.path.join(self._link('current'), self.PLAYBOOK)))
        self.assertFalse(os.path.lexists(self._link('previous')))

    def test_undeploy_ansible_no_previous_leaves_no_dangling_current(self):
        """With nothing to promote, current is removed rather than left
        pointing at a deleted tree.
        """
        app = self._deploy('1.0-1')

        self.lifecycle._undeploy_ansible(app)

        self.assertFalse(os.path.lexists(self._link('current')))
        self.assertEqual([], self._version_dirs())

    def test_undeploy_ansible_drops_dangling_previous(self):
        """A dangling rollback pointer is dropped, not promoted, so current
        never resolves to a missing tree.
        """
        self._deploy('1.0-1')
        failed_app = self._deploy('2.0-1')
        shutil.rmtree(os.path.join(self.app_base, '1.0-1'))

        self.lifecycle._undeploy_ansible(failed_app)

        self.assertFalse(os.path.lexists(self._link('current')))
        self.assertFalse(os.path.lexists(self._link('previous')))

    def test_undeploy_ansible_other_version_leaves_pointers_intact(self):
        """Undeploying a version that is not active leaves the pointer chain
        alone.
        """
        self._deploy('1.0-1')
        self._deploy('2.0-1')

        stale = self._make_app('1.0-1')
        self.lifecycle._undeploy_ansible(stale)

        self.assertEqual('2.0-1', self._link_target('current'))
        self.assertEqual('1.0-1', self._link_target('previous'))
        self.assertEqual(['2.0-1'], self._version_dirs())

    def test_undeploy_ansible_missing_version_is_noop(self):
        """Undeploying a version that was never deployed does not raise."""
        self._deploy('1.0-1')

        never = self._make_app('9.9-9')
        self.lifecycle._undeploy_ansible(never)

        self.assertEqual('1.0-1', self._link_target('current'))
        self.assertEqual(['1.0-1'], self._version_dirs())

    # ------------------------------------------------------------------
    # purge on application-delete
    # ------------------------------------------------------------------
    def test_purge_ansible_removes_whole_tree(self):
        """application-delete leaves no version directory and no pointer."""
        self._deploy('1.0-1')
        self._deploy('2.0-1')
        app = self._make_app('2.0-1')

        self.lifecycle._purge_ansible(app)

        self.assertFalse(os.path.exists(self.app_base))

    def test_purge_ansible_missing_tree_is_noop(self):
        """Purging when nothing was deployed does not raise."""
        app = self._make_app('1.0-1', with_ansible=False)

        self.lifecycle._purge_ansible(app)

        self.assertFalse(os.path.exists(self.app_base))

    def test_pre_delete_purges_instead_of_undeploying(self):
        """pre_delete removes the whole tree, not just the active version."""
        app = self._make_app('1.0-1')

        with mock.patch.object(self.lifecycle,
                               '_purge_ansible') as mock_purge, \
                mock.patch.object(self.lifecycle,
                                  '_undeploy_ansible') as mock_undeploy:
            self.lifecycle.pre_delete(mock.Mock(), app)

        mock_purge.assert_called_once_with(app)
        mock_undeploy.assert_not_called()

    def test_purge_then_redeploy_restores_tree(self):
        """A re-upload after delete rebuilds the tree, which is what keeps the
        documented remove/delete/upload restore procedure working.
        """
        self._deploy('1.0-1')
        self.lifecycle._purge_ansible(self._make_app('1.0-1'))

        self._deploy('1.0-1')

        self.assertEqual('1.0-1', self._link_target('current'))
        self.assertTrue(os.path.isfile(
            os.path.join(self._link('current'), self.PLAYBOOK)))

    # ------------------------------------------------------------------
    # downgrade uses the rollback promote, not the purge
    # ------------------------------------------------------------------
    def test_pre_downgrade_undeploys_single_version(self):
        """pre_downgrade retires one version rather than purging the tree."""
        app = self._make_app('2.0-1')

        with mock.patch.object(self.lifecycle,
                               '_undeploy_ansible') as mock_undeploy, \
                mock.patch.object(self.lifecycle,
                                  '_purge_ansible') as mock_purge:
            self.lifecycle.pre_downgrade(mock.Mock(), app)

        mock_undeploy.assert_called_once_with(app)
        mock_purge.assert_not_called()

    # ------------------------------------------------------------------
    # dispatch contract: a hook is only reachable when type, operation and
    # timing all match what sysinv sends. These pin the combinations so a
    # mis-registered hook fails here instead of silently never running.
    # ------------------------------------------------------------------
    def _dispatch(self, lifecycle_type, timing, operation):
        hook_info = mock.MagicMock()
        hook_info.lifecycle_type = lifecycle_type
        hook_info.relative_timing = timing
        hook_info.operation = operation
        return hook_info

    def test_downgrade_dispatched_as_resource_pre_reaches_pre_downgrade(self):
        """sysinv sends APP_DOWNGRADE_OP as RESOURCE + PRE.

        Verified against sysinv/conductor/kube_app.py, which sets
        lifecycle_type=RESOURCE and relative_timing=PRE on the downgrade hook.
        Registering it as OPERATION or POST makes it unreachable.
        """
        hook_info = self._dispatch(
            LifecycleConstants.APP_LIFECYCLE_TYPE_RESOURCE,
            LifecycleConstants.APP_LIFECYCLE_TIMING_PRE,
            constants.APP_DOWNGRADE_OP)
        app = self._make_app('2.0-1')

        with mock.patch.object(self.lifecycle, 'pre_downgrade') as mock_hook:
            self.lifecycle.app_lifecycle_actions(
                mock.Mock(), mock.Mock(), mock.Mock(), app, hook_info)

        mock_hook.assert_called_once()

    def test_delete_dispatched_as_operation_pre_reaches_pre_delete(self):
        """sysinv sends APP_DELETE_OP as OPERATION + PRE."""
        hook_info = self._dispatch(
            LifecycleConstants.APP_LIFECYCLE_TYPE_OPERATION,
            LifecycleConstants.APP_LIFECYCLE_TIMING_PRE,
            constants.APP_DELETE_OP)
        app = self._make_app('1.0-1')

        with mock.patch.object(self.lifecycle, 'pre_delete') as mock_hook:
            self.lifecycle.app_lifecycle_actions(
                mock.Mock(), mock.Mock(), mock.Mock(), app, hook_info)

        mock_hook.assert_called_once()

    def test_upload_dispatched_as_operation_post_reaches_post_upload(self):
        """sysinv sends APP_UPLOAD_OP as OPERATION + POST."""
        hook_info = self._dispatch(
            LifecycleConstants.APP_LIFECYCLE_TYPE_OPERATION,
            LifecycleConstants.APP_LIFECYCLE_TIMING_POST,
            constants.APP_UPLOAD_OP)
        app = self._make_app('1.0-1')

        with mock.patch.object(self.lifecycle, 'post_upload') as mock_hook:
            self.lifecycle.app_lifecycle_actions(
                mock.Mock(), mock.Mock(), mock.Mock(), app, hook_info)

        mock_hook.assert_called_once()
