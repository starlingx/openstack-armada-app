#
# Copyright (c) 2022 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from oslo_utils import uuidutils
from sysinv.common import constants
from sysinv.tests.db import base as dbbase

from k8sapp_openstack import utils as app_utils


class UtilsTest(dbbase.ControllerHostTestCase):
    def setUp(self):
        super(UtilsTest, self).setUp()

    def test_is_openstack_https_certificates_ready(self):
        self.dbapi.certificate_create(
            {
                "id": 1,
                "uuid": uuidutils.generate_uuid(),
                "certtype": constants.CERT_MODE_OPENSTACK,
                "signature": "abcdef",
            }
        )

        self.dbapi.certificate_create(
            {
                "id": 2,
                "uuid": uuidutils.generate_uuid(),
                "certtype": constants.CERT_MODE_OPENSTACK_CA,
                "signature": "abcdef",
            }
        )

        self.dbapi.certificate_create(
            {
                "id": 3,
                "uuid": uuidutils.generate_uuid(),
                "certtype": constants.CERT_MODE_SSL_CA,
                "signature": "abcdef",
            }
        )

        self.assertTrue(app_utils.is_openstack_https_certificates_ready())

    def test_is_openstack_https_certificates_ready_false(self):
        self.dbapi.certificate_create(
            {
                "id": 3,
                "uuid": uuidutils.generate_uuid(),
                "certtype": constants.CERT_MODE_DOCKER_REGISTRY,
                "signature": "abcdef",
            }
        )

        self.assertFalse(app_utils.is_openstack_https_certificates_ready())

    @mock.patch('k8sapp_openstack.utils.https_enabled', return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_certificates_ready', return_value=True)
    def test_is_openstack_https_ready_true(self, *_):
        self.assertTrue(app_utils.is_openstack_https_ready())

    @mock.patch('k8sapp_openstack.utils.https_enabled', return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_certificates_ready', return_value=False)
    def test_is_openstack_https_ready_false(self, *_):
        self.assertFalse(app_utils.is_openstack_https_ready())
