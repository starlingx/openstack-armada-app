#
# Copyright (c) 2026 Wind River Systems, Inc.
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
