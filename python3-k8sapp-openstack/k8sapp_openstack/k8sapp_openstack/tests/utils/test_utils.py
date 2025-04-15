#
# Copyright (c) 2022-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.common import constants
from sysinv.helm import common as helm_common
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

    def test_is_openvswitch_enabled_true(self):
        """Test is_openvswitch_enabled returns True when openvswitch
        is enabled.
        """
        mock_host = mock.MagicMock()
        mock_host.id = 1
        mock_host.invprovision = constants.PROVISIONED
        mock_host.ihost_action = constants.UNLOCK_ACTION
        mock_label = mock.MagicMock()
        mock_label.label_key = helm_common.LABEL_OPENVSWITCH
        mock_label.label_value = helm_common.LABEL_VALUE_ENABLED

        hosts = [mock_host]
        labels_by_hostid = {
            mock_host.id: [mock_label]
        }

        with mock.patch('k8sapp_openstack.utils.cutils.get_personalities',
                        return_value=[constants.WORKER]), \
            mock.patch('k8sapp_openstack.utils.cutils.has_openstack_compute',
                return_value=True):
            result = app_utils.is_openvswitch_enabled(hosts, labels_by_hostid)
            self.assertTrue(result)

    def test_is_openvswitch_enabled_false(self):
        """Test is_openvswitch_enabled returns False when openvswitch
        is not enabled.
        """
        mock_host = mock.MagicMock()
        mock_host.id = 1
        mock_host.invprovision = constants.PROVISIONED
        mock_host.ihost_action = constants.UNLOCK_ACTION

        mock_label = mock.MagicMock()
        mock_label.label_key = "fake_label"
        mock_label.label_value = "fake_value"

        hosts = [mock_host]
        labels_by_hostid = {
            mock_host.id: [mock_label]
        }

        with mock.patch('k8sapp_openstack.utils.cutils.get_personalities',
                        return_value=[constants.WORKER]), \
            mock.patch('k8sapp_openstack.utils.cutils.has_openstack_compute',
                return_value=True):
            result = app_utils.is_openvswitch_enabled(hosts, labels_by_hostid)
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

    @mock.patch('cephclient.wrapper.CephWrapper')
    @mock.patch('k8sapp_openstack.utils.is_rook_ceph_api_available',
                return_value=True)
    def test_get_rook_ceph_uuid(self, mock_api_available, mock_ceph_wrapper):
        """Test get_rook_ceph_uuid for rook ceph api available and responding ok
        """
        mock_fsid = '89bd29e9-c505-4170-a097-04dc8e43c897'
        mock_response = mock.MagicMock()
        mock_response.ok = True
        ceph_instance = mock_ceph_wrapper.return_value
        ceph_instance.fsid.return_value = mock_response, mock_fsid

        result = app_utils.get_rook_ceph_uuid()
        self.assertEqual(result, mock_fsid)
        ceph_instance.fsid.assert_called_once()
        mock_api_available.assert_called_once()

    @mock.patch('cephclient.wrapper.CephWrapper')
    @mock.patch('k8sapp_openstack.utils.is_rook_ceph_api_available',
                return_value=True)
    def test_get_rook_ceph_uuid_nok(self,
                                    mock_api_available,
                                    mock_ceph_wrapper):
        """Test get_rook_ceph_uuid for rook ceph api available but not responding ok
        """
        mock_fsid = None
        mock_response = mock.MagicMock()
        mock_response.ok = False
        ceph_instance = mock_ceph_wrapper.return_value
        ceph_instance.fsid.return_value = mock_response, mock_fsid

        result = app_utils.get_rook_ceph_uuid()
        self.assertEqual(result, None)
        ceph_instance.fsid.assert_called_once()
        mock_api_available.assert_called_once()

    @mock.patch('cephclient.wrapper.CephWrapper')
    @mock.patch('k8sapp_openstack.utils.is_rook_ceph_api_available',
                return_value=False)
    def test_get_rook_ceph_uuid_unavailable(self,
                                            mock_api_available,
                                            mock_ceph_wrapper):
        """Test get_rook_ceph_uuid for rook ceph api not available
        """
        mock_fsid = None
        mock_response = mock.MagicMock()
        mock_response.ok = False
        ceph_instance = mock_ceph_wrapper.return_value
        ceph_instance.fsid.return_value = mock_response, mock_fsid

        result = app_utils.get_rook_ceph_uuid()
        self.assertEqual(result, None)
        ceph_instance.fsid.assert_not_called()
        mock_api_available.assert_called_once()

    @mock.patch('cephclient.wrapper.CephWrapper')
    @mock.patch('k8sapp_openstack.utils.is_rook_ceph_api_available',
                return_value=True)
    def test_get_rook_ceph_uuid_api_exception(self,
                                              mock_api_available,
                                              mock_ceph_wrapper):
        """Test get_rook_ceph_uuid for rook ceph api exception
        """
        mock_response = mock.MagicMock()
        mock_response.ok = False
        ceph_instance = mock_ceph_wrapper.return_value
        ceph_instance.fsid.side_effect = Exception()

        result = app_utils.get_rook_ceph_uuid()
        self.assertEqual(result, None)
        ceph_instance.fsid.assert_called_once()
        mock_api_available.assert_called_once()

    @mock.patch('sysinv.db.api.get_instance')
    def test_is_rook_backend_available(self, mock_dbapi_get_instance):
        """Test is_rook_backend_available for rook ceph configured and applied
        """
        mock_backend_list = [mock.MagicMock()]
        mock_backend_list[0].state = constants.SB_STATE_CONFIGURED
        mock_backend_list[0].task = constants.APP_APPLY_SUCCESS
        db_instance = mock_dbapi_get_instance.return_value
        db_instance.storage_backend_get_list_by_type.return_value = mock_backend_list

        result = app_utils.is_rook_ceph_backend_available()
        self.assertEqual(result, True)
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

        result = app_utils.is_rook_ceph_backend_available()
        self.assertEqual(result, False)
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

        result = app_utils.is_rook_ceph_backend_available()
        self.assertEqual(result, False)
        db_instance.storage_backend_get_list_by_type.assert_called_once_with(
            backend_type=constants.SB_TYPE_CEPH_ROOK
        )

    @mock.patch('sysinv.db.api.get_instance', return_value=None)
    def test_is_rook_backend_available_none_db(self, mock_dbapi_get_instance):
        """Test is_rook_backend_available for dbapi failure
        """
        result = app_utils.is_rook_ceph_backend_available()
        self.assertEqual(result, False)
        mock_dbapi_get_instance.assert_called_once_with()

    @mock.patch('sysinv.db.api.get_instance')
    def test_is_rook_backend_available_empty(self, mock_dbapi_get_instance):
        """Test is_rook_backend_available for empty list of rook ceph backends
        """
        mock_backend_list = []
        db_instance = mock_dbapi_get_instance.return_value
        db_instance.storage_backend_get_list_by_type.return_value = mock_backend_list

        result = app_utils.is_rook_ceph_backend_available()
        self.assertEqual(result, False)
        db_instance.storage_backend_get_list_by_type.assert_called_once_with(
            backend_type=constants.SB_TYPE_CEPH_ROOK
        )

    @mock.patch('sysinv.common.kubernetes.KubeOperator')
    def test_is_rook_ceph_api_available(self, mock_kube_operator):
        """Test is_rook_backend_available for rook api pod in Running state
        """
        mock_pod_list = [mock.MagicMock()]
        mock_pod_list[0].metadata.name = \
            f'{app_constants.CEPH_ROOK_MANAGER_APP}-a-74cf47c859-8cgsx'
        kube_operator_instance = mock_kube_operator.return_value
        kube_operator_instance.kube_get_pods_by_selector.return_value = mock_pod_list
        result = app_utils.is_rook_ceph_api_available()
        self.assertEqual(result, True)
        kube_operator_instance.kube_get_pods_by_selector.assert_called_once_with(
            app_constants.HELM_NS_ROOK_CEPH,
            f"app={app_constants.CEPH_ROOK_MANAGER_APP}",
            app_constants.POD_SELECTOR_RUNNING
        )

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
