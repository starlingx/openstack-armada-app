#
# Copyright (c) 2022-2024 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.common import constants
from sysinv.helm.lifecycle_constants import LifecycleConstants
from sysinv.tests.db import base as dbbase

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.lifecycle import lifecycle_openstack


class OpenstackAppLifecycleOperatorTest(dbbase.ControllerHostTestCase):
    def setUp(self):
        super(OpenstackAppLifecycleOperatorTest, self).setUp()
        self.lifecycle = lifecycle_openstack.OpenstackAppLifecycleOperator()

    @mock.patch("k8sapp_openstack.utils.is_openstack_https_ready", return_value=False)
    def test__semantic_check_openstack_https_not_ready(self, *_):
        self.assertFalse(self.lifecycle._semantic_check_openstack_https_ready())

    @mock.patch("k8sapp_openstack.utils.is_openstack_https_ready", return_value=True)
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
    def test__semantic_check_openstack_https_ready(self, *_):
        self.assertTrue(self.lifecycle._semantic_check_openstack_https_ready())

    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.helm_utils')
    @mock.patch('k8sapp_openstack.lifecycle.lifecycle_openstack.app_utils')
    def test__recover_app_resources_failed_update(self, mock_app_utils, mock_helm_utils, *_):
        release = 'ingress'
        patch = {"spec": {"suspend": False}}

        release_failed = 'ingress-nginx-openstack'
        patch_failed = {"spec": {"suspend": True}}

        calls = [
            mock.call(
                release, patch
            ),
            mock.call(
                release_failed, patch_failed,
            )
        ]

        self.lifecycle._recover_app_resources_failed_update()

        mock_app_utils.update_helmrelease.assert_has_calls(calls)
        mock_helm_utils.delete_helm_release.assert_called_once_with(
            release=release_failed, namespace=app_constants.HELM_NS_OPENSTACK
        )

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

    def test__pre_update_actions(self, *_):
        app = mock.Mock()

        self.lifecycle._pre_update_backup_actions = mock.Mock()
        self.lifecycle._pre_update_cleanup_actions = mock.Mock()

        self.lifecycle._pre_update_actions(app)

        self.lifecycle._pre_update_backup_actions.assert_called_once_with(app)
        self.lifecycle._pre_update_cleanup_actions.assert_called_once()

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
        app = mock.Mock()

        self.lifecycle._recover_backup_snapshot = mock.Mock()
        self.lifecycle._recover_app_resources_failed_update = mock.Mock()

        self.lifecycle._recover_actions(app)

        self.lifecycle._recover_backup_snapshot.assert_called_once_with(app)
        self.lifecycle._recover_app_resources_failed_update.assert_called_once()

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
        self.lifecycle._pre_manual_apply_check = mock.Mock()

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
            self.lifecycle._pre_manual_apply_check,
            self.lifecycle._pre_update_actions,
            self.lifecycle._post_update_image_actions,
        ]

        operation_cases = [
            {
                'hook_info': mock.Mock(
                    lifecycle_type=constants.APP_LIFECYCLE_TYPE_OPERATION,
                    operation=constants.APP_APPLY_OP,
                    relative_timing=constants.APP_LIFECYCLE_TIMING_PRE,
                ),
                'assertions': [
                    self.lifecycle.pre_apply.assert_called_once,
                    self.lifecycle.post_apply.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=constants.APP_LIFECYCLE_TYPE_OPERATION,
                    operation=constants.APP_APPLY_OP,
                    relative_timing=constants.APP_LIFECYCLE_TIMING_POST,
                ),
                'assertions': [
                    self.lifecycle.pre_apply.assert_not_called,
                    self.lifecycle.post_apply.assert_called_once,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=constants.APP_LIFECYCLE_TYPE_OPERATION,
                    operation=constants.APP_REMOVE_OP,
                    relative_timing=constants.APP_LIFECYCLE_TIMING_PRE,
                ),
                'assertions': [
                    self.lifecycle.pre_remove.assert_called,
                    self.lifecycle.post_remove.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=constants.APP_LIFECYCLE_TYPE_OPERATION,
                    operation=constants.APP_REMOVE_OP,
                    relative_timing=constants.APP_LIFECYCLE_TIMING_POST,
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
                    lifecycle_type=constants.APP_LIFECYCLE_TYPE_RESOURCE,
                    operation=constants.APP_APPLY_OP,
                    relative_timing=constants.APP_LIFECYCLE_TIMING_PRE,
                ),
                'assertions': [
                    self.lifecycle._create_app_specific_resources_pre_apply.assert_called_once,
                    self.lifecycle._delete_app_specific_resources_post_remove.assert_not_called,
                    self.lifecycle._recover_actions.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=constants.APP_LIFECYCLE_TYPE_RESOURCE,
                    operation=constants.APP_REMOVE_OP,
                    relative_timing=constants.APP_LIFECYCLE_TIMING_POST,
                ),
                'assertions': [
                    self.lifecycle._create_app_specific_resources_pre_apply.assert_not_called,
                    self.lifecycle._delete_app_specific_resources_post_remove.assert_called_once,
                    self.lifecycle._recover_actions.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=constants.APP_LIFECYCLE_TYPE_RESOURCE,
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
                    lifecycle_type=constants.APP_LIFECYCLE_TYPE_RBD,
                    operation=constants.APP_APPLY_OP,
                    relative_timing=constants.APP_LIFECYCLE_TIMING_PRE,
                ),
                'assertions': [
                    mock_lifecycle_utils.create_rbd_provisioner_secrets.assert_called_once,
                    mock_lifecycle_utils.delete_rbd_provisioner_secrets.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=constants.APP_LIFECYCLE_TYPE_RBD,
                    operation=constants.APP_REMOVE_OP,
                    relative_timing=constants.APP_LIFECYCLE_TIMING_POST,
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
                    lifecycle_type=constants.APP_LIFECYCLE_TYPE_SEMANTIC_CHECK,
                    operation=constants.APP_EVALUATE_REAPPLY_OP,
                    mode=constants.APP_LIFECYCLE_MODE_AUTO,
                ),
                'assertions': [
                    self.lifecycle._semantic_check_evaluate_app_reapply.assert_called_once,
                    self.lifecycle._pre_manual_apply_check.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=constants.APP_LIFECYCLE_TYPE_SEMANTIC_CHECK,
                    operation=constants.APP_APPLY_OP,
                    mode=constants.APP_LIFECYCLE_MODE_MANUAL,
                    relative_timing=constants.APP_LIFECYCLE_TIMING_PRE,
                ),
                'assertions': [
                    self.lifecycle._semantic_check_evaluate_app_reapply.assert_not_called,
                    self.lifecycle._pre_manual_apply_check.assert_called_once,
                ]
            },
        ]

        manifest_cases = [
            {
                'hook_info': mock.Mock(
                    lifecycle_type=constants.APP_LIFECYCLE_TYPE_MANIFEST,
                    operation=constants.APP_APPLY_OP,
                    relative_timing=constants.APP_LIFECYCLE_TIMING_PRE,
                ),
                'assertions': [
                    self.lifecycle._pre_update_actions.assert_called,
                    self.lifecycle._post_update_image_actions.assert_not_called,
                ]
            },
            {
                'hook_info': mock.Mock(
                    lifecycle_type=constants.APP_LIFECYCLE_TYPE_MANIFEST,
                    operation=constants.APP_APPLY_OP,
                    relative_timing=constants.APP_LIFECYCLE_TIMING_POST,
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
