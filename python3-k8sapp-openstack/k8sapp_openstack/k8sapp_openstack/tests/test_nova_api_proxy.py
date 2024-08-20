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


class NovaApiProxyTestCase(test_plugins.K8SAppOpenstackAppMixin,
                           base.HelmTestCaseMixin):

    def setUp(self):
        super(NovaApiProxyTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class NovaApiProxyIPv4ControllerHostTestCase(NovaApiProxyTestCase,
                                             dbbase.ProvisionedControllerHostTestCase):

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_replicas(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA_API_PROXY,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            # Only one replica for a single controller
            'pod': {'replicas': {'proxy': 1}}
        })


class NovaApiProxyIPv4AIODuplexSystemTestCase(NovaApiProxyTestCase,
                                             dbbase.ProvisionedAIODuplexSystemTestCase):

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_replicas(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA_API_PROXY,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            # Expect two replicas because there are two controllers
            'pod': {'replicas': {'proxy': 2}}
        })
