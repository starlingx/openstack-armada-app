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
from k8sapp_openstack.helm import keystone
from k8sapp_openstack.tests import test_plugins


class KeystoneHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                           base.HelmTestCaseMixin):
    def setUp(self):
        super(KeystoneHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class KeystoneGetOverrideTest(KeystoneHelmTestCase,
                            dbbase.ControllerHostTestCase):
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_external_federation_urls', return_value={})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_oidc_overrides', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value=False)
    def test_keystone_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_KEYSTONE,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {},
            'endpoints': {
                'identity': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            },
            'conf': {},
            'network': {},
        })

    @mock.patch('os.path.exists', return_value=True)
    @mock.patch('six.moves.builtins.open', mock.mock_open(read_data="fake"))
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_external_federation_urls', return_value={})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_oidc_overrides', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=True)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value=False)
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
    def test_keystone_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_KEYSTONE,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': keystone.KeystoneHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'test': {
                            'cacert': keystone.KeystoneHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'stx_admin': {
                            'cacert': keystone.KeystoneHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                    'host_fqdn_override': {
                        'public': {
                            # 'host': mock.ANY,
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
            'secrets': {
                'tls': {
                    'identity': {
                        'api': {
                            'internal': 'keystone-tls-public',
                        },
                    },
                },
            },
        })

    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_external_federation_urls', return_value={})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_oidc_overrides', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value=False)
    def test_keystone_overrides_invalid_namespace(self, *_):
        """
        Asserts that an exception is raised if an invalid namespace
        is given when retrieving Helm override parameters.
        """
        self.assertRaises(exception.InvalidHelmNamespace,
                          self.operator.get_helm_chart_overrides,
                          app_constants.HELM_CHART_KEYSTONE,
                          cnamespace=common.HELM_NS_DEFAULT)

    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_external_federation_urls', return_value={})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_oidc_overrides', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value=False)
    def test_keystone_overrides_missing_namespace(self, *_):
        """
        Tests that the default Helm override parameters
        are returned when no namespace is passed.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_KEYSTONE)
        self.assertIsInstance(overrides, dict)
        self.assertIn(common.HELM_NS_OPENSTACK, overrides)

    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_external_federation_urls', return_value={})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_oidc_overrides', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value=False)
    def test_delete_project_policy_includes_domain_manager_and_protection(self, *_):
        """Verify delete_project policy has domain manager grant and protection guard."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_KEYSTONE,
            cnamespace=common.HELM_NS_OPENSTACK)
        policy = overrides['conf']['policy']
        rule = policy['identity:delete_project']
        self.assertIn('role:manager', rule)
        self.assertIn('domain_id:%(target.project.domain_id)s', rule)
        self.assertIn('not None:%(target.project.domain_id)s', rule)
        self.assertIn('not rule:protected_projects', rule)

    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_external_federation_urls', return_value={})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_oidc_overrides', return_value={})
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value=False)
    def test_delete_user_policy_includes_domain_manager_and_protection(self, *_):
        """Verify delete_user policy has domain manager grant and protection guard."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_KEYSTONE,
            cnamespace=common.HELM_NS_OPENSTACK)
        policy = overrides['conf']['policy']
        rule = policy['identity:delete_user']
        self.assertIn('role:manager', rule)
        self.assertIn('token.domain.id:%(target.user.domain_id)s', rule)
        self.assertIn('rule:protected_admins', rule)
        self.assertIn('rule:protected_services', rule)


class KeystoneDexFederationTest(KeystoneHelmTestCase,
                                dbbase.ControllerHostTestCase):
    """Tests for the DEX federation override generation.

    Covers the two-gate fix: auth methods and trusted_dashboard must be
    generated whenever DEX is enabled either explicitly (is_dex_enabled)
    or via auto-detection (auto_config_dex_federation), evaluated once and
    threaded down, and the auth methods list must preserve pre-existing
    methods such as application_credential.
    """

    def _keystone(self):
        return keystone.KeystoneHelm(self.operator)

    def _auth_method_list(self):
        result = self._keystone()._get_keystone_auth_methods()
        return result['methods'].split(',')

    # ---- _get_keystone_auth_methods: append to the default set ----

    def test_auth_methods_append_to_keystone_default(self):
        """Append mapped/openid to the Keystone default set without
        dropping any of it (oauth1 and application_credential included)."""
        method_list = self._auth_method_list()

        for base_method in ('external', 'password', 'token', 'oauth1',
                            'application_credential'):
            self.assertIn(base_method, method_list)
        self.assertIn('mapped', method_list)
        self.assertIn('openid', method_list)

    def test_auth_methods_no_duplicates(self):
        """mapped is already in the default set, so it is not duplicated
        when the DEX methods are appended; openid is added once."""
        method_list = self._auth_method_list()

        self.assertEqual(len(method_list), len(set(method_list)))
        self.assertEqual(method_list.count('mapped'), 1)
        self.assertEqual(method_list.count('openid'), 1)
        self.assertEqual(method_list[-1], 'openid')

    # ---- _get_conf_keystone_overrides: gate on the passed-in bool ----

    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_keystone_trusted_dashboard',
                return_value={'trusted_dashboard': 'x'})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_keystone_auth_methods',
                return_value={'methods': ('external,password,token,'
                                          'application_credential,mapped,'
                                          'openid')})
    def test_keystone_overrides_include_dex_sections_when_enabled(self, *_):
        overrides = self._keystone()._get_conf_keystone_overrides(
            dex_enabled=True)

        self.assertIn('auth', overrides)
        self.assertIn('federation', overrides)

    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_keystone_trusted_dashboard',
                return_value={'trusted_dashboard': 'x'})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_keystone_auth_methods',
                return_value={'methods': 'external,password,token'})
    def test_keystone_overrides_exclude_dex_sections_when_disabled(self, *_):
        overrides = self._keystone()._get_conf_keystone_overrides(
            dex_enabled=False)

        self.assertNotIn('auth', overrides)
        self.assertNotIn('federation', overrides)

    # ---- _get_conf_overrides: explicit OR auto, single evaluation ----

    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_external_federation_urls',
                return_value={'external': {}})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_oidc_overrides',
                return_value={})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_conf_keystone_overrides',
                return_value={})
    @mock.patch('k8sapp_openstack.helm.keystone.auto_config_dex_federation')
    @mock.patch('k8sapp_openstack.helm.keystone.is_dex_enabled')
    def test_conf_overrides_explicit_enable_wins(
            self, mock_explicit, mock_auto, *_):
        """Explicit enable renders dex_idp even when auto-detect fails."""
        mock_explicit.return_value = True
        mock_auto.return_value = False

        overrides = self._keystone()._get_conf_overrides()

        self.assertTrue(
            overrides['federation'].get('dex_idp', {}).get('enabled'))

    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_external_federation_urls',
                return_value={'external': {}})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_oidc_overrides',
                return_value={})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_conf_keystone_overrides',
                return_value={})
    @mock.patch('k8sapp_openstack.helm.keystone.auto_config_dex_federation')
    @mock.patch('k8sapp_openstack.helm.keystone.is_dex_enabled')
    def test_conf_overrides_auto_enable_is_fallback(
            self, mock_explicit, mock_auto, *_):
        """Auto-detection enables DEX when no explicit override is set.

        This is the DC subcloud case this change fixes.
        """
        mock_explicit.return_value = False
        mock_auto.return_value = True

        overrides = self._keystone()._get_conf_overrides()

        self.assertTrue(
            overrides['federation'].get('dex_idp', {}).get('enabled'))

    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_external_federation_urls',
                return_value={'external': {}})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_oidc_overrides',
                return_value={})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_conf_keystone_overrides',
                return_value={})
    @mock.patch('k8sapp_openstack.helm.keystone.auto_config_dex_federation')
    @mock.patch('k8sapp_openstack.helm.keystone.is_dex_enabled')
    def test_conf_overrides_disabled_when_neither(
            self, mock_explicit, mock_auto, *_):
        mock_explicit.return_value = False
        mock_auto.return_value = False

        overrides = self._keystone()._get_conf_overrides()

        self.assertNotIn('dex_idp', overrides['federation'])

    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_external_federation_urls',
                return_value={'external': {}})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_oidc_overrides',
                return_value={})
    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm._get_conf_keystone_overrides',
                return_value={})
    @mock.patch('k8sapp_openstack.helm.keystone.auto_config_dex_federation')
    @mock.patch('k8sapp_openstack.helm.keystone.is_dex_enabled')
    def test_conf_overrides_probe_evaluated_once(
            self, mock_explicit, mock_auto, mock_ks_overrides, *_):
        """The enablement decision is made once and threaded down.

        auto_config_dex_federation() runs a live DEX health probe, so it
        must not be called more than once per apply, and the same result
        must be passed to _get_conf_keystone_overrides().
        """
        mock_explicit.return_value = False
        mock_auto.return_value = True

        self._keystone()._get_conf_overrides()

        # is_dex_enabled() False short-circuits to auto; auto probed once.
        self.assertEqual(mock_auto.call_count, 1)
        # The single decision is passed through to the keystone.conf side.
        mock_ks_overrides.assert_called_once_with(True)
