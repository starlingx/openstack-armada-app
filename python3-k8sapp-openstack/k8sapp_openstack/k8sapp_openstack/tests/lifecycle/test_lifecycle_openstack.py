#
# Copyright (c) 2022 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
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
        'k8sapp_openstack.utils.get_openstack_certificate_files',
        return_value={
            app_constants.OPENSTACK_CERT: '/etc/ssl/private/openstack/cert.pem',
            app_constants.OPENSTACK_CERT_KEY: '/etc/ssl/private/openstack/key.pem',
            app_constants.OPENSTACK_CERT_CA: '/etc/ssl/private/openstack/ca-cert.pem'
        }
    )
    def test__semantic_check_openstack_https_ready(self, *_):
        self.assertTrue(self.lifecycle._semantic_check_openstack_https_ready())
