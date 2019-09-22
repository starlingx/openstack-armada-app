#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from k8sapp_openstack.helm import nova

from sysinv.helm import helm
from sysinv.common import constants

from sysinv.tests.db import base as dbbase


class NovaGetOverrideTest(dbbase.ControllerHostTestCase):

    def setUp(self):
        super(NovaGetOverrideTest, self).setUp()
        self.operator = helm.HelmOperator(self.dbapi)
        self.nova = nova.NovaHelm(self.operator)
        self.worker = self._create_test_host(
            personality=constants.WORKER,
            administrative=constants.ADMIN_LOCKED)
        self.ifaces = self._create_test_host_platform_interface(self.worker)
        self.dbapi.address_create({
            'name': 'test',
            'family': self.oam_subnet.version,
            'prefix': self.oam_subnet.prefixlen,
            'address': str(self.oam_subnet[24]),
            'interface_id': self.ifaces[0].id,
            'enable_dad': self.oam_subnet.version == 6
        })

    def test_update_host_addresses(self):
        self.nova._update_host_addresses(self.worker, {}, {}, {})
