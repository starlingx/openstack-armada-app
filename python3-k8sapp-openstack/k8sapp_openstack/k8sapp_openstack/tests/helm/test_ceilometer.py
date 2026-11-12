#
# Copyright (c) 2020-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import os

import mock
from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm import common
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base
import testtools
import yaml

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
    def test_ceilometer_overrides_servicemonitor_defaults_not_overridden(self, *_):
        """
        Asserts that servicemonitor_central, servicemonitor_compute,
        service_central_metrics, and service_compute_metrics are NOT
        present in manifests overrides by default, allowing chart-level
        defaults (via static-overrides) to take effect.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CEILOMETER,
            cnamespace=common.HELM_NS_OPENSTACK)
        manifests = overrides['manifests']
        self.assertNotIn('servicemonitor_central', manifests)
        self.assertNotIn('servicemonitor_compute', manifests)
        self.assertNotIn('service_central_metrics', manifests)
        self.assertNotIn('service_compute_metrics', manifests)
        # daemonset_ipmi must still be present
        self.assertFalse(manifests['daemonset_ipmi'])

    @mock.patch(
        'k8sapp_openstack.helm.ceilometer.CeilometerHelm'
        '._is_servicemonitor_disabled',
        return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_ceilometer_overrides_servicemonitor_disabled(self, *_):
        """
        Asserts that when _is_servicemonitor_disabled() returns True,
        only the ServiceMonitor toggles are explicitly set to False in
        manifests overrides, while the metrics Service toggles are left
        untouched (independent axis).
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CEILOMETER,
            cnamespace=common.HELM_NS_OPENSTACK)
        manifests = overrides['manifests']
        self.assertFalse(manifests['servicemonitor_central'])
        self.assertFalse(manifests['servicemonitor_compute'])
        self.assertNotIn('service_central_metrics', manifests)
        self.assertNotIn('service_compute_metrics', manifests)
        # daemonset_ipmi must still be present
        self.assertFalse(manifests['daemonset_ipmi'])

    @mock.patch(
        'k8sapp_openstack.helm.ceilometer.CeilometerHelm'
        '._is_metrics_service_disabled',
        return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_ceilometer_overrides_metrics_service_disabled(self, *_):
        """
        Asserts that when _is_metrics_service_disabled() returns True,
        the metrics Service toggles AND the ServiceMonitor toggles are
        explicitly set to False in manifests overrides, since
        ServiceMonitors depend on the metrics Services.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CEILOMETER,
            cnamespace=common.HELM_NS_OPENSTACK)
        manifests = overrides['manifests']
        self.assertFalse(manifests['service_central_metrics'])
        self.assertFalse(manifests['service_compute_metrics'])
        self.assertFalse(manifests['servicemonitor_central'])
        self.assertFalse(manifests['servicemonitor_compute'])
        # daemonset_ipmi must still be present
        self.assertFalse(manifests['daemonset_ipmi'])

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

    def _enable_watcher_chart_flag(self):
        """Seeds the application-level flag of the watcher chart as ON."""
        dbutils.create_test_helm_overrides(
            app_id=self.app.id,
            name=app_constants.HELM_CHART_WATCHER,
            namespace=common.HELM_NS_OPENSTACK,
            system_overrides={common.HELM_CHART_ATTR_ENABLED: True})

    def _add_compute_worker(self, unit):
        worker = self._create_test_host(
            personality=constants.WORKER,
            administrative=constants.ADMIN_LOCKED,
            unit=unit)
        dbutils.create_test_label(host_id=worker.id,
                                  label_key=common.LABEL_COMPUTE_LABEL,
                                  label_value=common.LABEL_VALUE_ENABLED)
        return worker

    def _get_overrides(self):
        return self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CEILOMETER,
            cnamespace=common.HELM_NS_OPENSTACK)

    def _assert_no_watcher_settings(self, overrides):
        self.assertNotIn('compute', overrides['conf']['ceilometer'])
        self.assertNotIn('polling', overrides['conf'])

    def _assert_watcher_settings(self, overrides):
        compute = overrides['conf']['ceilometer']['compute']
        self.assertEqual(
            app_constants.CEILOMETER_WATCHER_INSTANCE_DISCOVERY_METHOD,
            compute['instance_discovery_method'])
        self.assertIs(False, compute['fetch_extra_metadata'])
        sources = overrides['conf']['polling']['sources']
        self.assertEqual(
            ['openstack_compute', 'openstack_image_service',
             'openstack_block_storage', 'openstack_networking'],
            [source['name'] for source in sources])
        self.assertEqual(
            app_constants.CEILOMETER_WATCHER_COMPUTE_POLLING_INTERVAL,
            sources[0]['interval'])
        # Only the compute interval changes. The meters and the other
        # sources are sent as they are in the static overrides.
        self.assertEqual(
            app_constants.CEILOMETER_POLLING_SOURCES[0]['meters'],
            sources[0]['meters'])
        self.assertEqual(app_constants.CEILOMETER_POLLING_SOURCES[1:],
                         sources[1:])

    @mock.patch('k8sapp_openstack.helm.ceilometer.is_watcher_enabled',
                return_value=False)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_ceilometer_no_watcher_settings_when_gate_closed(
            self, _url, _https, _gate):
        """Asserts that a system without Watcher gets no Watcher setting from
        the plugin, so the static overrides (600 s polling,
        workload_partitioning discovery) apply unchanged."""
        self._assert_no_watcher_settings(self._get_overrides())

    @mock.patch('k8sapp_openstack.helm.ceilometer.is_watcher_enabled',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_ceilometer_watcher_settings_when_gate_open(
            self, _url, _https, _gate):
        """Asserts the Watcher settings while Watcher is deployed: libvirt
        discovery, no extra metadata fetch, and the compute meters polled at
        the Watcher interval with every other source unchanged.

        The constant is copied before it is changed, so the copy kept in
        constants still holds the static interval afterwards.
        """
        self._assert_watcher_settings(self._get_overrides())
        self.assertEqual(
            600, app_constants.CEILOMETER_POLLING_SOURCES[0]['interval'])
        # The plugin keeps what it already emitted.
        overrides = self._get_overrides()
        self.assertIn('notification', overrides['conf']['ceilometer'])
        self.assertIn('meter', overrides['conf']['ceilometer'])

    @mock.patch('k8sapp_openstack.utils.is_platform_app_available',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_ceilometer_watcher_settings_follow_gate_not_flag(
            self, _url, _https, _prometheus):
        """Asserts that the application-level flag alone does not apply the
        Watcher settings. With the flag ON and Prometheus available but one
        compute-labelled host, the real gate is closed."""
        self._enable_watcher_chart_flag()
        self._add_compute_worker(unit=0)
        self._assert_no_watcher_settings(self._get_overrides())

    @mock.patch('k8sapp_openstack.utils.is_platform_app_available',
                return_value=True)
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_ceilometer_watcher_settings_when_real_gate_opens(
            self, _url, _https, _prometheus):
        """Asserts the Watcher settings once the real gate opens: flag ON,
        two compute-labelled hosts, Prometheus available."""
        self._enable_watcher_chart_flag()
        self._add_compute_worker(unit=0)
        self._add_compute_worker(unit=1)
        self._assert_watcher_settings(self._get_overrides())


class CeilometerPollingSourcesSyncTest(testtools.TestCase):
    """Keeps the constants copy of the polling sources in sync with the
    static overrides."""

    STATIC_OVERRIDES = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        *([os.pardir] * 5),
        'stx-openstack-helm-fluxcd', 'stx-openstack-helm-fluxcd',
        'manifests', 'ceilometer', 'ceilometer-static-overrides.yaml')

    def test_polling_sources_match_static_overrides(self):
        """Asserts CEILOMETER_POLLING_SOURCES equals conf.polling.sources in
        ceilometer-static-overrides.yaml, so an edit of only one of them
        does not get silently replaced by the other."""
        with open(self.STATIC_OVERRIDES) as static_file:
            static = yaml.safe_load(static_file)
        self.assertEqual(static['conf']['polling']['sources'],
                         app_constants.CEILOMETER_POLLING_SOURCES)
