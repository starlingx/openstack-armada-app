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
    @mock.patch('k8sapp_openstack.helm.aodh.is_aodh_rest_notifier_tls_enabled', return_value=False)
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
    @mock.patch('k8sapp_openstack.helm.aodh.is_aodh_rest_notifier_tls_enabled', return_value=False)
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

    @mock.patch('k8sapp_openstack.helm.aodh.is_aodh_rest_notifier_tls_enabled', return_value=False)
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

    @mock.patch('k8sapp_openstack.helm.aodh.is_aodh_rest_notifier_tls_enabled', return_value=False)
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

    @mock.patch('k8sapp_openstack.helm.aodh.is_aodh_rest_notifier_tls_enabled', return_value=False)
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

    @mock.patch('k8sapp_openstack.helm.aodh.is_aodh_rest_notifier_tls_enabled', return_value=False)
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

    @mock.patch('k8sapp_openstack.helm.aodh.is_aodh_rest_notifier_tls_enabled', return_value=False)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_aodh_overrides_no_default_transport_url(self, *_):
        """
        Asserts that the plugin does not emit conf.aodh.DEFAULT, leaving
        the chart's OSH-generated /aodh transport_url fallback untouched.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_AODH,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertNotIn('transport_url', overrides['conf']['aodh']['DEFAULT'])

    @mock.patch('os.path.exists', return_value=True)
    @mock.patch('six.moves.builtins.open', mock.mock_open(read_data="fake"))
    @mock.patch('k8sapp_openstack.helm.aodh.is_aodh_rest_notifier_tls_enabled', return_value=False)
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

    @mock.patch('k8sapp_openstack.helm.aodh.is_aodh_rest_notifier_tls_enabled', return_value=False)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_aodh_overrides_rest_notifier_host_cert_disabled(self, *_):
        """Tests that Aodh rest notifier certificate configuration
        is not injected when it has not been enabled.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_AODH,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertIn('DEFAULT', overrides['conf']['aodh'])
        defaults = overrides['conf']['aodh']['DEFAULT']
        self.assertNotIn('rest_notifier_ca_bundle_certificate_path', defaults)
        notifier_pod = overrides['pod']['mounts']['aodh_notifier']['aodh_notifier']
        self.assertEqual(len(notifier_pod['volumes']), 0)
        self.assertEqual(len(notifier_pod['volumeMounts']), 0)

    @mock.patch('k8sapp_openstack.helm.aodh.is_aodh_rest_notifier_tls_enabled', return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_aodh_overrides_rest_notifier_host_cert_enabled_conf(self, *_):
        """Tests that the proper aodh.conf key is set to enabled custom
        host verification certificate for Aodh rest notifier requests."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_AODH,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertIn('DEFAULT', overrides['conf']['aodh'])
        defaults = overrides['conf']['aodh']['DEFAULT']
        self.assertIn('rest_notifier_ca_bundle_certificate_path', defaults)
        self.assertEqual(defaults['rest_notifier_ca_bundle_certificate_path'],
                         app_constants.AODH_REST_NOTIFIER_CA_CERT_MOUNT_PATH)

    @mock.patch('k8sapp_openstack.helm.aodh.is_aodh_rest_notifier_tls_enabled', return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_aodh_overrides_rest_notifier_host_cert_enabled_mounts(self, *_):
        """Tests that the volume mounts are injected into the Aodh notifier
        pod bound to the holder secret of host certificate."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_AODH,
            cnamespace=common.HELM_NS_OPENSTACK)
        notifier_pod = overrides['pod']['mounts']['aodh_notifier']['aodh_notifier']
        self.assertEqual(len(notifier_pod['volumes']), 1)
        self.assertEqual(len(notifier_pod['volumeMounts']), 1)
        self.assertEqual(notifier_pod['volumes'][0], {
                    'name': app_constants.AODH_REST_NOTIFIER_CA_CERT_SECRET_NAME,
                    'secret': {
                        'secretName': app_constants.AODH_REST_NOTIFIER_CA_CERT_SECRET_NAME,
                        'items': [{
                            'key': app_constants.AODH_REST_NOTIFIER_CA_CERT_SECRET_KEY,
                            'path': app_constants.AODH_REST_NOTIFIER_CA_CERT_SECRET_KEY
                        }]
                    }
                })
        self.assertEqual(notifier_pod['volumeMounts'][0], {
                    'name': app_constants.AODH_REST_NOTIFIER_CA_CERT_SECRET_NAME,
                    'mountPath': app_constants.AODH_REST_NOTIFIER_CA_CERT_MOUNT_PATH,
                    'subPath': app_constants.AODH_REST_NOTIFIER_CA_CERT_SECRET_KEY,
                    'readOnly': True
                })

    @mock.patch('k8sapp_openstack.helm.aodh.is_platform_app_available', return_value=False)
    @mock.patch('k8sapp_openstack.helm.aodh.is_aodh_rest_notifier_tls_enabled', return_value=False)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_aodh_overrides_prometheus_endpoint_not_available(self, *_):
        """Tests that the Prometheus endpoint configuration is disabled when
        the platform app is not available.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_AODH,
            cnamespace=common.HELM_NS_OPENSTACK)
        conf = overrides['conf']
        self.assertIn('prometheus', conf)
        self.assertIn('enabled', conf['prometheus'])
        self.assertEqual(False, conf['prometheus']['enabled'])

    @mock.patch('k8sapp_openstack.helm.aodh.is_platform_app_available', return_value=True)
    @mock.patch('k8sapp_openstack.helm.aodh.is_aodh_rest_notifier_tls_enabled', return_value=False)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_aodh_overrides_prometheus_endpoint_available(self, *_):
        """Tests that Prometheus endpoint configuration present in static overrides
        is preserved when the prometheus app is available in the platform.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_AODH,
            cnamespace=common.HELM_NS_OPENSTACK)
        conf = overrides['conf']
        self.assertNotIn('prometheus', conf)
