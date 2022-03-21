#
# Copyright (c) 2022 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock

from k8sapp_openstack.lifecycle import lifecycle_openstack

from sysinv.tests.db import base as dbbase


class OpenstackAppLifecycleOperatorTest(dbbase.ControllerHostTestCase):
    def setUp(self):
        super(OpenstackAppLifecycleOperatorTest, self).setUp()
        self.lifecycle = lifecycle_openstack.OpenstackAppLifecycleOperator()

    @mock.patch("k8sapp_openstack.utils.https_enabled", return_value=True)
    @mock.patch(
        "k8sapp_openstack.utils.is_openstack_https_certificates_ready",
        return_value=False,
    )
    def test__semantic_check_openstack_https_ready_certificates_not_ready(self, *_):
        self.assertTrue(self.lifecycle._semantic_check_openstack_https_not_ready())

    @mock.patch("k8sapp_openstack.utils.https_enabled", return_value=True)
    @mock.patch(
        "k8sapp_openstack.utils.is_openstack_https_certificates_ready",
        return_value=True,
    )
    def test__semantic_check_openstack_https_ready_certificates_ready(self, *_):
        self.assertFalse(self.lifecycle._semantic_check_openstack_https_not_ready())

    @mock.patch("k8sapp_openstack.utils.https_enabled", return_value=False)
    @mock.patch(
        "k8sapp_openstack.utils.is_openstack_https_certificates_ready",
        return_value=False,
    )
    def test__semantic_check_openstack_https_not_ready_certificates_not_ready(self, *_):
        self.assertFalse(self.lifecycle._semantic_check_openstack_https_not_ready())

    @mock.patch("k8sapp_openstack.utils.https_enabled", return_value=False)
    @mock.patch(
        "k8sapp_openstack.utils.is_openstack_https_certificates_ready",
        return_value=True,
    )
    def test__semantic_check_openstack_https_not_ready_certificates_ready(self, *_):
        self.assertFalse(self.lifecycle._semantic_check_openstack_https_not_ready())
