#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.helm import common
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.tests import test_plugins


class IronicHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                         base.HelmTestCaseMixin):
    def setUp(self):
        super(IronicHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class IronicGetOverrideTest(IronicHelmTestCase,
                            dbbase.ControllerHostTestCase):
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_ironic_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_IRONIC,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {},
            'network': {},
            'endpoints': {
                'baremetal': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            },
        })

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_ironic_reuses_glance_user(self, *_):
        overrides_glance = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_GLANCE,
            cnamespace=common.HELM_NS_OPENSTACK)
        overrides_ironic = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_IRONIC,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertEqual(
            overrides_ironic["endpoints"]["identity"]["auth"]["glance"],
            overrides_glance["endpoints"]["identity"]["auth"]["glance"],
        )
