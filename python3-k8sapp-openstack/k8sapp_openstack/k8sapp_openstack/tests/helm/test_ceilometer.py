#
# Copyright (c) 2020-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.common import exception
from sysinv.helm import common
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.tests import test_plugins


class CeilometerHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                             base.HelmTestCaseMixin):
    def setUp(self):
        super(CeilometerHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class CeilometerGetOverrideTest(CeilometerHelmTestCase,
                                dbbase.ControllerHostTestCase):
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_ceilometer_overrides(self, mock_get_url, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CEILOMETER,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {
                'replicas': {},
            },
            'conf': {
                'ceilometer': {
                    'notification': {
                        'messaging_urls': {'values': mock.ANY},
                    },
                    'meter': {
                        'meter_definitions_dirs': '/etc/ceilometer/meters.d',
                    },
                },
            },
            'manifests': {
                'daemonset_ipmi': False,
            },
            'endpoints': {
                'identity': {},
                'oslo_cache': {},
                'oslo_messaging': {},
            },
        })
        messaging_urls = overrides['conf']['ceilometer'][
            'notification']['messaging_urls']['values']
        self.assertEqual(
            ['rabbit://fake/ceilometer', 'rabbit://fake/cinder',
             'rabbit://fake/glance', 'rabbit://fake/nova',
             'rabbit://fake/keystone', 'rabbit://fake/neutron',
             'rabbit://fake/heat'],
            messaging_urls)
        mock_get_url.assert_any_call('/ceilometer')
        mock_get_url.assert_any_call('/cinder')
        mock_get_url.assert_any_call('/glance')
        mock_get_url.assert_any_call('/nova')
        mock_get_url.assert_any_call('/keystone')
        mock_get_url.assert_any_call('/neutron')
        mock_get_url.assert_any_call('/heat')
        self.assertNotIn('metering', overrides['endpoints'])
        self.assertNotIn('polling', overrides['conf']['ceilometer'])
        self.assertNotIn(
            'keystone_authtoken', overrides['conf']['ceilometer'])
        self.assertNotIn(
            'service_credentials', overrides['conf']['ceilometer'])
        self.assertNotIn('certificates', overrides['manifests'])

    @mock.patch('os.path.exists', return_value=True)
    @mock.patch('six.moves.builtins.open', mock.mock_open(read_data="fake"))
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=True)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm.get_ca_file',
        return_value='/etc/ssl/private/openstack/ca-cert.pem'
    )
    @mock.patch(
        'k8sapp_openstack.utils.get_openstack_certificate_values',
        return_value={
            app_constants.OPENSTACK_CERT: 'fake',
            app_constants.OPENSTACK_CERT_KEY: 'fake',
            app_constants.OPENSTACK_CERT_CA: 'fake'
        }
    )
    def test_ceilometer_overrides_https_wires_tls(self, *_):
        """
        Asserts that manifests.certificates and service_credentials.cafile
        are set when OpenStack HTTPS is enabled.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CEILOMETER,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertTrue(overrides['manifests']['certificates'])
        self.assertEqual(
            overrides['conf']['ceilometer']['service_credentials']['cafile'],
            '/etc/ssl/private/openstack/ca-cert.pem')
        self.assertNotIn(
            'keystone_authtoken', overrides['conf']['ceilometer'])
        self.assertNotIn('metering', overrides['endpoints'])

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_ceilometer_overrides_invalid_namespace(self, *_):
        """
        Asserts that an exception is raised if an invalid namespace
        is given when retrieving Helm override parameters.
        """
        self.assertRaises(exception.InvalidHelmNamespace,
                          self.operator.get_helm_chart_overrides,
                          app_constants.HELM_CHART_CEILOMETER,
                          cnamespace=common.HELM_NS_DEFAULT)

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_ceilometer_overrides_missing_namespace(self, *_):
        """
        Tests that the default Helm override parameters
        are returned when no namespace is passed.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CEILOMETER)
        self.assertIsInstance(overrides, dict)
        self.assertIn(common.HELM_NS_OPENSTACK, overrides)
