#
# Copyright (c) 2022 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
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
