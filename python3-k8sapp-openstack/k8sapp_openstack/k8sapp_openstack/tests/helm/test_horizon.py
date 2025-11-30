#
# Copyright (c) 2020-2025 Wind River Systems, Inc.
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
from k8sapp_openstack.helm import horizon
from k8sapp_openstack.tests import test_plugins


class HorizonHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                          base.HelmTestCaseMixin):
    def setUp(self):
        super(HorizonHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class HorizonWebSSOTestCase(HorizonHelmTestCase,
                            dbbase.ControllerHostTestCase):
    """Tests for Horizon WebSSO configuration with DEX integration."""

    def _get_local_settings_config(self, overrides):
        """Extract local_settings config from Horizon overrides."""
        return overrides.get('conf', {}).get(
            'horizon', {}).get('local_settings', {}).get('config', {})

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.helm.horizon.is_dex_enabled', return_value=False)
    def test_websso_disabled_when_dex_disabled(self, *_):
        """Test WebSSO config is absent when DEX is disabled."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_HORIZON,
            cnamespace=common.HELM_NS_OPENSTACK)
        config = self._get_local_settings_config(overrides)
        self.assertNotIn('auth', config)

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.helm.horizon.is_dex_enabled', return_value=True)
    @mock.patch(
        'k8sapp_openstack.helm.horizon.HorizonHelm._get_websso_auth_config_overrides',
        return_value={
            'auth': {
                'sso': {'enabled': True, 'initial_choice': 'credentials'},
                'idp_mapping': [{'name': 'dex_oidc', 'label': 'Login with DEX SSO',
                                 'idp': 'dex', 'protocol': 'openid'}]
            },
            'raw': {'OPENSTACK_KEYSTONE_URL': 'http://keystone.example.com/v3'}
        })
    def test_websso_enabled_with_dex(self, *_):
        """Test WebSSO config is present when DEX is enabled."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_HORIZON,
            cnamespace=common.HELM_NS_OPENSTACK)
        config = self._get_local_settings_config(overrides)

        self.assertTrue(config['auth']['sso']['enabled'])
        self.assertEqual(config['auth']['idp_mapping'][0]['idp'], 'dex')
        self.assertEqual(config['raw']['OPENSTACK_KEYSTONE_URL'],
                         'http://keystone.example.com/v3')


class HorizonGetOverrideTest(HorizonHelmTestCase,
                            dbbase.ControllerHostTestCase):
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value=False)
    def test_horizon_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_HORIZON,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'conf': {},
            'endpoints': {
                'dashboard': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            },
            'network': {},
        })

    @mock.patch('os.path.exists', return_value=True)
    @mock.patch('six.moves.builtins.open', mock.mock_open(read_data="fake"))
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
    def test_horizon_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_HORIZON,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': horizon.HorizonHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        }
                    },
                },
                'dashboard': {
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
        })

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value=False)
    def test_horizon_overrides_invalid_namespace(self, *_):
        """
        Asserts that an exception is raised if an invalid namespace
        is given when retrieving Helm override parameters.
        """
        self.assertRaises(exception.InvalidHelmNamespace,
                          self.operator.get_helm_chart_overrides,
                          app_constants.HELM_CHART_HORIZON,
                          cnamespace=common.HELM_NS_DEFAULT)

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.utils._get_value_from_application', return_value=False)
    def test_horizon_overrides_missing_namespace(self, *_):
        """
        Tests that the default Helm override parameters
        are returned when no namespace is passed.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_HORIZON)
        self.assertIsInstance(overrides, dict)
        self.assertIn(common.HELM_NS_OPENSTACK, overrides)
