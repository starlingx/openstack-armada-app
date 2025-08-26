#
# Copyright (c) 2022-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm.lifecycle_constants import LifecycleConstants
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.lifecycle import lifecycle_openstack


EXTENDED_VSWITCH_ALLOWED_COMBINATIONS = (app_constants.VSWITCH_ALLOWED_COMBINATIONS +
                                        [{"other-vswitch=enabled"}])


class OpenstackAppLifecycleOperatorTest(dbbase.BaseHostTestCase):
    def setUp(self):
        super(OpenstackAppLifecycleOperatorTest, self).setUp()
        self.lifecycle = lifecycle_openstack.OpenstackAppLifecycleOperator()

    def _rook_ceph_backend_available(self, ceph_type: str =
                                     constants.SB_TYPE_CEPH):
        return ceph_type == constants.SB_TYPE_CEPH_ROOK

    def _ceph_backend_available(self, ceph_type: str =
                                     constants.SB_TYPE_CEPH):
        return ceph_type == constants.SB_TYPE_CEPH

    @mock.patch('k8sapp_openstack.utils.is_rook_ceph_api_available',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils.get_ceph_fsid',
                return_value='aa8c8da0-47de-4fad-8b5d-2c06be236fc8')
    @mock.patch('k8sapp_openstack.utils.is_ceph_backend_available')
    def test_semantic_check_storage_backend_available_rook(
        self,
        mock_is_ceph_backend_available,
        mock_get_ceph_fsid,
        mock_is_rook_ceph_api_available
    ):
        """ Test _semantic_check_storage_backend_available for rook ceph
        backend, api and fsid available.
        """
        mock_is_ceph_backend_available.side_effect = \
            self._rook_ceph_backend_available
        self.lifecycle._semantic_check_storage_backend_available()
        mock_is_ceph_backend_available.assert_called()
        mock_get_ceph_fsid.assert_called()
        mock_is_rook_ceph_api_available.assert_called()

    @mock.patch('k8sapp_openstack.utils.get_ceph_fsid',
                return_value='aa8c8da0-47de-4fad-8b5d-2c06be236fc8')
    @mock.patch('k8sapp_openstack.utils.is_ceph_backend_available')
    def test_semantic_check_storage_backend_available_ceph(
        self,
        mock_is_ceph_backend_available,
        mock_get_ceph_fsid
    ):
        """ Test _semantic_check_storage_backend_available for host ceph
        backend and fsid available.
        """
        mock_is_ceph_backend_available.side_effect = \
            self._ceph_backend_available
        self.lifecycle._semantic_check_storage_backend_available()
        mock_is_ceph_backend_available.assert_called()
        mock_get_ceph_fsid.assert_called()

    @mock.patch('k8sapp_openstack.utils.get_ceph_fsid', return_value=None)
    @mock.patch('k8sapp_openstack.utils.is_ceph_backend_available')
    def test_semantic_check_storage_backend_available_fsid_unavailable(
        self,
        mock_is_ceph_backend_available,
        mock_get_ceph_fsid
    ):
        """ Test _semantic_check_storage_backend_available for host ceph
        available and fsid unavailable.
        """
        mock_is_ceph_backend_available.side_effect = \
            self._ceph_backend_available
        try:
            self.lifecycle._semantic_check_storage_backend_available()
        except exception.LifecycleSemanticCheckException:
            pass  # the exception is the expected result
        else:
            self.fail("LifecycleSemanticCheckException was not raised")
        mock_get_ceph_fsid.assert_called()

    @mock.patch('k8sapp_openstack.utils.get_ceph_fsid', return_value=None)
    @mock.patch('k8sapp_openstack.utils.is_ceph_backend_available',
                side_effect=[False, False])
    def test_semantic_check_storage_backend_available_no_backends(self, *_):
        """ Test _semantic_check_storage_backend_available for both ceph
        backends not available.
        """
        try:
            self.lifecycle._semantic_check_storage_backend_available()
        except exception.LifecycleSemanticCheckException:
            pass  # the exception is the expected result
        else:
            self.fail("LifecycleSemanticCheckException was not raised")

    @mock.patch('k8sapp_openstack.utils.force_app_reconciliation')
    @mock.patch('k8sapp_openstack.utils.delete_kubernetes_resource')
    @mock.patch('k8sapp_openstack.utils.get_app_version_list',
                return_value=['25.03-0', '25.09-0'])
    def test__recover_app_resources_failed_update(
        self,
        mock_get_app_version_list,
        mock_delete_kubernetes_resource,
        mock_force_app_reconciliation
    ):
        """Test _recover_app_resources_failed_update for the app update
        operation
        """
        app_op = mock.MagicMock()
        app = mock.MagicMock()
        app.name = 'stx-openstack'
        app.version = '25.09-0'
        app.sync_imgfile = ("/opt/platform/fluxcd/<stx version>/stx-openstack/"
                            "25.03-0/stx-openstack-images.yaml")

        self.lifecycle._recover_app_resources_failed_update(app_op, app)

        app_op._deregister_app_abort.assert_called_once_with(app.name)
        mock_get_app_version_list.assert_called_once()
        mock_delete_kubernetes_resource.assert_called_once_with(
            resource_type='helmrelease',
            resource_name='mariadb'
        )
        mock_force_app_reconciliation.assert_called_once()

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.app_utils')
    def test__post_apply(self, mock_app_utils, *_):
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
            calls.append(mock.call(snapshot_name))

        mock_app_utils.get_number_of_controllers.return_value = number_of_controllers

        self.lifecycle.post_apply(context, conductor_obj, None, hook_info)

        conductor_obj._update_config_for_stx_openstack.assert_called_once_with(context)
        conductor_obj._update_radosgw_config.assert_called_once_with(context)

        mock_app_utils.delete_snapshot.assert_has_calls(calls)

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
        app_op = mock.Mock()

        self.lifecycle._recover_backup_snapshot = mock.Mock()
        self.lifecycle._recover_app_resources_failed_update = mock.Mock()

        self.lifecycle._recover_actions(app_op, app)

        self.lifecycle._recover_backup_snapshot.assert_called_once_with(app)
        self.lifecycle._recover_app_resources_failed_update.\
            assert_called_once_with(app_op, app)

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

        self.lifecycle._pre_update_actions = mock.Mock()
        self.lifecycle._post_update_image_actions = mock.Mock()

        mocked_methods = [
            self.lifecycle.pre_apply,
            self.lifecycle.post_apply,
            self.lifecycle.pre_remove,
            self.lifecycle.post_remove,
            self.lifecycle._create_app_specific_resources_pre_apply,
            self.lifecycle._delete_app_specific_resources_post_remove,
            self.lifecycle._recover_actions,
            mock_lifecycle_utils.create_rbd_provisioner_secrets,
            mock_lifecycle_utils.delete_rbd_provisioner_secrets,
            self.lifecycle._semantic_check_evaluate_app_reapply,
            self.lifecycle._pre_apply_check,
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

        rbd_cases = [
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_RBD,
                    operation=constants.APP_APPLY_OP,
                    relative_timing=LifecycleConstants.APP_LIFECYCLE_TIMING_PRE,
                ),
                'assertions': [
                    mock_lifecycle_utils.create_rbd_provisioner_secrets.assert_called_once,
                    mock_lifecycle_utils.delete_rbd_provisioner_secrets.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=LifecycleConstants.APP_LIFECYCLE_TYPE_RBD,
                    operation=constants.APP_REMOVE_OP,
                    relative_timing=LifecycleConstants.APP_LIFECYCLE_TIMING_POST,
                ),
                'assertions': [
                    mock_lifecycle_utils.create_rbd_provisioner_secrets.assert_not_called,
                    mock_lifecycle_utils.delete_rbd_provisioner_secrets.assert_called_once,
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
                    self.lifecycle._post_update_image_actions.assert_not_called,
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
                    self.lifecycle._post_update_image_actions.assert_called,
                ]
            },
        ]

        cases = operation_cases + resource_cases + rbd_cases + semantic_cases + manifest_cases

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

    @mock.patch('k8sapp_openstack.helpers.ldap.check_group', return_value=False)
    @mock.patch('k8sapp_openstack.helpers.ldap.add_group', return_value=True)
    @mock.patch('k8sapp_openstack.utils.create_clients_working_directory', return_value=True)
    @mock.patch('k8sapp_openstack.utils.get_clients_working_directory', return_value='/custom/path')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.lifecycle_utils.create_local_registry_secrets')
    @mock.patch('sysinv.common.kubernetes.KubeOperator')
    def test_create_app_specific_resources_pre_apply_success(
            self,
            mock_kube_operator,
            mock_create_local_registry_secrets,
            mock_get_working_dir,
            mock_create_dir,
            mock_add_group,
            mock_check_group):
        """ Test the pre-apply actions for creating app-specific resources. """

        app_op = mock.Mock()
        app = mock.Mock(name='test_app', version='1.0')
        hook_info = mock.Mock()

        mock_kube = mock_kube_operator.return_value
        mock_kube.kube_get_config_map.return_value = True
        mock_kube.kube_read_config_map.return_value = mock.Mock()

        self.lifecycle._create_app_specific_resources_pre_apply(app_op, app, hook_info)

        mock_create_local_registry_secrets.assert_called_once()
        mock_kube.kube_delete_config_map.assert_called_once()
        mock_kube.kube_create_config_map.assert_called_once()
        mock_check_group.assert_called_once()
        mock_add_group.assert_called_once()
        mock_create_dir.assert_called_once_with(path='/custom/path')

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
            mock_check_group):
        """ Test the pre-apply actions for creating app-specific resources with a failure. """

        mock_kube = mock_kube_operator.return_value
        mock_kube.kube_get_config_map.return_value = True
        mock_kube.kube_read_config_map.return_value = False

        app_op = mock.Mock()
        app = mock.Mock(name='test_app', version='1.0')
        hook_info = mock.Mock()

        self.assertRaises(
            exception.LifecycleMissingInfo,
            self.lifecycle._create_app_specific_resources_pre_apply,
            app_op,
            app,
            hook_info
        )

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.lifecycle_utils')
    @mock.patch(
        'k8sapp_openstack.lifecycle.lifecycle_openstack.OpenstackAppLifecycleOperator._post_remove_ldap_actions'
    )
    def test_delete_app_specific_resources_post_remove(
            self,
            mock_post_remove_ldap_actions,
            mock_lifecycle_utils):
        """ Test the post-remove actions for deleting app-specific resources. """

        app_op = mock.Mock()
        app = mock.Mock()
        hook_info = mock.Mock()

        self.lifecycle._delete_app_specific_resources_post_remove(app_op, app, hook_info)

        mock_lifecycle_utils.delete_local_registry_secrets.assert_called_once()
        mock_lifecycle_utils.delete_persistent_volume_claim.assert_called_once()
        mock_lifecycle_utils.delete_configmap.assert_called_once()
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
