#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm import common
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import watcher
from k8sapp_openstack.tests import test_plugins


class WatcherHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                          base.HelmTestCaseMixin):
    def setUp(self):
        super(WatcherHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class WatcherGetOverrideTest(WatcherHelmTestCase,
                             dbbase.ControllerHostTestCase):
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_watcher_overrides(self, *_):
        """Asserts the default HTTP override surface."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {},
            'conf': {},
            'endpoints': {
                'infra_optim': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                    'port': {},
                    'scheme': {},
                },
            },
        })
        self.assertNotIn('manifests', overrides)

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_watcher_overrides_endpoint_blocks(self, *_):
        """Asserts exactly the five endpoint blocks, no sixth."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertEqual(
            {'identity', 'infra_optim', 'oslo_cache', 'oslo_db',
             'oslo_messaging'},
            set(overrides['endpoints'].keys()))

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_watcher_overrides_invalid_namespace(self, *_):
        """Asserts that an invalid namespace raises InvalidHelmNamespace."""
        self.assertRaises(exception.InvalidHelmNamespace,
                          self.operator.get_helm_chart_overrides,
                          app_constants.HELM_CHART_WATCHER,
                          cnamespace=common.HELM_NS_DEFAULT)

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_watcher_overrides_missing_namespace(self, *_):
        """Asserts the full namespace-keyed mapping is returned with no
        namespace argument."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER)
        self.assertIsInstance(overrides, dict)
        self.assertIn(common.HELM_NS_OPENSTACK, overrides)

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_watcher_overrides_identity_four_users(self, *_):
        """Asserts the four identity users and their key shapes.

        AUTH_USERS has one element but the output carries four users: the
        common-users helper adds admin, test and stx_admin for every service.
        The service user deliberately carries no username key -- that comes
        from the chart's own values.yaml default -- so adding one would be
        wrong.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        auth = overrides['endpoints']['identity']['auth']
        self.assertEqual({'admin', 'test', 'stx_admin', 'watcher'},
                         set(auth.keys()))
        for user in auth.values():
            self.assertIn('region_name', user)
            self.assertIn('password', user)
        for user in ('admin', 'test', 'stx_admin'):
            self.assertIn('username', auth[user])
        self.assertNotIn('username', auth['watcher'])

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    @mock.patch('k8sapp_openstack.helm.watcher.WatcherHelm.'
                '_num_provisioned_controllers', return_value=1)
    def test_watcher_overrides_replicas_one_controller(self, *_):
        """Asserts the three replica keys each equal 1."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        replicas = overrides['pod']['replicas']
        self.assertEqual({'api', 'applier', 'decision_engine'},
                         set(replicas.keys()))
        self.assertEqual(1, replicas['api'])
        self.assertEqual(1, replicas['applier'])
        self.assertEqual(1, replicas['decision_engine'])

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    @mock.patch('k8sapp_openstack.helm.watcher.WatcherHelm.'
                '_num_provisioned_controllers', return_value=2)
    def test_watcher_overrides_replicas_two_controllers(self, *_):
        """Asserts the three replica keys each equal 2."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        replicas = overrides['pod']['replicas']
        self.assertEqual({'api', 'applier', 'decision_engine'},
                         set(replicas.keys()))
        self.assertEqual(2, replicas['api'])
        self.assertEqual(2, replicas['applier'])
        self.assertEqual(2, replicas['decision_engine'])

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    @mock.patch('k8sapp_openstack.helm.watcher.WatcherHelm.'
                '_num_provisioned_controllers', return_value=0)
    def test_watcher_overrides_replicas_zero_controllers(self, *_):
        """Asserts the floor: zero provisioned controllers still yields one
        replica for each of the three Watcher pod types.

        This is the ONLY test that distinguishes the floored
        _num_replicas_for_platform_app() from the unfloored
        _num_provisioned_controllers() -- the one- and two-controller cases
        pass under either helper. It fails if the plugin regresses to the
        unfloored count, which would emit replicas: 0 and scale every Watcher
        workload to zero. Do not drop it as redundant.

        Note the mock target: the raw _num_provisioned_controllers, not the
        floored wrapper the plugin calls. That leaves the real max(1, ...) in
        the path, so this case exercises the floor rather than asserting
        against a stubbed return value.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        replicas = overrides['pod']['replicas']
        self.assertEqual({'api', 'applier', 'decision_engine'},
                         set(replicas.keys()))
        self.assertEqual(1, replicas['api'])
        self.assertEqual(1, replicas['applier'])
        self.assertEqual(1, replicas['decision_engine'])

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_watcher_overrides_clients_auth_keys(self, *_):
        """Asserts all seven watcher_clients_auth keys individually by name."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        clients_auth = overrides['conf']['watcher']['watcher_clients_auth']
        self.assertEqual(
            {'auth_type', 'username', 'password', 'project_name',
             'user_domain_name', 'project_domain_name', 'region_name'},
            set(clients_auth.keys()))
        self.assertEqual(app_constants.WATCHER_CLIENTS_AUTH_TYPE,
                         clients_auth['auth_type'])
        self.assertEqual('watcher', clients_auth['username'])
        self.assertEqual(app_constants.WATCHER_CLIENTS_AUTH_PROJECT_NAME,
                         clients_auth['project_name'])
        self.assertEqual(app_constants.WATCHER_CLIENTS_AUTH_USER_DOMAIN_NAME,
                         clients_auth['user_domain_name'])
        self.assertEqual(
            app_constants.WATCHER_CLIENTS_AUTH_PROJECT_DOMAIN_NAME,
            clients_auth['project_domain_name'])

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_watcher_overrides_clients_auth_password_matches_identity(
            self, *_):
        """Asserts the client-auth password equals the identity service-user
        password (the shared-password invariant).

        If these diverged the service would authenticate with a credential
        Keystone was never given -- a runtime auth failure no structural
        assertion would catch.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        clients_auth = overrides['conf']['watcher']['watcher_clients_auth']
        identity_watcher = overrides['endpoints']['identity']['auth']['watcher']
        self.assertTrue(clients_auth['password'])
        self.assertEqual(identity_watcher['password'],
                         clients_auth['password'])

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_watcher_overrides_clients_auth_omits_static_fields(self, *_):
        """Asserts the constant members of watcher_clients_auth stay out of
        the system overrides.

        cafile, certfile, keyfile and auth_url ship from
        watcher-static-overrides.yaml; emitting them here would duplicate a
        build-time constant into the runtime layer. interface is absent from
        both: the static overrides pin internal endpoints per client instead
        (keystone_client.interface, placement_client.interface,
        cinder/gnocchi/ironic_client.endpoint_type, nova.valid_interfaces).
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        clients_auth = overrides['conf']['watcher']['watcher_clients_auth']
        for key in ('cafile', 'certfile', 'keyfile', 'auth_url', 'insecure'):
            self.assertNotIn(key, clients_auth)

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_watcher_overrides_notification_transport_url(
            self, mock_get_url, *_):
        """Asserts the notification transport_url resolves to the nova vhost
        and the helper was called once with '/nova'."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        transport_url = overrides['conf']['watcher'][
            'oslo_messaging_notifications']['transport_url']
        self.assertEqual('rabbit://fake/nova', transport_url)
        mock_get_url.assert_called_once_with('/nova')

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_watcher_overrides_no_default_section(self, *_):
        """Asserts conf.watcher.DEFAULT is absent, which makes
        conf.watcher.DEFAULT.host unreachable.

        DEFAULT.host must never be set: Watcher's notification queue name is
        the value of CONF.host, which defaults to the pod name. Per-replica
        queue isolation exists only while the option is unset; pinning it to a
        shared value would collapse both Decision Engine replicas onto one
        queue as competing consumers and silently halve each replica's
        model-update rate. Do not "helpfully" add a DEFAULT section back.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertNotIn('DEFAULT', overrides['conf']['watcher'])

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_watcher_overrides_https_disabled(self, *_):
        """Asserts the HTTPS-disabled surface."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        auth = overrides['endpoints']['identity']['auth']
        for user in auth.values():
            self.assertNotIn('cacert', user)
        self.assertNotIn('keystone_authtoken', overrides['conf']['watcher'])
        self.assertNotIn('manifests', overrides)
        self.assertEqual({}, overrides['endpoints']['infra_optim']['port'])
        self.assertEqual({}, overrides['endpoints']['infra_optim']['scheme'])

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
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_watcher_overrides_https_enabled(self, *_):
        """Asserts the HTTPS-enabled surface.

        get_ca_file is mocked to a path that differs from the real return
        value, so these assertions prove the value flowed from the helper
        rather than coincidentally matching a hardcoded literal.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        auth = overrides['endpoints']['identity']['auth']
        self.assertEqual({'admin', 'test', 'stx_admin', 'watcher'},
                         set(auth.keys()))
        for user in auth.values():
            self.assertEqual(watcher.WatcherHelm.get_ca_file(),
                             user['cacert'])
        self.assertEqual(
            watcher.WatcherHelm.get_ca_file(),
            overrides['conf']['watcher']['keystone_authtoken']['cafile'])
        public_tls = overrides['endpoints']['infra_optim'][
            'host_fqdn_override']['public']['tls']
        self.assertIn('crt', public_tls)
        self.assertIn('key', public_tls)
        self.assertIn('ca', public_tls)
        self.assertEqual(
            443, overrides['endpoints']['infra_optim']['port']['api']['public'])
        self.assertEqual(
            'https', overrides['endpoints']['infra_optim']['scheme']['public'])
        self.assertTrue(overrides['manifests']['certificates'])

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
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    def test_watcher_overrides_https_enabled_keeps_transport_url(self, *_):
        """Asserts the notification URL and cafile coexist under HTTPS.

        Guards the _update_overrides deep merge: written as a plain
        assignment, the HTTPS branch would silently drop both
        watcher_clients_auth and oslo_messaging_notifications, and every other
        test would still pass.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        conf_watcher = overrides['conf']['watcher']
        self.assertIn('/nova', conf_watcher[
            'oslo_messaging_notifications']['transport_url'])
        self.assertIn('watcher_clients_auth', conf_watcher)
        self.assertEqual(watcher.WatcherHelm.get_ca_file(),
                         conf_watcher['keystone_authtoken']['cafile'])

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_rabbit_notification_url',
        side_effect=lambda rabbit_path: 'rabbit://fake%s' % rabbit_path)
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_service_region_name')
    def test_watcher_get_region_name(self, mock_get_region, *_):
        """Asserts the region name is resolved with the chart name and lands in
        watcher_clients_auth.region_name."""
        mock_get_region.return_value = 'regionA'
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_WATCHER,
            cnamespace=common.HELM_NS_OPENSTACK)
        mock_get_region.assert_called_with(app_constants.HELM_CHART_WATCHER)
        region_name = overrides['conf']['watcher'][
            'watcher_clients_auth']['region_name']
        self.assertEqual('regionA', region_name)


# Patch targets for the enablement gate tests. The gate is
# k8sapp_openstack.utils.is_watcher_enabled, which WatcherHelm returns.
PROMETHEUS_AVAILABLE = 'k8sapp_openstack.utils.is_platform_app_available'
CENTRAL_CLOUD = 'k8sapp_openstack.utils.is_central_cloud'
APP_FLAG = 'sysinv.common.utils.is_chart_enabled'
NUM_COMPUTES = 'sysinv.db.sqlalchemy.api.Connection.count_hosts_by_label'
GATE_LOG = 'k8sapp_openstack.utils.LOG'


class WatcherGateTestCase(WatcherHelmTestCase):
    """Harness for the enablement gate, copied from test_garbd.py."""

    def setUp(self):
        super(WatcherGateTestCase, self).setUp()
        # The application level check returns False when no helm-overrides
        # record exists for the chart. Seed one with enabled=True so the
        # gate conditions are what the assertions exercise.
        dbutils.create_test_helm_overrides(
            app_id=self.app.id,
            name=app_constants.HELM_CHART_WATCHER,
            namespace=common.HELM_NS_OPENSTACK,
            system_overrides={common.HELM_CHART_ATTR_ENABLED: True})
        self.watcher = watcher.WatcherHelm(self.operator)

    def _gate(self):
        return self.watcher._is_enabled(self.app_name,
                                        app_constants.HELM_CHART_WATCHER,
                                        common.HELM_NS_OPENSTACK)

    def _label_host(self, host, label_key,
                    label_value=common.LABEL_VALUE_ENABLED):
        dbutils.create_test_label(host_id=host.id,
                                  label_key=label_key,
                                  label_value=label_value)

    def _label_aio_controllers(self):
        """Assigns the compute label to every AIO controller.

        AIO controllers carry openstack-compute-node in addition to
        openstack-control-plane, so _num_computes() counts them.
        """
        for host in self.hosts:
            if host.personality == constants.CONTROLLER:
                self._label_host(host, common.LABEL_COMPUTE_LABEL)

    def _add_worker(self, unit=0,
                    administrative=constants.ADMIN_UNLOCKED,
                    invprovision=constants.PROVISIONED,
                    compute_labelled=True):
        """Adds a dedicated worker host to the system.

        :param unit: host unit number, used to build the hostname
        :param administrative: administrative state of the host
        :param invprovision: provisioning state of the host
        :param compute_labelled: whether to assign the
            openstack-compute-node label to the host
        :returns: the created host object
        """
        worker = self._create_test_host(
            constants.WORKER,
            unit=unit,
            administrative=administrative,
            operational=constants.OPERATIONAL_ENABLED,
            availability=constants.AVAILABILITY_AVAILABLE,
            invprovision=invprovision)
        if compute_labelled:
            self._label_host(worker, common.LABEL_COMPUTE_LABEL)
        return worker

    def _mock_manifest_operator(self):
        return mock.Mock(
            APP=self.app_name,
            CHART_GROUPS_LUT={self.watcher.CHART: 'watcher-chart-group'},
            CHARTS_LUT={self.watcher.CHART: 'watcher-chart'})


class WatcherGateAioSimplexTest(WatcherGateTestCase,
                                dbbase.AIOSimplexHostTestCase):
    """Gate decisions on a system with one compute-labelled host."""

    def setUp(self):
        super(WatcherGateAioSimplexTest, self).setUp()
        # The AIO controller is compute labelled on a real system, so the
        # count under test is 1, not 0.
        self._label_aio_controllers()

    @mock.patch(GATE_LOG)
    @mock.patch(PROMETHEUS_AVAILABLE, return_value=True)
    @mock.patch(CENTRAL_CLOUD, return_value=False)
    def test_watcher_disabled_with_one_compute(self, _central, _prom,
                                               mock_log):
        """Asserts that Watcher is disabled with one compute-labelled host.

        A rebalancing Audit live-migrates guests, so a single compute host
        leaves no destination. The closure is logged once at INFO with the
        counted number and the required minimum, so a missing or wrong
        label is visible in sysinv.log.
        """
        self.assertFalse(self._gate())
        mock_log.info.assert_called_once()
        args = mock_log.info.call_args[0]
        self.assertIn(1, args)
        self.assertIn(app_constants.WATCHER_MIN_COMPUTE_HOSTS, args)

    @mock.patch(APP_FLAG, return_value=False)
    @mock.patch(PROMETHEUS_AVAILABLE, return_value=False)
    @mock.patch(CENTRAL_CLOUD, return_value=True)
    def test_watcher_enabled_on_central_cloud(self, _, mock_prometheus,
                                              mock_app_flag):
        """Asserts that Watcher is always enabled on a System Controller.

        The chart must be enabled during "application-upload --images" so
        that the Watcher images are downloaded for the subclouds. The
        carve-out runs first, so the gate opens on a system with one
        compute host, no Prometheus and the application-level flag off,
        and neither the flag nor Prometheus is read.
        """
        self.assertTrue(self._gate())
        mock_app_flag.assert_not_called()
        mock_prometheus.assert_not_called()

    @mock.patch(PROMETHEUS_AVAILABLE, return_value=True)
    def test_watcher_disabled_below_threshold_when_user_enabled(
            self, mock_prometheus):
        """Asserts that an operator ON does not defeat the compute check.

        The application-level flag is one boolean, written from
        disabled_charts at upload and by helm-chart-attribute-modify, so
        the plugin cannot tell an explicit ON from the default. The checks
        after the flag can only close the gate, so with the flag ON and
        one compute host Watcher stays disabled, and the Prometheus check
        is not reached.
        """
        # Precondition: the application-level flag really is ON, so the
        # closed gate below comes from the compute count.
        db_chart = self.dbapi.helm_override_get(
            self.app.id, app_constants.HELM_CHART_WATCHER,
            common.HELM_NS_OPENSTACK)
        self.assertTrue(
            db_chart.system_overrides[common.HELM_CHART_ATTR_ENABLED])
        self.assertFalse(self._gate())
        mock_prometheus.assert_not_called()

    @mock.patch(PROMETHEUS_AVAILABLE, return_value=True)
    def test_watcher_enabled_after_adding_compute_worker(self, _):
        """Asserts that a second compute-labelled host opens the gate.

        Adding a dedicated worker brings the count to exactly
        WATCHER_MIN_COMPUTE_HOSTS. Only one controller exists, so this also fails
        if the controller count is used instead of the compute count.
        """
        self._add_worker()
        self.assertTrue(self._gate())

    @mock.patch(PROMETHEUS_AVAILABLE, return_value=True)
    def test_watcher_disabled_unlabelled_worker_not_counted(self, _):
        """Asserts that a host without the compute label is not counted.

        The count is of openstack-compute-node labels, not of hosts or of
        worker personalities, so a worker that is not an OpenStack compute
        node leaves the count at 1.
        """
        self._add_worker(compute_labelled=False)
        self.assertFalse(self._gate())


class WatcherGateAioDuplexTest(WatcherGateTestCase,
                               dbbase.ProvisionedAIODuplexSystemTestCase):
    """Gate decisions on AIO-DX, where both controllers are compute
    labelled."""

    def setUp(self):
        super(WatcherGateAioDuplexTest, self).setUp()
        self._label_aio_controllers()

    @mock.patch(GATE_LOG)
    @mock.patch(PROMETHEUS_AVAILABLE, return_value=True)
    @mock.patch(CENTRAL_CLOUD, return_value=False)
    def test_watcher_enabled_on_aio_duplex(self, _central, mock_prometheus,
                                           mock_log):
        """Asserts that Watcher is enabled on AIO-DX with Prometheus.

        Both AIO controllers carry the compute label, so the count is 2
        with no dedicated worker. The Prometheus lookup uses the default
        accepted states, and the open path logs nothing.
        """
        self.assertTrue(self._gate())
        mock_prometheus.assert_called_once_with(
            app_constants.PROMETHEUS_PLATFORM_APP_NAME)
        mock_log.info.assert_not_called()
        mock_log.debug.assert_not_called()

    @mock.patch(GATE_LOG)
    @mock.patch(PROMETHEUS_AVAILABLE, return_value=False)
    @mock.patch(CENTRAL_CLOUD, return_value=False)
    def test_watcher_disabled_without_prometheus(self, _central, _prom,
                                                 mock_log):
        """Asserts that Watcher is disabled without platform Prometheus.

        Prometheus is Watcher's only datasource, and an Audit with no data
        still reports SUCCEEDED with an empty Action Plan. The closure is
        logged once at INFO naming the application, because it is only
        re-evaluated when stx-openstack is applied or reapplied.
        """
        self.assertFalse(self._gate())
        mock_log.info.assert_called_once()
        self.assertIn(app_constants.PROMETHEUS_PLATFORM_APP_NAME,
                      mock_log.info.call_args[0])

    @mock.patch(GATE_LOG)
    @mock.patch(PROMETHEUS_AVAILABLE, return_value=True)
    @mock.patch(NUM_COMPUTES, return_value=2)
    @mock.patch(APP_FLAG, return_value=False)
    @mock.patch(CENTRAL_CLOUD, return_value=False)
    def test_watcher_disabled_at_application_level(
            self, _central, _flag, mock_num_computes, mock_prometheus,
            mock_log):
        """Asserts that an operator OFF always wins.

        The flag is read before the compute and Prometheus checks, on a
        system that would otherwise open the gate, and a False value
        returns at once. It logs the reason once at INFO.
        """
        self.assertFalse(self._gate())
        mock_num_computes.assert_not_called()
        mock_prometheus.assert_not_called()
        mock_log.info.assert_called_once_with(
            "Watcher is disabled at the application level")

    @mock.patch(PROMETHEUS_AVAILABLE, return_value=True)
    def test_watcher_enabled_with_locked_controller(self, _):
        """Asserts that locking a compute-labelled host keeps the gate open.

        host-availability-updated is a reapply trigger, so a count that
        filtered on host state would uninstall Watcher during routine
        maintenance on AIO-DX instead of leaving it running on the other
        controller.
        """
        host2 = self.dbapi.ihost_update(
            self.host2.uuid, {'administrative': constants.ADMIN_LOCKED})
        self.assertEqual(constants.ADMIN_LOCKED, host2.administrative)
        self.assertTrue(self._gate())


class WatcherChartUpdatesTest(WatcherGateTestCase,
                              dbbase.ProvisionedAIODuplexSystemTestCase):
    """Chart and resource updates on AIO-DX with Prometheus available."""

    def setUp(self):
        super(WatcherChartUpdatesTest, self).setUp()
        self._label_aio_controllers()

    @mock.patch(PROMETHEUS_AVAILABLE, return_value=True)
    def test_execute_kustomize_updates_keeps_enabled_resource(self, _):
        """Asserts that the HelmRelease resource is retained when the gate
        is open."""
        operator = mock.Mock(APP=self.app_name)
        self.watcher.execute_kustomize_updates(operator)
        operator.helm_release_resource_delete.assert_not_called()

    @mock.patch(PROMETHEUS_AVAILABLE, return_value=True)
    def test_execute_manifest_updates_keeps_enabled_chart(self, _):
        """Asserts that the chart is left in its chart group when the gate
        is open."""
        operator = self._mock_manifest_operator()
        self.watcher.execute_manifest_updates(operator)
        operator.chart_group_chart_delete.assert_not_called()

    @mock.patch(PROMETHEUS_AVAILABLE, return_value=True)
    @mock.patch(APP_FLAG, return_value=False)
    def test_execute_kustomize_updates_removes_user_disabled_resource(
            self, *_):
        """Asserts that the HelmRelease resource is deleted when the
        operator disables Watcher on a system that otherwise opens the
        gate.

        helm_release_resource_delete looks its argument up by HelmRelease
        name, so the HelmRelease name, not the chart name, must be passed.
        """
        operator = mock.Mock(APP=self.app_name)
        self.watcher.execute_kustomize_updates(operator)
        operator.helm_release_resource_delete.assert_called_once_with(
            self.watcher.HELM_RELEASE)


class WatcherChartUpdatesTopologyTest(WatcherGateTestCase,
                                      dbbase.AIOSimplexHostTestCase):
    """Chart and resource removal driven by the compute count alone.

    One compute-labelled host exists and the application-level flag is
    ON, so _is_enabled() returns False on its own and the removal happens
    without the chart being disabled by the user.
    """

    def setUp(self):
        super(WatcherChartUpdatesTopologyTest, self).setUp()
        self._label_aio_controllers()

    @mock.patch(PROMETHEUS_AVAILABLE, return_value=True)
    def test_execute_kustomize_updates_removes_resource_with_one_compute(
            self, _):
        """Asserts that the HelmRelease resource is deleted on a system
        with one compute host, by its HelmRelease name."""
        operator = mock.Mock(APP=self.app_name)
        self.watcher.execute_kustomize_updates(operator)
        operator.helm_release_resource_delete.assert_called_once_with(
            self.watcher.HELM_RELEASE)

    @mock.patch(PROMETHEUS_AVAILABLE, return_value=True)
    def test_execute_manifest_updates_removes_chart_with_one_compute(
            self, _):
        """Asserts that the chart is removed from its chart group on a
        system with one compute host."""
        operator = self._mock_manifest_operator()
        self.watcher.execute_manifest_updates(operator)
        operator.chart_group_chart_delete.assert_called_once_with(
            'watcher-chart-group', 'watcher-chart')


class WatcherGateSystemControllerUpdatesTest(WatcherGateTestCase,
                                             dbbase.AIOSimplexHostTestCase):
    """HelmRelease handling on a System Controller."""

    def setUp(self):
        super(WatcherGateSystemControllerUpdatesTest, self).setUp()
        self._label_aio_controllers()

    @mock.patch(PROMETHEUS_AVAILABLE, return_value=False)
    @mock.patch(CENTRAL_CLOUD, return_value=True)
    def test_execute_kustomize_updates_keeps_resource_on_central_cloud(
            self, *_):
        """Asserts that the HelmRelease resource is retained on a System
        Controller with one compute host and no Prometheus, so that the
        Watcher images are downloaded for the subclouds."""
        operator = mock.Mock(APP=self.app_name)
        self.watcher.execute_kustomize_updates(operator)
        operator.helm_release_resource_delete.assert_not_called()
