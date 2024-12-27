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
