#
# Copyright (c) 2022 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock

from oslo_utils import uuidutils

from k8sapp_openstack.helm import openstack
from sysinv.common import constants
from sysinv.helm import helm

from sysinv.tests.db import base as dbbase


class OpenstackBaseHelmTest(dbbase.ControllerHostTestCase):
    def setUp(self):
        super(OpenstackBaseHelmTest, self).setUp()
        self.operator = helm.HelmOperator(self.dbapi)
        self.openstack = openstack.OpenstackBaseHelm(self.operator)

    @mock.patch.object(openstack.OpenstackBaseHelm, "_https_enabled",
                       return_value=True)
    def test_is_openstack_https_ready_true(self, _):
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

        self.assertTrue(self.openstack._is_openstack_https_ready())

    @mock.patch.object(openstack.OpenstackBaseHelm, "_https_enabled",
                       return_value=True)
    def test_is_openstack_https_ready_false(self, _):
        self.dbapi.certificate_create(
            {
                "id": 3,
                "uuid": uuidutils.generate_uuid(),
                "certtype": constants.CERT_MODE_DOCKER_REGISTRY,
                "signature": "abcdef",
            }
        )

        self.assertFalse(self.openstack._is_openstack_https_ready())
