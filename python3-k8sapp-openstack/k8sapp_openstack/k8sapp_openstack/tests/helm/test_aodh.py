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
from k8sapp_openstack.helm import aodh
from k8sapp_openstack.tests import test_plugins


class AodhHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                       base.HelmTestCaseMixin):
    def setUp(self):
        super(AodhHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class AodhGetOverrideTest(AodhHelmTestCase,
                          dbbase.ControllerHostTestCase):
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_aodh_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_AODH,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {},
            'endpoints': {
                'alarming': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            },
            'conf': {},
        })

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
    def test_aodh_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_AODH,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'conf': {
                'aodh': {
                    'keystone_authtoken': {
                        'cafile': aodh.AodhHelm.get_ca_file(),
                    },
                    'service_credentials': {
                        'region_name': mock.ANY,
                    }
                },
            },
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': aodh.AodhHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'aodh': {
                            'cacert': aodh.AodhHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                },
                'alarming': {
                    'host_fqdn_override': {
                        'public': {
                            'tls': {
                                'ca': 'fake',
                                'crt': 'fake',
                                'key': 'fake',
                            },
                        },
                    },
                },
            },
            'manifests': {
                'certificates': True,
            },
        })

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_aodh_overrides_invalid_namespace(self, *_):
        """
        Asserts that an exception is raised if an invalid namespace
        is given when retrieving Helm override parameters.
        """
        self.assertRaises(exception.InvalidHelmNamespace,
                          self.operator.get_helm_chart_overrides,
                          app_constants.HELM_CHART_AODH,
                          cnamespace=common.HELM_NS_DEFAULT)

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_aodh_overrides_missing_namespace(self, *_):
        """
        Tests that the default Helm override parameters
        are returned when no namespace is passed.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_AODH)
        self.assertIsInstance(overrides, dict)
        self.assertIn(common.HELM_NS_OPENSTACK, overrides)

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_service_region_name')
    def test_aodh_get_region_name(self, mock_get_region, *_):
        """
        Tests the injected service region name in override parameters.
        """
        mock_get_region.return_value = 'regionA'
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_AODH)
        mock_get_region.assert_called_with(app_constants.HELM_CHART_AODH)
        self.assertIsInstance(overrides, dict)
        result_service_conf = overrides[common.HELM_NS_OPENSTACK]['conf'][app_constants.HELM_CHART_AODH]
        result_region_name = result_service_conf['service_credentials']['region_name']
        self.assertEqual('regionA', result_region_name)

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        return_value=(
            'rabbit://rabbitmq-admin:fake-pass@'
            'rabbitmq.openstack.svc.cluster.local:5672/ceilometer'))
    def test_aodh_overrides_notification_transport_url(self, mock_get_url, *_):
        """
        Asserts that the Aodh notification transport_url is set from the
        shared rabbitmq notification URL helper, using the ceilometer
        vhost.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_AODH,
            cnamespace=common.HELM_NS_OPENSTACK)
        transport_url = overrides['conf']['aodh'][
            'oslo_messaging_notifications']['transport_url']
        self.assertEqual(
            'rabbit://rabbitmq-admin:fake-pass@'
            'rabbitmq.openstack.svc.cluster.local:5672/ceilometer',
            transport_url)
        mock_get_url.assert_called_once_with('/ceilometer')

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_aodh_overrides_no_default_transport_url(self, *_):
        """
        Asserts that the plugin does not emit conf.aodh.DEFAULT, leaving
        the chart's OSH-generated /aodh transport_url fallback untouched.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_AODH,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertNotIn('DEFAULT', overrides['conf']['aodh'])

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
    def test_aodh_overrides_https_enabled_has_notification_transport_url(
            self, *_):
        """
        Asserts that the notification transport_url override coexists
        with the keystone_authtoken.cafile override when HTTPS is
        enabled.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_AODH,
            cnamespace=common.HELM_NS_OPENSTACK)
        transport_url = overrides['conf']['aodh'][
            'oslo_messaging_notifications']['transport_url']
        self.assertIn('/ceilometer', transport_url)
        self.assertEqual(
            overrides['conf']['aodh']['keystone_authtoken']['cafile'],
            aodh.AodhHelm.get_ca_file())
