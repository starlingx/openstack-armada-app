#
# Copyright (c) 2022-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import os
import subprocess

import mock
from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import kubernetes
from sysinv.tests.db import base as dbbase

from k8sapp_openstack import utils as app_utils
from k8sapp_openstack.common import constants as app_constants


class UtilsTest(dbbase.ControllerHostTestCase):
    def setUp(self):
        super(UtilsTest, self).setUp()

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=True)
    def test_is_openstack_https_ready_true(self, *_):
        self.assertTrue(app_utils.is_openstack_https_ready())

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_is_openstack_https_ready_false(self, *_):
        self.assertFalse(app_utils.is_openstack_https_ready())

    @staticmethod
    def _get_mock_host_list(hosts: list):
        mock_hosts = []
        for host in hosts:
            mock_host = mock.MagicMock()
            for key, value in host.items():
                setattr(mock_host, key, value)
            mock_hosts.append(mock_host)
        return mock_hosts

    @staticmethod
    def _get_mock_label_list(labels_by_host: dict):
        mock_labels = []
        for host_id, labels in labels_by_host.items():
            for key, value in labels.items():
                mock_label = mock.MagicMock()
                mock_label.host_id = host_id
                mock_label.label_key = key
                mock_label.label_value = value
                mock_labels.append(mock_label)
        return mock_labels

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    @mock.patch('sysinv.db.api.get_instance')
    def test_is_openvswitch_enabled_true(self, mock_dbapi_get_instance, *_):
        """Test is_openvswitch_enabled returns True when openvswitch
        is enabled.
        """
        mock_hosts = self._get_mock_host_list([
            {
                "id": 1,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
            }
        ])

        mock_labels = self._get_mock_label_list({
            1: {
                'openstack-compute-node': 'enabled',
                'openvswitch': 'enabled',
            }
        })

        db_instance = mock_dbapi_get_instance.return_value
        db_instance.ihost_get_list.return_value = mock_hosts
        db_instance.label_get_all.return_value = mock_labels

        result = app_utils.is_openvswitch_enabled()
        self.assertTrue(result)

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=app_constants.VSWITCH_LABEL_NONE)
    @mock.patch('sysinv.db.api.get_instance')
    def test_is_openvswitch_enabled_false(self, mock_dbapi_get_instance, *_):
        """Test is_openvswitch_enabled returns False when openvswitch
        is not enabled.
        """
        mock_hosts = self._get_mock_host_list([
            {
                "id": 1,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
            }
        ])

        mock_labels = self._get_mock_label_list({
            1: {
                'openstack-compute-node': 'enabled',
                "fake_label": "fake_value",
            }
        })

        db_instance = mock_dbapi_get_instance.return_value
        db_instance.ihost_get_list.return_value = mock_hosts
        db_instance.label_get_all.return_value = mock_labels

        result = app_utils.is_openvswitch_enabled()
        self.assertFalse(result)

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=f'{app_constants.CEPH_ROOK_IMAGE_DEFAULT_REPO}:'
                             f'{app_constants.CEPH_ROOK_IMAGE_DEFAULT_TAG}')
    def test_get_image_rook_ceph(self, mock_get_value_from_application):
        """Test test_get_image_rook_ceph for valid image override
        """
        expected = f'{app_constants.CEPH_ROOK_IMAGE_DEFAULT_REPO}:'\
                   f'{app_constants.CEPH_ROOK_IMAGE_DEFAULT_TAG}'

        result = app_utils.get_image_rook_ceph()
        self.assertEqual(result, expected)
        mock_get_value_from_application.assert_called_once()

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response',
                return_value="89bd29e9-c505-4170-a097-04dc8e43c897")
    def test_get_ceph_fsid(self, mock_send_cmd):
        """Test get_ceph_fsid happy path
        """
        result = app_utils.get_ceph_fsid()
        self.assertEqual(result, '89bd29e9-c505-4170-a097-04dc8e43c897')
        mock_send_cmd.assert_called_with(['ceph', 'fsid'])

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response',
                return_value="89bd29e9")
    def test_get_ceph_fsid_invalid_pattern(self, mock_send_cmd):
        """Test get_ceph_fsid for fsid not following the expected pattern
        """
        result = app_utils.get_ceph_fsid()
        self.assertEqual(result, None)
        mock_send_cmd.assert_called_with(['ceph', 'fsid'])

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response',
                return_value="")
    def test_get_ceph_fsid_unavailable(self, mock_send_cmd):
        """Test get_ceph_fsid for fsid unavailable
        """
        result = app_utils.get_ceph_fsid()
        self.assertEqual(result, None)
        mock_send_cmd.assert_called_with(['ceph', 'fsid'])

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response',
                side_effect=Exception())
    def test_get_ceph_fsid_cmd_failure(self, mock_send_cmd):
        """Test get_ceph_fsid for command failure
        """
        result = app_utils.get_ceph_fsid()
        self.assertEqual(result, None)
        mock_send_cmd.assert_called_with(['ceph', 'fsid'])

    @mock.patch('sysinv.db.api.get_instance')
    def test_is_rook_backend_available(self, mock_dbapi_get_instance):
        """Test is_rook_backend_available for rook ceph configured and applied
        """
        mock_backend_list = [mock.MagicMock()]
        mock_backend_list[0].state = constants.SB_STATE_CONFIGURED
        mock_backend_list[0].task = constants.APP_APPLY_SUCCESS
        db_instance = mock_dbapi_get_instance.return_value
        db_instance.storage_backend_get_list_by_type.return_value = mock_backend_list

        result, message = app_utils.is_ceph_backend_available(
            ceph_type=constants.SB_TYPE_CEPH_ROOK
        )
        self.assertEqual(result, True)
        self.assertEqual(message, "")
        db_instance.storage_backend_get_list_by_type.assert_called_once_with(
            backend_type=constants.SB_TYPE_CEPH_ROOK
        )

    @mock.patch('sysinv.db.api.get_instance')
    def test_is_rook_backend_available_not_applied(self,
                                                   mock_dbapi_get_instance):
        """Test is_rook_backend_available for rook ceph not successfully applied
        """
        mock_backend_list = [mock.MagicMock()]
        mock_backend_list[0].state = constants.SB_STATE_CONFIGURED
        mock_backend_list[0].task = constants.APP_APPLY_FAILURE
        db_instance = mock_dbapi_get_instance.return_value
        db_instance.storage_backend_get_list_by_type.return_value = mock_backend_list

        result, message = app_utils.is_ceph_backend_available(
            ceph_type=constants.SB_TYPE_CEPH_ROOK
        )
        self.assertEqual(result, False)
        self.assertEqual(message, app_constants.CEPH_BACKEND_NOT_CONFIGURED)
        db_instance.storage_backend_get_list_by_type.assert_called_once_with(
            backend_type=constants.SB_TYPE_CEPH_ROOK
        )

    @mock.patch('sysinv.db.api.get_instance')
    def test_is_rook_backend_available_not_configured(self,
                                                      mock_dbapi_get_instance):
        """Test is_rook_backend_available for rook ceph not configured
        """
        mock_backend_list = [mock.MagicMock()]
        mock_backend_list[0].state = constants.SB_STATE_CONFIGURING
        mock_backend_list[0].task = constants.APP_APPLY_SUCCESS
        db_instance = mock_dbapi_get_instance.return_value
        db_instance.storage_backend_get_list_by_type.return_value = mock_backend_list

        result, message = app_utils.is_ceph_backend_available(
            ceph_type=constants.SB_TYPE_CEPH_ROOK
        )
        self.assertEqual(result, False)
        self.assertEqual(message, app_constants.CEPH_BACKEND_NOT_CONFIGURED)
        db_instance.storage_backend_get_list_by_type.assert_called_once_with(
            backend_type=constants.SB_TYPE_CEPH_ROOK
        )

    @mock.patch('sysinv.db.api.get_instance', return_value=None)
    def test_is_rook_backend_available_none_db(self, mock_dbapi_get_instance):
        """Test is_rook_backend_available for dbapi failure
        """
        result, message = app_utils.is_ceph_backend_available(
            ceph_type=constants.SB_TYPE_CEPH_ROOK
        )
        self.assertEqual(result, False)
        self.assertEqual(message, app_constants.DB_API_NOT_AVAILABLE)
        mock_dbapi_get_instance.assert_called_once_with()

    @mock.patch('sysinv.db.api.get_instance')
    def test_is_rook_backend_available_empty(self, mock_dbapi_get_instance):
        """Test is_rook_backend_available for empty list of rook ceph backends
        """
        mock_backend_list = []
        db_instance = mock_dbapi_get_instance.return_value
        db_instance.storage_backend_get_list_by_type.return_value = mock_backend_list

        result, message = app_utils.is_ceph_backend_available(
            ceph_type=constants.SB_TYPE_CEPH_ROOK
        )
        self.assertEqual(result, False)
        self.assertEqual(message, f"No {constants.SB_TYPE_CEPH_ROOK} backend available")
        db_instance.storage_backend_get_list_by_type.assert_called_once_with(
            backend_type=constants.SB_TYPE_CEPH_ROOK
        )

    @mock.patch('cephclient.wrapper.CephWrapper')
    @mock.patch('sysinv.common.kubernetes.KubeOperator')
    def test_is_rook_ceph_api_available(
        self,
        mock_kube_operator,
        mock_ceph_wrapper
    ):
        """Test is_rook_backend_available for rook api pod in Running state
        """
        # Mocks for Rook Ceph pods checking
        mock_pod_list = [mock.MagicMock()]
        mock_pod_list[0].metadata.name = \
            f'{app_constants.CEPH_ROOK_MANAGER_APP}-a-74cf47c859-8cgsx'
        kube_operator_instance = mock_kube_operator.return_value
        kube_operator_instance.kube_get_pods_by_selector.return_value = mock_pod_list

        # Mocks for Rook Ceph API request
        mock_fsid = '89bd29e9-c505-4170-a097-04dc8e43c897'
        mock_response = mock.MagicMock()
        mock_response.ok = True
        ceph_instance = mock_ceph_wrapper.return_value
        ceph_instance.fsid.return_value = mock_response, mock_fsid

        result = app_utils.is_rook_ceph_api_available()

        # Ensures that the final result is as expected
        self.assertEqual(result, True)
        # Ensures that rook ceph pods were checked
        kube_operator_instance.kube_get_pods_by_selector.assert_called_once_with(
            app_constants.HELM_NS_ROOK_CEPH,
            f"app={app_constants.CEPH_ROOK_MANAGER_APP}",
            app_constants.POD_SELECTOR_RUNNING
        )
        # Ensures that API responsiveness was checked
        ceph_instance.fsid.assert_called()

    @mock.patch('cephclient.wrapper.CephWrapper')
    @mock.patch('sysinv.common.kubernetes.KubeOperator')
    def test_is_rook_ceph_api_available_not_responding(
        self,
        mock_kube_operator,
        mock_ceph_wrapper
    ):
        """Test is_rook_backend_available for rook api pod running but not
        responding
        """
        # Mocks for Rook Ceph pods checking
        mock_pod_list = [mock.MagicMock()]
        mock_pod_list[0].metadata.name = \
            f'{app_constants.CEPH_ROOK_MANAGER_APP}-a-74cf47c859-8cgsx'
        kube_operator_instance = mock_kube_operator.return_value
        kube_operator_instance.kube_get_pods_by_selector.return_value = mock_pod_list

        # Mocks for Rook Ceph API request
        mock_response = mock.MagicMock()
        mock_response.ok = False
        ceph_instance = mock_ceph_wrapper.return_value
        ceph_instance.fsid.side_effect = Exception()

        result = app_utils.is_rook_ceph_api_available()

        # Ensures that the final result is as expected
        self.assertEqual(result, False)
        # Ensures that rook ceph pods were checked
        kube_operator_instance.kube_get_pods_by_selector.assert_called_once_with(
            app_constants.HELM_NS_ROOK_CEPH,
            f"app={app_constants.CEPH_ROOK_MANAGER_APP}",
            app_constants.POD_SELECTOR_RUNNING
        )
        # Ensures that API responsiveness was checked
        ceph_instance.fsid.assert_called()

    @mock.patch('sysinv.common.kubernetes.KubeOperator')
    def test_is_rook_ceph_api_available_not_running(self, mock_kube_operator):
        """Test is_rook_backend_available for rook api pod not in Running state
        """
        mock_pod_list = []
        kube_operator_instance = mock_kube_operator.return_value
        kube_operator_instance.kube_get_pods_by_selector.return_value = mock_pod_list
        result = app_utils.is_rook_ceph_api_available()
        self.assertEqual(result, False)
        kube_operator_instance.kube_get_pods_by_selector.assert_called_once_with(
            app_constants.HELM_NS_ROOK_CEPH,
            f"app={app_constants.CEPH_ROOK_MANAGER_APP}",
            app_constants.POD_SELECTOR_RUNNING
        )

    @mock.patch('os.listdir', return_value=['1.0.0', '2.0.0', '3.0.0'])
    def test_get_app_version_list(self, mock_listdir):
        """Test get_app_version_list returns the correct list of versions."""
        base_dir = '/fake/base/dir'
        app_name = 'fake_app'
        expected_versions = ['1.0.0', '2.0.0', '3.0.0']
        result = app_utils.get_app_version_list(base_dir, app_name)
        self.assertEqual(result, expected_versions)
        mock_listdir.assert_called_once_with(os.path.join(base_dir, app_name))

    @mock.patch('builtins.open', new_callable=mock.mock_open, read_data='{"download_images": ["image1", "image2"]}')
    @mock.patch('yaml.safe_load', return_value={"download_images": ["image1", "image2"]})
    def test_get_image_list(self, mock_yaml_load, mock_open):
        """Test get_image_list returns the correct list of images."""
        image_dir = '/fake/image/dir'
        expected_images = ["image1", "image2"]
        result = app_utils.get_image_list(image_dir)
        self.assertEqual(result, expected_images)
        mock_open.assert_called_once_with(image_dir, 'r', encoding='utf-8')
        mock_yaml_load.assert_called_once()

    @mock.patch('k8sapp_openstack.utils.get_image_list', side_effect=[
        ["image1", "image2"],
        ["image1", "image2", "image3"],
        ["image1", "image4"]
    ])
    def test_get_residual_images(self, mock_get_image_list):
        """Test get_residual_images returns the correct list of residual images."""
        image_file_dir = '/fake/image/dir'
        app_version = '2.0.0'
        app_version_list = ['1.0.0', '2.0.0', '3.0.0']
        expected_residual_images = ["image3", "image4"]
        result = app_utils.get_residual_images(image_file_dir, app_version, app_version_list)
        self.assertEqual(set(result), set(expected_residual_images))

    @mock.patch('k8sapp_openstack.utils.list_crictl_images', return_value={
        "images": [
            {"repoTags": ["image1"], "id": "id1"},
            {"repoTags": ["image2"], "id": "id2"}
        ]
    })
    @mock.patch('k8sapp_openstack.utils.subprocess.run')
    def test_delete_residual_images(self, mock_subprocess_run, mock_list_crictl_images):
        """Test delete_residual_images removes the correct images."""
        image_list = ["image1", "image3"]
        mock_subprocess_run.return_value = mock.Mock()
        app_utils.delete_residual_images(image_list)
        mock_list_crictl_images.assert_called_once()
        mock_subprocess_run.assert_called_once_with(
            args=["bash", "-c", "source /etc/platform/openrc && crictl rmi id1"],
            capture_output=True,
            text=True,
            shell=False
        )

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response', return_value="controller-0\ncontroller-1")
    def test_get_number_of_controllers(self, mock_send_cmd):
        """Test get_number_of_controllers returns the correct count."""
        result = app_utils.get_number_of_controllers()
        self.assertEqual(result, 2)
        mock_send_cmd.assert_called_once()

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response')
    @mock.patch('builtins.open', new_callable=mock.mock_open)
    @mock.patch('json.dump')
    def test_check_and_create_snapshot_class(self, mock_json_dump, mock_open, mock_send_cmd):
        """Test check_and_create_snapshot_class creates the snapshot class if not present."""
        mock_send_cmd.side_effect = [Exception("Not found"), None]
        snapshot_class = "test-snapshot-class"
        path = "/tmp"
        app_utils.check_and_create_snapshot_class(snapshot_class, path)
        mock_send_cmd.assert_any_call([
            "kubectl", "--kubeconfig", mock.ANY,
            "-n", mock.ANY,
            "get", "volumesnapshotclasses.snapshot.storage.k8s.io", snapshot_class
        ])
        mock_open.assert_called_once_with(f"{path}/{snapshot_class}-class.json", "w")
        mock_json_dump.assert_called_once()

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response')
    @mock.patch('builtins.open', new_callable=mock.mock_open)
    @mock.patch('json.dump')
    def test_create_pvc_snapshot(self, mock_json_dump, mock_open, mock_send_cmd):
        """Test create_pvc_snapshot creates the snapshot correctly."""
        snapshot_name = "test-snapshot"
        pvc_name = "test-pvc"
        snapshot_class = "test-snapshot-class"
        path = "/tmp"
        app_utils.create_pvc_snapshot(snapshot_name, pvc_name, snapshot_class, path)
        mock_send_cmd.assert_any_call([
            "kubectl", "--kubeconfig", mock.ANY,
            "create", "-f", f"{path}/{pvc_name}-snapshot.json"
        ])
        mock_open.assert_called_once_with(f"{path}/{pvc_name}-snapshot.json", "w")
        mock_json_dump.assert_called_once()

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response')
    @mock.patch('builtins.open', new_callable=mock.mock_open)
    @mock.patch('json.dump')
    def test_restore_pvc_snapshot(self, mock_json_dump, mock_open, mock_send_cmd):
        """Test restore_pvc_snapshot restores the snapshot correctly."""
        snapshot_name = "test-snapshot"
        pvc_name = "test-pvc"
        statefulset_name = "test-sts"
        number_of_controllers = 2
        path = "/tmp"
        mock_send_cmd.side_effect = [
            None, None, "10Gi test-storage-class", None, None, None
        ]
        app_utils.restore_pvc_snapshot(snapshot_name, pvc_name, statefulset_name, number_of_controllers, path)
        mock_send_cmd.assert_any_call([
            "kubectl", "--kubeconfig", mock.ANY,
            "create", "-f", f"{path}/{pvc_name}-snapshot-to-apply.json"
        ])
        mock_open.assert_called_once_with(f"{path}/{pvc_name}-snapshot-to-apply.json", "w")
        mock_json_dump.assert_called_once()

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response')
    def test_delete_snapshot(self, mock_send_cmd):
        """Test delete_snapshot deletes the snapshot correctly."""
        snapshot_name = "test-snapshot"
        app_utils.delete_snapshot(snapshot_name)
        mock_send_cmd.assert_called_once_with([
            "kubectl", "--kubeconfig", mock.ANY,
            "-n", mock.ANY,
            "delete", "volumesnapshots.snapshot.storage.k8s.io", snapshot_name
        ])

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response')
    def test_delete_kubernetes_resource(self, mock_send_cmd):
        """Test delete_kubernetes_resource deletes the resource correctly."""
        resource_type = "pvc"
        resource_name = "test-pvc"
        app_utils.delete_kubernetes_resource(resource_type, resource_name)
        mock_send_cmd.assert_called_once_with([
            "kubectl", "--kubeconfig", mock.ANY,
            "delete", resource_type, resource_name,
            "-n", mock.ANY
        ])

    @mock.patch('sysinv.db.api.get_instance')
    def test_get_system_vswitch_labels_openvswitch(self, mock_dbapi_get_instance):
        """Test if get_system_vswitch_labels returns the Openvswitch label.
        """
        mock_hosts = self._get_mock_host_list([
            {
                "id": 1,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
            }
        ])

        mock_labels = self._get_mock_label_list({
            1: {
                'openstack-compute-node': 'enabled',
                'openvswitch': 'enabled',
            }
        })

        db_instance = mock_dbapi_get_instance.return_value
        db_instance.ihost_get_list.return_value = mock_hosts
        db_instance.label_get_all.return_value = mock_labels

        labels, conflicts = app_utils.get_system_vswitch_labels(db_instance)

        pass_condition = (labels == {app_constants.OPENVSWITCH_LABEL}
                          and len(conflicts) == 0)
        self.assertTrue(pass_condition)

    @mock.patch('sysinv.db.api.get_instance')
    def test_get_system_vswitch_labels_openvswitch_dpdk(self, mock_dbapi_get_instance):
        """Test if get_system_vswitch_labels returns the Openvswitch-DPDK label.
        """
        mock_hosts = self._get_mock_host_list([
            {
                "id": 1,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
            }
        ])

        mock_labels = self._get_mock_label_list({
            1: {
                'openstack-compute-node': 'enabled',
                'openvswitch': 'enabled',
                'dpdk': 'enabled',
            }
        })

        db_instance = mock_dbapi_get_instance.return_value
        db_instance.ihost_get_list.return_value = mock_hosts
        db_instance.label_get_all.return_value = mock_labels

        labels, conflicts = app_utils.get_system_vswitch_labels(db_instance)

        pass_condition = (labels == {app_constants.OPENVSWITCH_LABEL, app_constants.DPDK_LABEL}
                          and len(conflicts) == 0)
        self.assertTrue(pass_condition)

    @mock.patch('sysinv.db.api.get_instance')
    def test_get_system_vswitch_labels_empty(self, mock_dbapi_get_instance):
        """Test if get_system_vswitch_labels returns 'none' when no labels are found.
        """
        mock_hosts = self._get_mock_host_list([
            {
                "id": 1,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
            }
        ])

        mock_labels = self._get_mock_label_list({
            1: {
                'openstack-compute-node': 'enabled',
            }
        })

        db_instance = mock_dbapi_get_instance.return_value
        db_instance.ihost_get_list.return_value = mock_hosts
        db_instance.label_get_all.return_value = mock_labels

        labels, conflicts = app_utils.get_system_vswitch_labels(db_instance)

        pass_condition = (conflicts == {app_constants.VSWITCH_LABEL_NONE}
                          and len(labels) == 0)
        self.assertTrue(pass_condition)

    @mock.patch('sysinv.db.api.get_instance')
    def test_get_system_vswitch_labels_multiple_labels(self, mock_dbapi_get_instance):
        """Test if get_system_vswitch_labels returns a set with size > 1
         when multiple labels are found.
        """

        OTHER_VSWITCH_LABEL = "other-vswitch=enabled"

        mock_hosts = self._get_mock_host_list([
            {
                "id": 1,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
            }
        ])

        mock_labels = self._get_mock_label_list({
            1: {
                'openstack-compute-node': 'enabled',
                'openvswitch': 'enabled',
                'dpdk': 'enabled',
                'other-vswitch': 'enabled',
            }
        })

        mock_label_combinations = (app_constants.VSWITCH_ALLOWED_COMBINATIONS +
                                   [{OTHER_VSWITCH_LABEL}])

        db_instance = mock_dbapi_get_instance.return_value
        db_instance.ihost_get_list.return_value = mock_hosts
        db_instance.label_get_all.return_value = mock_labels

        labels, conflicts = app_utils.get_system_vswitch_labels(db_instance,
                                                                mock_label_combinations)

        pass_condition = (conflicts == {app_constants.OPENVSWITCH_LABEL,
                                        app_constants.DPDK_LABEL, OTHER_VSWITCH_LABEL}
                          and len(labels) == 0)
        self.assertTrue(pass_condition)

    @mock.patch('sysinv.db.api.get_instance')
    def test_get_system_vswitch_labels_multiple_hosts_same_label(self, mock_dbapi_get_instance):
        """Test if get_system_vswitch_labels returns one label
         when multiple hosts with the same label are found.
        """
        mock_hosts = self._get_mock_host_list([
            {
                "id": 1,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
            },
            {
                "id": 2,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
            },
        ])

        mock_labels = self._get_mock_label_list({
            1: {
                'openstack-compute-node': 'enabled',
                'openvswitch': 'enabled',
            },
            2: {
                'openstack-compute-node': 'enabled',
                'openvswitch': 'enabled',
            }
        })

        db_instance = mock_dbapi_get_instance.return_value
        db_instance.ihost_get_list.return_value = mock_hosts
        db_instance.label_get_all.return_value = mock_labels

        labels, conflicts = app_utils.get_system_vswitch_labels(db_instance)

        pass_condition = (labels == {app_constants.OPENVSWITCH_LABEL}
                          and len(conflicts) == 0)
        self.assertTrue(pass_condition)

    @mock.patch('sysinv.db.api.get_instance')
    def test_get_system_vswitch_labels_multiple_hosts_two_labels(self, mock_dbapi_get_instance):
        """Test if get_system_vswitch_labels returns multiple labels
         when multiple hosts with different labels are found.
        """
        mock_hosts = self._get_mock_host_list([
            {
                "id": 1,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
            },
            {
                "id": 2,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
            },
        ])

        mock_labels = self._get_mock_label_list({
            1: {
                'openstack-compute-node': 'enabled',
                'openvswitch': 'enabled',
            },
            2: {
                'openstack-compute-node': 'enabled',
                'openvswitch': 'enabled',
                'dpdk': 'enabled',
            }
        })

        db_instance = mock_dbapi_get_instance.return_value
        db_instance.ihost_get_list.return_value = mock_hosts
        db_instance.label_get_all.return_value = mock_labels

        labels, conflicts = app_utils.get_system_vswitch_labels(db_instance)

        pass_condition = (conflicts == {app_constants.OPENVSWITCH_LABEL, app_constants.DPDK_LABEL}
                          and len(labels) == 0)
        self.assertTrue(pass_condition)

    @mock.patch('sysinv.db.api.get_instance')
    def test_get_system_vswitch_labels_multiple_hosts_one_label(self, mock_dbapi_get_instance):
        """Test if get_system_vswitch_labels returns multiple labels with one as 'none' when
         when one of the hosts is unlabeled.
        """
        mock_hosts = self._get_mock_host_list([
            {
                "id": 1,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
            },
            {
                "id": 2,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
            },
        ])

        mock_labels = self._get_mock_label_list({
            1: {
                'openstack-compute-node': 'enabled',
                'openvswitch': 'enabled',
            },
            2: {
                'openstack-compute-node': 'enabled',
            }
        })

        db_instance = mock_dbapi_get_instance.return_value
        db_instance.ihost_get_list.return_value = mock_hosts
        db_instance.label_get_all.return_value = mock_labels

        labels, conflicts = app_utils.get_system_vswitch_labels(db_instance)

        pass_condition = (conflicts == {app_constants.VSWITCH_LABEL_NONE}
                          and labels == {app_constants.OPENVSWITCH_LABEL})
        self.assertTrue(pass_condition)

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
            return_value=[app_constants.OPENVSWITCH_LABEL])
    def test_get_current_vswitch_label_openvswitch_from_file(self, *_):
        """Test if get_current_vswitch_label returns the Openvswitch label when
         it is on the override file
        """
        result = app_utils.get_current_vswitch_label()
        self.assertEqual(result, {app_constants.OPENVSWITCH_LABEL})

    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
            return_value=[app_constants.OPENVSWITCH_LABEL, app_constants.DPDK_LABEL])
    def test_get_current_vswitch_label_openvswitch_dpdk_from_file(self, *_):
        """Test if get_current_vswitch_label returns the Openvswitch-DPDK label when
         it is on the override file
        """
        result = app_utils.get_current_vswitch_label()
        self.assertEqual(result, {app_constants.OPENVSWITCH_LABEL, app_constants.DPDK_LABEL})

    @mock.patch('k8sapp_openstack.utils.get_system_vswitch_labels',
                return_value=({app_constants.OPENVSWITCH_LABEL}, set()))
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=['none'])
    @mock.patch('sysinv.db.api.get_instance')
    def test_get_current_vswitch_label_openvswitch(self, *_):
        """
        Test if get_current_vswitch_label returns the Openvswitch label
        """
        result = app_utils.get_current_vswitch_label()
        self.assertEqual(result, {app_constants.OPENVSWITCH_LABEL})

    @mock.patch('k8sapp_openstack.utils.get_system_vswitch_labels',
                return_value=({app_constants.OPENVSWITCH_LABEL, app_constants.DPDK_LABEL},
                              set()))
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=['none'])
    @mock.patch('sysinv.db.api.get_instance')
    def test_get_current_vswitch_label_openvswitch_dpdk(self, *_):
        """
        Test if get_current_vswitch_label returns the Openvswitch-DPDK label
        """
        result = app_utils.get_current_vswitch_label()
        self.assertEqual(result, {app_constants.OPENVSWITCH_LABEL, app_constants.DPDK_LABEL})

    @mock.patch('k8sapp_openstack.utils.get_system_vswitch_labels',
                return_value=(set(), set()))
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=['none'])
    @mock.patch('sysinv.db.api.get_instance')
    def test_get_current_vswitch_label_empty(self, *_):
        """
        Test if get_current_vswitch_label returns empty set when both labels and
        conflicts are empty
        """
        result = app_utils.get_current_vswitch_label()
        self.assertEqual(len(result), 0)

    @mock.patch('k8sapp_openstack.utils.get_system_vswitch_labels',
                return_value=({app_constants.OPENVSWITCH_LABEL},
                              {app_constants.VSWITCH_LABEL_NONE}))
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=['none'])
    @mock.patch('sysinv.db.api.get_instance')
    def test_get_current_vswitch_label_conflict_none(self, *_):
        """
        Test if get_current_vswitch_label returns empty set when there are hosts
        without vswitch labels
        """
        result = app_utils.get_current_vswitch_label()
        self.assertEqual(len(result), 0)

    @mock.patch('k8sapp_openstack.utils.get_system_vswitch_labels',
                return_value=(set(), {
                    app_constants.VSWITCH_LABEL_NONE,
                    app_constants.OPENVSWITCH_LABEL, app_constants.DPDK_LABEL}))
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=['none'])
    @mock.patch('sysinv.db.api.get_instance')
    def test_get_current_vswitch_label_conflict_none_and_mismatch(self, *_):
        """
        Test if get_current_vswitch_label returns empty set when there are hosts
        without vswitch labels and hosts with mismatched labels
        """
        result = app_utils.get_current_vswitch_label()
        self.assertEqual(len(result), 0)

    @mock.patch('k8sapp_openstack.utils.get_system_vswitch_labels',
                return_value=(set(), {app_constants.OPENVSWITCH_LABEL, app_constants.DPDK_LABEL}))
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value=['none'])
    @mock.patch('sysinv.db.api.get_instance')
    def test_get_current_vswitch_label_conflict_mismatch(self, *_):
        """
        Test if get_current_vswitch_label returns empty set when there are hosts
        with mismatched labels
        """
        result = app_utils.get_current_vswitch_label()
        self.assertEqual(len(result), 0)

    @mock.patch('sysinv.helm.utils.call_fluxcd_reconciliation')
    def test_force_app_reconciliation(self, mock_fluxcd_reconciliation):
        """Test force_app_reconciliation to force fluxcd reconciliation for all
        the app helm releases
        """
        helm_releases = [
            "cinder",
            "clients",
            "fm-rest-api",
            "glance",
            "heat",
            "horizon",
            "ingress-nginx-openstack",
            "keystone",
            "libvirt",
            "mariadb",
            "memchaced",
            "neutron",
            "nginx-ports-control",
            "nova",
            "nova-api-proxy",
            "openvswitch",
            "pci-irq-affinity-agent",
            "placement",
            "rabbitmq"
        ]
        mock_chart_list = []
        for chart in helm_releases:
            mock_chart = mock.MagicMock()
            mock_chart.metadata_name = chart
            mock_chart.chart_label = chart
            mock_chart.namespace = "openstack"
            mock_chart.helm_repo_name = "starlingx"
            mock_chart_list.append(mock_chart)
        mock_app_op = mock.MagicMock()
        mock_app_op._get_list_of_charts.return_value = mock_chart_list
        mock_app = mock.MagicMock()
        mock_app.name = 'stx-openstack'
        mock_app.version = '25.09-0'

        app_utils.force_app_reconciliation(mock_app_op, mock_app)

        # Asserts that reconciliation is called for all the helm releases
        for release in helm_releases:
            mock_fluxcd_reconciliation.assert_any_call(release, "openstack")

    @mock.patch('sysinv.db.api.get_instance')
    def test_get_hosts_uuids(self, mock_dbapi_get_instance):
        """
        Test if get_hosts_uuids returns the given enabled compute nodes.
        Must return data from all nodes.
        """

        MOCK_UUID_1 = "01234567-abcd-0123-abcd-0123456789ef"
        MOCK_UUID_2 = "76543210-dcba-3210-dcba-fe9876543210"

        mock_hosts = self._get_mock_host_list([
            {
                "id": 1,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
                "hostname": "host1",
                "uuid": MOCK_UUID_1
            },
            {
                "id": 2,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
                "hostname": "host2",
                "uuid": MOCK_UUID_2
            },
        ])

        mock_labels = self._get_mock_label_list({
            1: {
                'openstack-compute-node': 'enabled',
            },
            2: {
                'openstack-compute-node': 'enabled',
            }
        })

        db_instance = mock_dbapi_get_instance.return_value
        db_instance.ihost_get_list.return_value = mock_hosts
        db_instance.label_get_all.return_value = mock_labels

        hosts_uuids = app_utils.get_hosts_uuids()

        print(hosts_uuids)

        self.assertTrue(all([
            {'name': "host1", 'uuid': MOCK_UUID_1} in hosts_uuids,
            {'name': "host2", 'uuid': MOCK_UUID_2} in hosts_uuids,
        ]))

    @mock.patch('sysinv.db.api.get_instance')
    def test_get_hosts_uuids_unprovisioned_locked(self, mock_dbapi_get_instance):
        """
        Test if get_hosts_uuids returns only the enabled compute nodes.
        Must return data only for provisioned or unlocked nodes.
        """

        MOCK_UUID_1 = "01234567-abcd-0123-abcd-0123456789ef"
        MOCK_UUID_2 = "76543210-dcba-3210-dcba-fe9876543210"

        mock_hosts = self._get_mock_host_list([
            {
                "id": 1,
                "invprovision": constants.UNPROVISIONED,
                "ihost_action": constants.LOCK_ACTION,
                "subfunctions": constants.WORKER,
                "hostname": "host1",
                "uuid": MOCK_UUID_1
            },
            {
                "id": 2,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
                "hostname": "host2",
                "uuid": MOCK_UUID_2
            },
        ])

        mock_labels = self._get_mock_label_list({
            1: {
                'openstack-compute-node': 'enabled',
            },
            2: {
                'openstack-compute-node': 'enabled',
            }
        })

        db_instance = mock_dbapi_get_instance.return_value
        db_instance.ihost_get_list.return_value = mock_hosts
        db_instance.label_get_all.return_value = mock_labels

        hosts_uuids = app_utils.get_hosts_uuids()

        self.assertTrue(all([
            {"name": "host1", "uuid": MOCK_UUID_1} not in hosts_uuids,
            {"name": "host2", "uuid": MOCK_UUID_2} in hosts_uuids,
        ]))

    @mock.patch('sysinv.db.api.get_instance')
    def test_get_hosts_uuids_controller(self, mock_dbapi_get_instance):
        """
        Test if get_hosts_uuids returns only the enabled compute nodes.
        Must return data only for worker nodes.
        """

        MOCK_UUID_1 = "01234567-abcd-0123-abcd-0123456789ef"
        MOCK_UUID_2 = "76543210-dcba-3210-dcba-fe9876543210"

        mock_hosts = self._get_mock_host_list([
            {
                "id": 1,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.CONTROLLER,
                "hostname": "host1",
                "uuid": MOCK_UUID_1
            },
            {
                "id": 2,
                "invprovision": constants.PROVISIONED,
                "ihost_action": constants.UNLOCK_ACTION,
                "subfunctions": constants.WORKER,
                "hostname": "host2",
                "uuid": MOCK_UUID_2
            },
        ])

        mock_labels = self._get_mock_label_list({
            1: {
                'openstack-compute-node': 'enabled',
            },
            2: {
                'openstack-compute-node': 'enabled',
            }
        })

        db_instance = mock_dbapi_get_instance.return_value
        db_instance.ihost_get_list.return_value = mock_hosts
        db_instance.label_get_all.return_value = mock_labels

        hosts_uuids = app_utils.get_hosts_uuids()

        self.assertTrue(all([
            {"name": "host1", "uuid": MOCK_UUID_1} not in hosts_uuids,
            {"name": "host2", "uuid": MOCK_UUID_2} in hosts_uuids,
        ]))

    @mock.patch('sysinv.db.api.get_instance')
    def test_is_central_cloud_true(self, mock_dbapi_get_instance):
        """Test is_central_cloud returns True when system role is
           Central Cloud.
        """
        system_mock = mock.MagicMock()
        system_mock.distributed_cloud_role = \
            constants.DISTRIBUTED_CLOUD_ROLE_SYSTEMCONTROLLER
        db_instance = mock_dbapi_get_instance.return_value
        db_instance.isystem_get_one.return_value = system_mock

        result = app_utils.is_central_cloud()
        self.assertTrue(result)

    @mock.patch('sysinv.db.api.get_instance')
    def test_is_central_cloud_false(self, mock_dbapi_get_instance):
        """Test is_central_cloud returns False when system role is not
          Central Cloud.
        """
        system_mock = mock.MagicMock()
        system_mock.distributed_cloud_role = "subcloud"
        db_instance = mock_dbapi_get_instance.return_value
        db_instance.isystem_get_one.return_value = system_mock

        result = app_utils.is_central_cloud()
        self.assertFalse(result)

    @mock.patch('sysinv.db.api.get_instance')
    def test_is_central_cloud_attribute_error(self, mock_dbapi_get_instance):
        """Test is_central_cloud returns False if system object is missing
           attribute.
        """
        system_mock = mock.MagicMock()
        del system_mock.distributed_cloud_role  # forces AttributeError
        db_instance = mock_dbapi_get_instance.return_value
        db_instance.isystem_get_one.return_value = system_mock

        result = app_utils.is_central_cloud()
        self.assertFalse(result)

    @mock.patch('sysinv.db.api.get_instance', return_value=None)
    def test_is_central_cloud_no_db(self, mock_dbapi_get_instance):
        """Test is_central_cloud returns False when dbapi is unavailable"""
        result = app_utils.is_central_cloud()
        self.assertFalse(result)

    def mock_address_pool_get(self, address_pool_uuid):
        """
        Get address-pool mock object

        Args:
            address_pool_uuid (str): address pool unique identifier
        Returns:
            mock.MagicMock(): address pool mock object matching the given uuid
        """
        mock_pools = [mock.MagicMock(), mock.MagicMock()]
        mock_pools[0].uuid = "434e61be-3603-4082-a139-fb6a0514189a"
        mock_pools[0].family = constants.IPV4_FAMILY
        mock_pools[1].uuid = "b40b1db7-19cd-49a0-ae41-f586bee69a8c"
        mock_pools[1].family = constants.IPV6_FAMILY
        for pool in mock_pools:
            if pool.uuid == address_pool_uuid:
                return pool
        return None

    @mock.patch('sysinv.db.api.get_instance')
    def test_get_ip_families_single_stack(self, mock_dbapi_get_instance):
        """ Test get_ip_families for single stack deployments
        """
        mock_network = mock.MagicMock()
        mock_network.id = 7
        mock_net_addr_pools = [mock.MagicMock()]
        mock_net_addr_pools[0].address_pool_uuid = \
            "434e61be-3603-4082-a139-fb6a0514189a"

        db_instance = mock_dbapi_get_instance.return_value
        db_instance.network_get_by_type.return_value = mock_network
        db_instance.network_addrpool_get_by_network_id.return_value = \
            mock_net_addr_pools
        db_instance.address_pool_get.side_effect = \
            self.mock_address_pool_get

        result = app_utils.get_ip_families()
        self.assertEqual(result, {constants.IPV4_FAMILY})

    @mock.patch('sysinv.db.api.get_instance')
    def test_get_ip_families_dual_stack(self, mock_dbapi_get_instance):
        """ Test get_ip_families for Dual-Stack deployments
        """
        mock_network = mock.MagicMock()
        mock_network.id = 7
        mock_net_addr_pools = [mock.MagicMock(), mock.MagicMock()]
        mock_net_addr_pools[0].address_pool_uuid = \
            "434e61be-3603-4082-a139-fb6a0514189a"
        mock_net_addr_pools[1].address_pool_uuid = \
            "b40b1db7-19cd-49a0-ae41-f586bee69a8c"

        db_instance = mock_dbapi_get_instance.return_value
        db_instance.network_get_by_type.return_value = mock_network
        db_instance.network_addrpool_get_by_network_id.return_value = \
            mock_net_addr_pools
        db_instance.address_pool_get.side_effect = \
            self.mock_address_pool_get

        result = app_utils.get_ip_families()
        self.assertEqual(result, {constants.IPV4_FAMILY, constants.IPV6_FAMILY})

    @mock.patch('sysinv.db.api.get_instance')
    def test_get_ip_families_invalid_network(self, mock_dbapi_get_instance):
        """ Test get_ip_families for invalid network type
        """
        db_instance = mock_dbapi_get_instance.return_value
        network_type_exception = exception.NetworkTypeNotFound(
            type=constants.NETWORK_TYPE_CLUSTER_SERVICE
        )
        db_instance.network_get_by_type.side_effect = network_type_exception

        result = app_utils.get_ip_families()
        self.assertEqual(result, set())

    @mock.patch('k8sapp_openstack.utils.get_ip_families',
                return_value={constants.IPV4_FAMILY})
    def test_is_ipv4_on_ipv4(self, mock_get_ip_families):
        """ Test is_ipv4 for IPv4 systems
        """
        result = app_utils.is_ipv4()
        self.assertEqual(result, True)
        mock_get_ip_families.assert_called_once()

    @mock.patch('k8sapp_openstack.utils.get_ip_families',
                return_value={constants.IPV6_FAMILY})
    def test_is_ipv4_on_ipv6(self, mock_get_ip_families):
        """ Test is_ipv4 for IPv6 systems
        """
        result = app_utils.is_ipv4()
        self.assertEqual(result, False)
        mock_get_ip_families.assert_called_once()

    @mock.patch('k8sapp_openstack.utils.get_ip_families',
                return_value={constants.IPV4_FAMILY, constants.IPV6_FAMILY})
    def test_is_ipv4_on_dual_stack(self, mock_get_ip_families):
        """ Test is_ipv4 for Dual-Stack systems
        """
        result = app_utils.is_ipv4()
        self.assertEqual(result, False)
        mock_get_ip_families.assert_called_once()

    @mock.patch("k8sapp_openstack.utils.subprocess.run")
    def test_get_server_list_success(self, mock_run):
        """ Test get_server_list for a successful call with servers available
        """
        mock_process = mock.MagicMock()
        mock_process.stdout = "server1\nserver2\n"
        mock_process.stderr = ""
        mock_process.check_returncode.return_value = None
        mock_run.return_value = mock_process

        result = app_utils.get_server_list()

        assert result == "server1\nserver2"
        mock_run.assert_called_once_with(
            args=["bash", "-c", "source /var/opt/openstack/admin-openrc && openstack server list --all-projects"],
            capture_output=True,
            text=True,
            shell=False,
        )

    @mock.patch("k8sapp_openstack.utils.subprocess.run")
    def test_get_server_list_nonzero_exit(self, mock_run):
        """ Test get_server_list for a non zero exit code
        """
        mock_process = mock.MagicMock()
        mock_process.stdout = ""
        mock_process.stderr = "Error: something went wrong"
        mock_process.check_returncode.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd="openstack server list"
        )
        mock_run.return_value = mock_process

        result = app_utils.get_server_list()

        assert result == ""

    @mock.patch("k8sapp_openstack.utils.subprocess.run")
    def test_get_server_list_no_servers(self, mock_run):
        """ Test get_server_list for a successful call with no servers available
        """
        mock_process = mock.MagicMock()
        mock_process.stdout = "\n"
        mock_process.stderr = ""
        mock_process.check_returncode.return_value = None
        mock_run.return_value = mock_process

        result = app_utils.get_server_list()

        assert result == ""

    @mock.patch("k8sapp_openstack.utils._get_value_from_application")
    def test_is_dex_enabled_returns_true(self, mock_get_value):
        mock_get_value.return_value = True

        result = app_utils.is_dex_enabled()
        self.assertTrue(result)
        mock_get_value.assert_called_once_with(
            default_value=False,
            chart_name=app_constants.HELM_CHART_KEYSTONE,
            override_name="conf.federation.dex_idp.enabled",
        )

    @mock.patch("k8sapp_openstack.utils._get_value_from_application")
    def test_is_dex_enabled_returns_false(self, mock_get_value):
        """ test is_dex_enabled for when dex_ipd.enabled equals false
        """
        mock_get_value.return_value = False

        result = app_utils.is_dex_enabled()
        self.assertFalse(result)

    def test_get_dex_issuer_url_enabled_success(self):
        """ Test get_dex_issuer_url with successfully retrieving parameter
        """
        db_mock = mock.Mock()
        db_mock.service_parameter_get_one.return_value.value = "https://dex.example.com"

        result = app_utils.get_dex_issuer_url(db_mock, dex_enabled=True)
        assert result == "https://dex.example.com"

    def test_get_dex_issuer_url_enabled_not_found(self):
        """ Test get_dex_issuer_url with dex enabled but not configured
        """
        db_mock = mock.Mock()
        db_mock.service_parameter_get_one.side_effect = Exception("DB error")

        self.assertRaises(
            exception.NotFound,
            app_utils.get_dex_issuer_url,
            db_mock,
            dex_enabled=True)

    def test_get_dex_issuer_url_disabled_not_found(self):
        """ Test get_dex_issuer_url with dex disabled
        """
        db_mock = mock.Mock()
        db_mock.service_parameter_get_one.side_effect = Exception("DB error")

        result = app_utils.get_dex_issuer_url(db_mock, dex_enabled=False)
        assert result == ""

    @staticmethod
    def _return_default(default_value, *_, **__):
        return default_value

    @staticmethod
    def _override_timeout_only(default_value, *_, **kwargs):
        if kwargs.get('override_name') == "conf.federation.dex_conf.timeout":
            return 10
        return default_value

    @staticmethod
    def _override_all_health_checks(default_value, *_, **kwargs):
        overrides = {
            "conf.federation.dex_conf.timeout": 30,
            "conf.federation.dex_conf.retries": 5,
            "conf.federation.dex_conf.verify": True,
            "conf.federation.dex_conf.probe_endpoint": "/probe",
        }
        return overrides.get(kwargs.get('override_name'), default_value)

    @mock.patch('k8sapp_openstack.utils._get_value_from_application')
    def test_get_dex_health_check_config_defaults(self, mock_get_value):
        """Ensure defaults are returned when no overrides exist."""
        mock_get_value.side_effect = self._return_default

        expected_config = {
            "timeout": app_constants.DEX_HEALTH_CHECK_DEFAULT_TIMEOUT,
            "retries": app_constants.DEX_HEALTH_CHECK_DEFAULT_RETRIES,
            "verify": app_constants.DEX_HEALTH_CHECK_DEFAULT_VERIFY,
            "endpoint": app_constants.DEX_HEALTH_CHECK_DEFAULT_ENDPOINT,
        }
        config = app_utils.get_dex_health_check_config()

        self.assertEqual(config, expected_config)
        self.assertEqual(mock_get_value.call_count, 4)

    @mock.patch('k8sapp_openstack.utils._get_value_from_application')
    def test_get_dex_health_check_config_partial_override(self, mock_get_value):
        """Ensure single override updates only its specific field."""
        mock_get_value.side_effect = self._override_timeout_only

        expected_config = {
            "timeout": 10,
            "retries": app_constants.DEX_HEALTH_CHECK_DEFAULT_RETRIES,
            "verify": app_constants.DEX_HEALTH_CHECK_DEFAULT_VERIFY,
            "endpoint": app_constants.DEX_HEALTH_CHECK_DEFAULT_ENDPOINT,
        }
        config = app_utils.get_dex_health_check_config()

        self.assertEqual(config, expected_config)

    @mock.patch('k8sapp_openstack.utils._get_value_from_application')
    def test_get_dex_health_check_config_full_override(self, mock_get_value):
        """Ensure overrides can customize every health-check option."""
        mock_get_value.side_effect = self._override_all_health_checks

        expected_config = {"timeout": 30, "retries": 5, "verify": True, "endpoint": "/probe"}
        config = app_utils.get_dex_health_check_config()

        self.assertEqual(config, expected_config)

    def test_oidc_parameters_exist_all_present(self):
        """Ensure True is returned when every OIDC parameter exists."""
        db = mock.MagicMock()

        result = app_utils.oidc_parameters_exist(db)

        self.assertTrue(result)
        self.assertEqual(db.service_parameter_get_one.call_count, 4)

    def test_oidc_parameters_exist_missing_value(self):
        """Ensure False is returned when any OIDC parameter lookup fails."""
        db = mock.MagicMock()
        db.service_parameter_get_one.side_effect = [
            mock.MagicMock(),
            Exception("missing parameter"),
        ]

        result = app_utils.oidc_parameters_exist(db)

        self.assertFalse(result)
        self.assertEqual(db.service_parameter_get_one.call_count, 2)

    @mock.patch('k8sapp_openstack.utils.get_dex_health_check_config',
                return_value={"timeout": app_constants.DEX_HEALTH_CHECK_DEFAULT_TIMEOUT,
                              "retries": app_constants.DEX_HEALTH_CHECK_DEFAULT_RETRIES,
                              "verify": app_constants.DEX_HEALTH_CHECK_DEFAULT_VERIFY,
                              "endpoint": app_constants.DEX_HEALTH_CHECK_DEFAULT_ENDPOINT})
    @mock.patch('k8sapp_openstack.utils.get_dex_issuer_url', return_value="")
    @mock.patch('k8sapp_openstack.utils.requests.get')
    def test_check_dex_healthy_missing_issuer(
        self, mock_requests_get, mock_get_dex_issuer_url, _
    ):
        """Ensure the check fails fast when the issuer URL is missing."""
        result = app_utils.check_dex_healthy(mock.MagicMock(), dex_enabled=True)

        self.assertFalse(result)
        mock_get_dex_issuer_url.assert_called_once()
        mock_requests_get.assert_not_called()

    @mock.patch('k8sapp_openstack.utils.get_dex_health_check_config',
                return_value={"timeout": 2, "retries": 2, "verify": True, "endpoint": "/healthz"})
    @mock.patch('k8sapp_openstack.utils.get_dex_issuer_url',
                return_value="https://dex.example")
    @mock.patch('k8sapp_openstack.utils.requests.get')
    def test_check_dex_healthy_success(
        self, mock_requests_get, mock_get_dex_issuer_url, _
    ):
        """Ensure Dex health check succeeds on HTTP 200 responses."""
        response = mock.MagicMock()
        response.status_code = app_constants.DEX_HEALTHY_STATUS_CODE
        response.ok = True
        response.text = "ok"
        mock_requests_get.return_value = response

        result = app_utils.check_dex_healthy(mock.MagicMock(), dex_enabled=True)

        self.assertTrue(result)
        mock_get_dex_issuer_url.assert_called_once()
        mock_requests_get.assert_called_once_with(
            "https://dex.example/healthz", timeout=2, verify=True
        )

    @mock.patch('k8sapp_openstack.utils.get_dex_health_check_config',
                return_value={"timeout": 1, "retries": 2, "verify": False, "endpoint": "/healthz"})
    @mock.patch('k8sapp_openstack.utils.get_dex_issuer_url',
                return_value="https://dex.example")
    @mock.patch('k8sapp_openstack.utils.requests.get')
    def test_check_dex_healthy_non_success_status(
        self, mock_requests_get, mock_get_dex_issuer_url, _
    ):
        """Ensure Dex health check retries and ultimately fails on non-200."""
        response = mock.MagicMock()
        response.status_code = 500
        response.ok = False
        response.text = "must fail"
        mock_requests_get.return_value = response

        result = app_utils.check_dex_healthy(mock.MagicMock(), dex_enabled=True)

        self.assertFalse(result)
        self.assertEqual(mock_requests_get.call_count, 2)
        mock_get_dex_issuer_url.assert_called_once()
        mock_requests_get.assert_called_with(
            "https://dex.example/healthz", timeout=1, verify=False
        )

    @mock.patch('k8sapp_openstack.utils.get_dex_health_check_config',
                return_value={"timeout": 3, "retries": 1, "verify": False, "endpoint": "/probe"})
    @mock.patch('k8sapp_openstack.utils.get_dex_issuer_url',
                return_value="https://dex.example")
    @mock.patch('k8sapp_openstack.utils.requests.get')
    def test_check_dex_healthy_uses_probe_endpoint_override(
        self, mock_requests_get, mock_get_dex_issuer_url, _
    ):
        """Ensure custom probe endpoint is appended to issuer URL."""
        response = mock.MagicMock()
        response.status_code = app_constants.DEX_HEALTHY_STATUS_CODE
        response.ok = True
        response.text = "ok"
        mock_requests_get.return_value = response

        result = app_utils.check_dex_healthy(mock.MagicMock(), dex_enabled=True)

        self.assertTrue(result)
        mock_requests_get.assert_called_once_with(
            "https://dex.example/probe", timeout=3, verify=False
        )

    @mock.patch('k8sapp_openstack.utils.get_services_fqdn_pattern')
    @mock.patch('k8sapp_openstack.utils.get_endpoint_domain')
    def test_get_external_service_url_keystone_https(self, mock_get_endpoint_domain,
                                                     mock_fqdn_pattern):
        """Test get_external_service_url with Keystone, FQDN configured and HTTPS"""
        mock_get_endpoint_domain.return_value = "example.com"
        mock_fqdn_pattern.return_value = "{service_name}.{endpoint_domain}"
        db_mock = mock.Mock()

        result = app_utils.get_external_service_url(
            dbapi=db_mock,
            service_name='keystone',
            https_ready=True
        )

        assert result == "https://keystone.example.com"

    @mock.patch('k8sapp_openstack.utils.get_services_fqdn_pattern')
    @mock.patch('k8sapp_openstack.utils.get_endpoint_domain')
    def test_get_external_service_url_horizon_http(self, mock_get_endpoint_domain,
                                                   mock_fqdn_pattern):
        """Test get_external_service_url with Horizon, FQDN configured and HTTP"""
        mock_get_endpoint_domain.return_value = "example.com"
        mock_fqdn_pattern.return_value = "{service_name}.{endpoint_domain}"
        db_mock = mock.Mock()

        result = app_utils.get_external_service_url(
            dbapi=db_mock,
            service_name='horizon',
            https_ready=False
        )

        assert result == "http://horizon.example.com"

    @mock.patch('k8sapp_openstack.utils.get_endpoint_domain')
    def test_get_external_service_url_without_fqdn(self, mock_get_endpoint_domain):
        """Test get_external_service_url returns empty string when FQDN not configured"""
        mock_get_endpoint_domain.return_value = ""
        db_mock = mock.Mock()

        result = app_utils.get_external_service_url(
            dbapi=db_mock,
            service_name='keystone',
            https_ready=True
        )

        assert result == ""

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response',
                return_value="ontap-nas:nfs:iscsi")
    @mock.patch('k8sapp_openstack.utils.is_netapp_storageclass_available',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value='trident')
    @mock.patch('k8sapp_openstack.utils.is_user_overrides_available',
                return_value=False)
    @mock.patch('sysinv.common.kubernetes.KubeOperator')
    def test_check_netapp_backends_nfs(self, mock_kube_operator, *_):
        """ Test if check_netapp_backends can find the 'nfs' backend
        """
        # Mocks for Netapp pods checking
        mock_pod_list = [mock.MagicMock()]
        kube_operator_instance = mock_kube_operator.return_value
        kube_operator_instance.kube_get_pods_by_selector.return_value = mock_pod_list

        backends_map = app_utils.check_netapp_backends()

        assert backends_map["nfs"]

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response',
                return_value="ontap-san:nfs:iscsi")
    @mock.patch('k8sapp_openstack.utils.is_netapp_storageclass_available',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value='trident')
    @mock.patch('k8sapp_openstack.utils.is_user_overrides_available',
                return_value=False)
    @mock.patch('sysinv.common.kubernetes.KubeOperator')
    def test_check_netapp_backends_iscsi(self, mock_kube_operator, *_):
        """ Test if check_netapp_backends can find the 'iscsi' backend
        """
        mock_pod_list = [mock.MagicMock()]
        kube_operator_instance = mock_kube_operator.return_value
        kube_operator_instance.kube_get_pods_by_selector.return_value = mock_pod_list

        backends_map = app_utils.check_netapp_backends()

        assert backends_map["iscsi"]

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response',
                return_value="ontap-san:nfs:fc")
    @mock.patch('k8sapp_openstack.utils.is_netapp_storageclass_available',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value='trident')
    @mock.patch('k8sapp_openstack.utils.is_user_overrides_available',
                return_value=False)
    @mock.patch('sysinv.common.kubernetes.KubeOperator')
    def test_check_netapp_backends_fc(self, mock_kube_operator, *_):
        """ Test if check_netapp_backends can find the 'fc' backend
        """
        mock_pod_list = [mock.MagicMock()]
        kube_operator_instance = mock_kube_operator.return_value
        kube_operator_instance.kube_get_pods_by_selector.return_value = mock_pod_list

        backends_map = app_utils.check_netapp_backends()

        assert backends_map["fc"]

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response',
                return_value="ontap-san:nfs:iscsi\nontap-nas:nfs:iscsi")
    @mock.patch('k8sapp_openstack.utils.is_netapp_storageclass_available',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value='trident')
    @mock.patch('k8sapp_openstack.utils.is_user_overrides_available',
                return_value=False)
    @mock.patch('sysinv.common.kubernetes.KubeOperator')
    def test_check_netapp_backends_multiple(self, mock_kube_operator, *_):
        """ Test if check_netapp_backends can find multiple backends
        """
        mock_pod_list = [mock.MagicMock()]
        kube_operator_instance = mock_kube_operator.return_value
        kube_operator_instance.kube_get_pods_by_selector.return_value = mock_pod_list

        backends_map = app_utils.check_netapp_backends()

        assert backends_map["nfs"] and backends_map["iscsi"]

    @mock.patch('k8sapp_openstack.utils.send_cmd_read_response',
                return_value="")
    @mock.patch('k8sapp_openstack.utils.is_netapp_storageclass_available',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application',
                return_value='trident')
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override',
                return_value=["ceph"])
    @mock.patch('k8sapp_openstack.utils.is_user_overrides_available',
                return_value=False)
    @mock.patch('sysinv.common.kubernetes.KubeOperator')
    def test_check_netapp_backends_none(self, mock_kube_operator, *_):
        """ Test if check_netapp_backends returns a backend_map with all
            values set to false when no backends are available
        """
        mock_pod_list = [mock.MagicMock()]
        kube_operator_instance = mock_kube_operator.return_value
        kube_operator_instance.kube_get_pods_by_selector.return_value = mock_pod_list

        backends_map = app_utils.check_netapp_backends()

        assert not any(backends_map.values())

    @mock.patch('k8sapp_openstack.utils._get_value_from_application')
    def test_get_enabled_storage_backends_from_override_netapp_nfs(self, mock_get_values):
        """ Test if get_enabled_storage_backends_from_override selects netapp-nfs
            when it's the only backend enabled
        """
        mock_get_values.return_value = [
            {"name": "ceph", "enabled": False},
            {"name": "netapp-nfs", "enabled": True},
            {"name": "netapp-iscsi", "enabled": False},
            {"name": "netapp-fc", "enabled": False},
        ]

        enabled_backends = app_utils.get_enabled_storage_backends_from_override()
        assert enabled_backends == ["netapp-nfs"]

    @mock.patch('k8sapp_openstack.utils._get_value_from_application')
    def test_get_enabled_storage_backends_from_override_multiple(self, mock_get_values):
        """ Test if get_enabled_storage_backends_from_override selects all the
            enabled backends found
        """
        mock_get_values.return_value = [
            {"name": "ceph", "enabled": True},
            {"name": "netapp-nfs", "enabled": False},
            {"name": "netapp-iscsi", "enabled": True},
            {"name": "netapp-fc", "enabled": False},
        ]

        enabled_backends = app_utils.get_enabled_storage_backends_from_override()
        assert enabled_backends == ["ceph", "netapp-iscsi"]

    @mock.patch('k8sapp_openstack.utils._get_value_from_application')
    def test_get_enabled_storage_backends_from_override_none(self, mock_get_values):
        """ Test if get_enabled_storage_backends_from_override returns an empty
            list if no backend is enabled
        """
        mock_get_values.return_value = [
            {"name": "ceph", "enabled": False},
            {"name": "netapp-nfs", "enabled": False},
            {"name": "netapp-iscsi", "enabled": False},
            {"name": "netapp-fc", "enabled": False},
        ]

        enabled_backends = app_utils.get_enabled_storage_backends_from_override()
        assert len(enabled_backends) == 0

    @mock.patch('k8sapp_openstack.utils._get_value_from_application')
    def test_get_storage_backends_priority_list(self, mock_get_values):
        """ Test if get_storage_backends_priority_list works properly
        """
        chart = app_constants.HELM_CHART_CINDER
        mock_get_values.return_value = [
            "netapp-nfs", "ceph", "netapp-iscsi", "netapp-fc"
        ]

        priority_list = app_utils.get_storage_backends_priority_list(chart)
        assert priority_list == ["netapp-nfs", "ceph", "netapp-iscsi", "netapp-fc"]

    @mock.patch('k8sapp_openstack.utils.is_netapp_storageclass_available', return_value=False)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value='trident')
    @mock.patch('k8sapp_openstack.utils.is_user_overrides_available', return_value=True)
    @mock.patch('k8sapp_openstack.utils.get_enabled_storage_backends_from_override')
    @mock.patch('sysinv.common.kubernetes.KubeOperator')
    def test_check_netapp_backends_from_override(self, mock_kube_operator, mock_enabled_backends, *_):
        """ Test if check_netapp_backends returns a backend_map with the
            values present in the override file
        """
        mock_pod_list = [mock.MagicMock()]
        kube_operator_instance = mock_kube_operator.return_value
        kube_operator_instance.kube_get_pods_by_selector.return_value = mock_pod_list

        mock_enabled_backends.return_value = ["netapp-nfs"]

        backends_map = app_utils.check_netapp_backends()

        assert backends_map["nfs"]

    @mock.patch("k8sapp_openstack.utils.subprocess.run")
    def test_get_netapp_storage_class_name(self, mock_run):
        """ Tests if get_netapp_storage_class_name returns a valid
            storage class name for netapp.
         """
        mock_process = mock.MagicMock()
        mock_process.stdout = "netapp-nas-backend ontap-nas"
        mock_process.stderr = ""
        mock_process.check_returncode.return_value = None
        mock_run.return_value = mock_process

        result = app_utils.get_netapp_storage_class_name(app_constants.BACKEND_TYPE_NETAPP_NFS)

        assert result == "netapp-nas-backend"
        mock_run.assert_called_once_with(
            args=["kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
            "get", "sc", "-o", "custom-columns=NAME:.metadata.name,TYPE:.parameters.backendType"],
            capture_output=True,
            text=True,
            check=True,
            shell=False
        )

    def test_get_endpoint_domain_without_parameter(self):
        """ Test whether get_endpoint_domain returns an empty value when
            service_parameter_get_one returns a false value.
        """
        db_mock = mock.Mock()
        db_mock.service_parameter_get_one.return_value = None

        result = app_utils.get_endpoint_domain(dbapi=db_mock)

        assert result == ""

    def test_get_endpoint_domain_with_parameter(self):
        """ Test whether get_endpoint_domain returns the expected value when
            service_parameter_get_one returns a true value.
        """
        endpoint_param = mock.Mock()
        endpoint_param.value = "example.com"
        db_mock = mock.Mock()
        db_mock.service_parameter_get_one.return_value = endpoint_param

        result = app_utils.get_endpoint_domain(dbapi=db_mock)

        assert result == "example.com"
