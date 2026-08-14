#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.helm import common
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import prometheus_openstack_exporter
from k8sapp_openstack.tests import test_plugins


class PrometheusOpenstackExporterHelmTestCase(
        test_plugins.K8SAppOpenstackAppMixin,
        base.HelmTestCaseMixin):
    def setUp(self):
        super(PrometheusOpenstackExporterHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class PrometheusOpenstackExporterIsEnabledTest(
        PrometheusOpenstackExporterHelmTestCase,
        dbbase.ControllerHostTestCase):
    def setUp(self):
        super(PrometheusOpenstackExporterIsEnabledTest, self).setUp()
        self.plugin = \
            prometheus_openstack_exporter.PrometheusOpenstackExporterHelm(
                self.operator)

    @mock.patch('k8sapp_openstack.utils.is_central_cloud', return_value=True)
    def test_is_enabled_true_on_central_cloud(self, *_):
        """On a Central Cloud (System Controller) the chart is always
        enabled so its image is downloaded during "application-upload
        --images" and subclouds can pull it."""
        self.assertTrue(self.plugin._is_enabled(
            self.app_name,
            app_constants.HELM_CHART_PROMETHEUS_OPENSTACK_EXPORTER,
            common.HELM_NS_OPENSTACK))

    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._is_enabled',
        return_value=False)
    @mock.patch('k8sapp_openstack.utils.is_central_cloud', return_value=False)
    def test_is_enabled_defers_to_base_when_disabled(self, *_):
        """Outside a Central Cloud, defers to the default logic; disabled
        by default (via disabled_charts)."""
        self.assertFalse(self.plugin._is_enabled(
            self.app_name,
            app_constants.HELM_CHART_PROMETHEUS_OPENSTACK_EXPORTER,
            common.HELM_NS_OPENSTACK))

    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._is_enabled',
        return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_central_cloud', return_value=False)
    def test_is_enabled_defers_to_base_when_enabled(self, *_):
        """Outside a Central Cloud, enabled if the operator enabled it
        (default logic returns True)."""
        self.assertTrue(self.plugin._is_enabled(
            self.app_name,
            app_constants.HELM_CHART_PROMETHEUS_OPENSTACK_EXPORTER,
            common.HELM_NS_OPENSTACK))
