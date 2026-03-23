# Copyright (c) 2020-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import base64

from eventlet.green import subprocess
import mock
from oslo_serialization import jsonutils
from sqlalchemy.orm.exc import NoResultFound
from sysinv.common import exception
from sysinv.helm import common
from sysinv.helm import helm
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack
from k8sapp_openstack.tests import test_plugins


class MockOpenstackHelm(openstack.OpenstackBaseHelm):
    """
    Proxy object for testing OpenstackBaseHelm class provided methods.
    """
    CHART = "CHART"
    HELM_RELEASE = "HELM_RELEASE"

    def __init__(self, operator):
        super(MockOpenstackHelm, self).__init__(operator)


class OpenstackBaseHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                                base.HelmTestCaseMixin):
    def setUp(self):
        super(OpenstackBaseHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class OpenstackHelmUnitTests(OpenstackBaseHelmTestCase,
                             dbbase.ControllerHostTestCase):
    def setUp(self):
        super(OpenstackHelmUnitTests, self).setUp()
        self.operator = helm.HelmOperator()
        self.helm = MockOpenstackHelm(self.operator)

    def test_get_namespaces(self):
        """Tests that namespaces match the list of supported namespaces."""
        self.assertEqual(self.helm.get_namespaces(), self.helm.SUPPORTED_NAMESPACES)

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_service')
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.context', new={})
    def test_get_service_config_multiple_services(self, mock_get_service, *_):
        """Tests the retrieval of configuration set parameters of services."""
        mock_get_service.side_effect = [
            {"test": "name"},
            {"test2": "name2"}
        ]
        service1 = app_constants.HELM_CHART_KEYSTONE
        service2 = app_constants.HELM_CHART_NOVA

        result1 = self.helm._get_service_config(service1)
        result2 = self.helm._get_service_config(service2)
        self.assertEqual(result1, {"test": "name"})
        self.assertEqual(result2, {"test2": "name2"})
        self.assertEqual(
            set(self.helm.context['_service_configs'].keys()),
            {service1, service2}
        )

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi', new=None)
    def test_get_service_parameters_dbapi_none(self, *_):
        """Asserts on empty service parameters when dbapi is unavailable."""
        result = self.helm._get_service_parameters(app_constants.HELM_CHART_KEYSTONE)
        self.assertEqual(result, [])

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi.service_parameter_get_all',
                return_value=[{'section': "test"}])
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi', new=mock.Mock())
    def test_get_service_parameters_with_result(self, service_parameter_get_all, *_):
        """Tests retrieval of services current configuration parameters."""
        result = self.helm._get_service_parameters(app_constants.HELM_CHART_KEYSTONE)
        self.assertEqual(result, [{'section': "test"}])
        service_parameter_get_all.assert_called_once_with(service=app_constants.HELM_CHART_KEYSTONE)

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi.service_parameter_get_all',
                side_effect=NoResultFound)
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi', new=mock.Mock())
    def test_get_service_parameters_no_result(self, service_parameter_get_all, *_):
        """Tests handling of missing service configuration parameters."""
        result = self.helm._get_service_parameters(app_constants.HELM_CHART_KEYSTONE)
        self.assertEqual(result, [])
        service_parameter_get_all.assert_called_once_with(service=app_constants.HELM_CHART_KEYSTONE)

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.context', new={
                    '_service_params': {
                        app_constants.HELM_CHART_KEYSTONE: [1, 2, 3]
                    }
                })
    def test_get_service_parameter_configs_cache(self, *_):
        """Tests retrieval of cached service configuration values."""
        result = self.helm._get_service_parameter_configs(app_constants.HELM_CHART_KEYSTONE)
        self.assertEqual(result, [1, 2, 3])

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_service_parameters',
            return_value=[{"section": "test"}])
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.context', new={})
    def test_get_service_parameter_configs_miss(self, *_):
        """Tests post retrieval caching of service configuration values."""
        result = self.helm._get_service_parameter_configs(app_constants.HELM_CHART_KEYSTONE)
        self.assertEqual(result, [{"section": "test"}])
        self.assertIn(
            app_constants.HELM_CHART_KEYSTONE,
            self.helm.context['_service_params'])

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_service_parameters',
            return_value=[])
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.context', new={})
    def test_get_service_parameter_configs_unavailable(self, *_):
        """Tests post retrieval caching of service configuration values for empty returned params,
        when api not available or service not found"""
        result = self.helm._get_service_parameter_configs("test_service_name")
        assert result is None

    def test_service_parameter_lookup_one_found(self, *_):
        """Asserts successful lookup of a configuration parameter."""
        params = [
            {"section": "test1", "name": "name1", "value": "value1"},
            {"section": "test2", "name": "name2", "value": "v2"}
        ]
        result = self.helm._service_parameter_lookup_one(params, "test2", "name2", "default")
        self.assertEqual(result, "v2")

    def test_service_parameter_lookup_one_not_found(self, *_):
        """Asserts an unsuccessful lookup of a configuration parameter."""
        params = [
            {"section": "test1", "name": "name1", "value": "value1"}
        ]
        result = self.helm._service_parameter_lookup_one(params, "testX", "nameX", "default")
        self.assertEqual(result, "default")

    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm.get_admin_project_name',
                return_value="admin_project")
    def test_get_admin_project_name(self, *_):
        """Asserts on the default project name."""
        self.assertEqual(self.helm._get_admin_project_name(), "admin_project")

    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm.get_admin_project_domain',
                return_value="admin_domain")
    def test_get_admin_project_domain(self, *_):
        """Asserts on the default project domain."""
        self.assertEqual(self.helm._get_admin_project_domain(), "admin_domain")

    @mock.patch('k8sapp_openstack.helm.keystone.KeystoneHelm.get_admin_user_domain',
                return_value="user_domain")
    def test_get_admin_user_domain(self, *_):
        """Asserts on the default user domain."""
        self.assertEqual(self.helm._get_admin_user_domain(), "user_domain")

    def test_get_database_username(self):
        """Asserts on the default database username."""
        self.assertEqual(
            self.helm._get_database_username(app_constants.HELM_CHART_NOVA),
            "admin-nova")

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._generate_random_password', return_value="pw")
    @mock.patch('k8sapp_openstack.helm.openstack.keyring.get_password', return_value=None)
    @mock.patch('k8sapp_openstack.helm.openstack.keyring.set_password')
    def test_get_keyring_password_generates(self, set_password, *_):
        """Tests keyring password generation associated with a service."""
        pw = self.helm._get_keyring_password(app_constants.HELM_CHART_KEYSTONE, "usr")
        self.assertEqual(pw, b"pw")
        set_password.assert_called_once_with(app_constants.HELM_CHART_KEYSTONE, "usr", "pw")

    @mock.patch('k8sapp_openstack.helm.openstack.keyring.get_password',
                return_value="keyring_password")
    @mock.patch('k8sapp_openstack.helm.openstack.keyring.set_password')
    def test_get_keyring_password_from_keyring_config(self, set_password, *_):
        """Tests password retrieval from keyring config associated with a service."""
        pw = self.helm._get_keyring_password(app_constants.HELM_CHART_KEYSTONE, "usr")
        self.assertEqual(pw, b"keyring_password")
        set_password.assert_not_called()

    @mock.patch('k8sapp_openstack.helm.openstack.keyring.get_password', return_value=None)
    @mock.patch('k8sapp_openstack.helm.openstack.subprocess.check_output',
                return_value='ceph_password'.encode('utf8'))
    @mock.patch('k8sapp_openstack.helm.openstack.keyring.set_password')
    def test_get_keyring_password_generate_ceph_key(self, set_password, *_):
        """Tests keyring password generation associated with a service when ceph password format is
        given as parameter, (pw_format == comom.PASSWORD_FORMAT_CEPH) condition is valid"""
        pw = self.helm._get_keyring_password(
            app_constants.HELM_CHART_KEYSTONE,
            "usr",
            common.PASSWORD_FORMAT_CEPH)

        self.assertEqual(pw, b"ceph_password")
        set_password.assert_called_once_with(
            app_constants.HELM_CHART_KEYSTONE,
            "usr",
            "ceph_password")

    @mock.patch('k8sapp_openstack.helm.openstack.keyring.get_password', return_value=None)
    @mock.patch('k8sapp_openstack.helm.openstack.subprocess.check_output')
    @mock.patch('k8sapp_openstack.helm.openstack.keyring.set_password')
    def test_get_keyring_password_generate_ceph_key_fail(self, set_password, mock_check_output, *_):
        """Tests keyring password generation associated with a service when ceph password format is
        given as parameter, but gets an error when generating key (subprocess.check_output throws
        exception)"""

        mock_check_output.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd="ceph-authtool --gen-print-key",
            output=b"",
            stderr=b"error generating key")

        self.assertRaises(exception.SysinvException,
                          self.helm._get_keyring_password,
                          app_constants.HELM_CHART_KEYSTONE,
                          "usr",
                          common.PASSWORD_FORMAT_CEPH)
        set_password.assert_not_called()

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._region_config',
                return_value=False)
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._region_name',
                return_value="RegionOne")
    def test_get_service_region_name_default(self, *_):
        """Asserts on the default region name of a service."""
        self.assertEqual(
            self.helm._get_service_region_name(app_constants.HELM_CHART_KEYSTONE),
            "RegionOne")

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._region_config',
                return_value=True)
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_service_config',
                return_value=mock.Mock(region_name="RegionTwo"))
    def test_get_service_region_name_with_config(self, *_):
        """Tests the retrieval of region name of a service."""
        self.assertEqual(
            self.helm._get_service_region_name(app_constants.HELM_CHART_KEYSTONE),
            b"RegionTwo")

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._region_config',
                return_value=True)
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_service_config',
                return_value=mock.Mock(capabilities={'service_name': app_constants.HELM_CHART_KEYSTONE}))
    def test_get_configured_service_name_with_region_config(self, *_):
        """Tests the service name retrieval with an associated region."""
        self.assertEqual(self.helm._get_configured_service_name(app_constants.HELM_CHART_KEYSTONE),
                        app_constants.HELM_CHART_KEYSTONE)

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._region_config',
                return_value=True)
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_service_config',
                return_value=mock.Mock(capabilities={'v1_service_name': app_constants.HELM_CHART_KEYSTONE + 'v1'}))
    def test_get_configured_service_name_with_version(self, *_):
        """Tests the retrieval of a service name and version."""
        self.assertEqual(self.helm._get_configured_service_name(
            app_constants.HELM_CHART_KEYSTONE, version='v1'),
            app_constants.HELM_CHART_KEYSTONE + 'v1')

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._region_config',
                return_value=False)
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_service_config',
                return_value=mock.Mock(capabilities={'service_name': app_constants.HELM_CHART_KEYSTONE}))
    def test_get_configured_service_name_no_region_config(self, *_):
        """Tests the retrieval of a service name with missing region cofiguration."""
        self.assertEqual(self.helm._get_configured_service_name(
            app_constants.HELM_CHART_KEYSTONE, version='v2'),
            app_constants.HELM_CHART_KEYSTONE + 'v2')
        self.assertEqual(self.helm._get_configured_service_name(
            app_constants.HELM_CHART_KEYSTONE),
            app_constants.HELM_CHART_KEYSTONE)

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_service_config',
            return_value=mock.Mock(capabilities={'service_type': "stype"}))
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._region_config',
            return_value=True)
    def test_get_configured_service_type_with_region_config(self, *_):
        """Asserts on configured service type in a region."""
        self.assertEqual(self.helm._get_configured_service_type(app_constants.HELM_CHART_KEYSTONE), 'stype')

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_service_config',
            return_value=mock.Mock(capabilities={'v1_service_type': "stypev1"}))
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._region_config', return_value=True)
    def test_get_configured_service_type_with_version(self, *_):
        """Asserts on specific version of a service type."""
        service_type = self.helm._get_configured_service_type(
            app_constants.HELM_CHART_KEYSTONE,
            version='v1')
        self.assertEqual(service_type, "stypev1")

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._region_config', return_value=False)
    def test_get_configured_service_type_no_region_config(self, *_):
        """Asserts on default service type configuration."""
        self.helm._region_config = mock.Mock(return_value=False)
        self.assertIsNone(self.helm._get_configured_service_type(app_constants.HELM_CHART_KEYSTONE))

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi.helm_override_get',
                return_value=mock.Mock(system_overrides={'test': "name"}))
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi', new=mock.Mock())
    @mock.patch('sysinv.common.utils.find_openstack_app', return_value=mock.Mock(id=1))
    def test_get_or_generate_password(self, *_):
        """Tests on general purpose password retrieval or generation."""
        pw = self.helm._get_or_generate_password('chart', 'ns', 'test')
        self.assertEqual(pw, b'name')

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi', new=mock.Mock())
    @mock.patch('sysinv.common.utils.find_openstack_app', return_value=mock.Mock(id=1,))
    def test_get_or_generate_password_fails_to_retrieve_and_create_overrides(self, *_):
        """Tests on general purpose password retrieval or generation. When it fails to get chart
        overrides and its password and also fails to create them, this method should return None"""
        with mock.patch.object(
                self.helm.dbapi,
                'helm_override_get') as mock_helm_override_get, \
            mock.patch.object(
                self.helm.dbapi,
                'helm_override_create') as mock_helm_override_create:
            mock_helm_override_get.side_effect = exception.HelmOverrideNotFound("test")
            mock_helm_override_create.side_effect = Exception("test_case: error creating overrides")
            result = self.helm._get_or_generate_password('chart', 'ns', 'test')
            assert result is None

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi', new=mock.Mock())
    @mock.patch('sysinv.common.utils.find_openstack_app', return_value=mock.Mock(id=1))
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._generate_random_password',
                return_value="generated_password")
    def test_get_or_generate_password_fails_to_store_generated_passsword(self, *_):
        """Tests on general purpose password retrieval or generation. In this case it fails to get
        override values and password from them, instead it generates one but fails to store it."""
        with mock.patch.object(self.helm.dbapi, 'helm_override_update', side_effect=Exception(
                "test case: failed to store override")) as mock_helm_override_update, \
            mock.patch.object(self.helm.dbapi, 'kube_app_get_inactive', return_value=[]), \
            mock.patch.object(self.helm.dbapi, 'helm_override_get', return_value=mock.Mock(
                system_overrides={'key_dummy': 'value_dummy'})):
            pw = self.helm._get_or_generate_password('chart', 'ns', 'test_password_field')
            mock_helm_override_update.assert_called_once_with(
                app_id=1,
                name='chart',
                namespace='ns',
                values={
                    'system_overrides': {
                        'key_dummy': 'value_dummy',
                        'test_password_field': 'generated_password'
                    }
                }
            )
            self.assertEqual(pw, b'generated_password')

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi', new=mock.Mock())
    @mock.patch('sysinv.common.utils.find_openstack_app', return_value=mock.Mock(id=1))
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._generate_random_password',
                return_value="generated_password")
    def test_get_or_generate_password_gets_from_inactive_app(self, *_):
        """Tests on general purpose password retrieval or generation. In this case it retrieves the
        override values from inactive app."""
        with mock.patch.object(self.helm.dbapi,
                               'helm_override_update'
                               ) as mock_helm_override_update, \
            mock.patch.object(self.helm.dbapi,
                              'kube_app_get_inactive',
                              return_value=[mock.Mock(id=1)]
                              ), \
            mock.patch.object(self.helm.dbapi,
                              'helm_override_get',
                              side_effect=[
                                  mock.Mock(system_overrides={'key_dummy': 'value_dummy'}),
                                  mock.Mock(system_overrides={'pw_field': 'pw_from_inactive_app'})]
                              ):
            pw = self.helm._get_or_generate_password('chart', 'ns', 'pw_field')
            mock_helm_override_update.assert_called_once_with(
                app_id=1,
                name='chart',
                namespace='ns',
                values={
                    'system_overrides': {
                        'key_dummy': 'value_dummy',
                        'pw_field': 'pw_from_inactive_app'
                    }
                }
            )
            self.assertEqual(pw, b'pw_from_inactive_app')

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi', new=None)
    def test_get_or_generate_password_dbapi_unavailable(self, *_):
        """Tests on general purpose password retrieval or generation. When dbapi not available this
        method should return None"""
        result = self.helm._get_or_generate_password('chart', 'ns', 'test')
        assert result is None

    @mock.patch('k8sapp_openstack.utils.get_services_fqdn_pattern',
                return_value="{service_name}.{endpoint_domain}")
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_service_parameter',
                return_value=mock.Mock(value="domain.com"))
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._is_openstack_https_ready',
                return_value=False)
    def test_get_endpoints_host_fqdn_overrides(self, *_):
        """Tests the retrieval of service hostnames."""
        result = self.helm._get_endpoints_host_fqdn_overrides(app_constants.HELM_CHART_KEYSTONE)
        self.assertIn("public", result)
        self.assertIn("host", result["public"])

    @mock.patch('k8sapp_openstack.utils.get_services_fqdn_pattern',
                return_value="{service_name}.{endpoint_domain}")
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_endpoint_public_tls',
                return_value={'crt': "fake", 'key': "fake", 'ca': "fake"})
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_service_parameter',
                return_value=mock.Mock(value="domain.com"))
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._is_openstack_https_ready',
                return_value=True)
    def test_get_endpoints_host_fqdn_https_overrides(self, *_):
        """Tests the retrieval of service hostnames when HTTPS is enabled."""
        result = self.helm._get_endpoints_host_fqdn_overrides(app_constants.HELM_CHART_KEYSTONE)
        self.assertIn("public", result)
        self.assertIn("host", result["public"])
        self.assertIn("tls", result["public"])

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_keyring_password',
                return_value=b"pw")
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.context', new={})
    def test_get_ceph_password(self, *_):
        """Tests the retrieval of Ceph password associated with a service."""
        pw = self.helm._get_ceph_password(app_constants.HELM_CHART_KEYSTONE, "user")
        self.assertEqual(pw, b"pw")
        self.assertEqual(self.helm.context['_ceph_passwords'][app_constants.HELM_CHART_KEYSTONE]["user"], b"pw")

    @mock.patch('sysinv.common.kubernetes.KubeOperator.kube_get_secret')
    def test_get_or_generate_ssh_keys_from_secret(self, mock_get_secret, *_):
        """Asserts keys are retrieved from an existing K8s secret."""
        mock_get_secret.return_value = mock.Mock(
            data={
                'private-key': base64.b64encode(b'priv_from_secret'),
                'public-key': base64.b64encode(b'pub_from_secret'),
            }
        )
        priv, pub = self.helm._get_or_generate_ssh_keys(
            "openstack", secret_name="nova-ssh")
        self.assertEqual(priv, "priv_from_secret")
        self.assertEqual(pub, "pub_from_secret")
        mock_get_secret.assert_called_once_with(
            name="nova-ssh", namespace="openstack")

    @mock.patch('sysinv.common.kubernetes.KubeOperator.kube_get_secret',
                return_value=None)
    def test_get_or_generate_ssh_keys_secret_not_found(self, mock_get_secret, *_):
        """Asserts new keys are generated when the K8s secret does not exist."""
        priv, pub = self.helm._get_or_generate_ssh_keys(
            "openstack", secret_name="nova-ssh")
        self.assertIn("BEGIN", priv)
        self.assertTrue(pub.startswith("ssh-rsa"))

    def test_get_or_generate_ssh_keys_no_secret_name(self, *_):
        """Asserts new keys are generated when no secret_name is provided."""
        priv, pub = self.helm._get_or_generate_ssh_keys("openstack")
        self.assertIn("BEGIN", priv)
        self.assertTrue(pub.startswith("ssh-rsa"))

    @mock.patch('sysinv.common.kubernetes.KubeOperator.kube_get_secret',
                side_effect=Exception("k8s unavailable"))
    def test_get_or_generate_ssh_keys_secret_exception(self, *_):
        """Asserts new keys are generated when the K8s API raises an exception."""
        priv, pub = self.helm._get_or_generate_ssh_keys(
            "openstack", secret_name="nova-ssh")
        self.assertIn("BEGIN", priv)
        self.assertTrue(pub.startswith("ssh-rsa"))

    def test_get_service_default_dns_name(self):
        """Tests the formatting of services' DNS names."""
        result = self.helm._get_service_default_dns_name(app_constants.HELM_CHART_KEYSTONE)
        self.assertIn(app_constants.HELM_CHART_KEYSTONE, result)

    @mock.patch("k8sapp_openstack.helm.openstack.app_utils.is_ceph_backend_available", return_value=(True, ""))
    def test_get_ceph_client_overrides_rook(self, *_):
        """Matches the default backend user secret name."""
        result = self.helm._get_ceph_client_overrides()
        self.assertIn("user_secret_name", result)

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi.interface_network_get_all',
                return_value=[mock.Mock(interface_id=1), mock.Mock(interface_id=2)])
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi', new=mock.Mock())
    def test_get_interface_networks(self, *_):
        """Tests the handling of interfaces network information."""
        result = self.helm._get_interface_networks()
        self.assertIn(1, result)
        self.assertIn(2, result)

    @mock.patch("k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_interface_networks",
                return_value={
                    1: [mock.Mock(interface_id=1, network_id=2)]
                })
    def test_get_interface_network_query_found(self, *_):
        """Tests querying of available network interfaces."""
        result = self.helm._get_interface_network_query(1, 2)
        self.assertEqual(result.interface_id, 1)
        self.assertEqual(result.network_id, 2)

    @mock.patch("k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_interface_networks", return_value={})
    def test_get_interface_network_query_not_found(self, *_):
        """Asserts on exception when no matching network interfaces are found."""
        self.assertRaises(openstack.exception.InterfaceNetworkNotFoundByHostInterfaceNetwork,
                          self.helm._get_interface_network_query, 1, 3)

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_host_interfaces',
                return_value={1: [mock.Mock(id=2)]})
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_interface_network_query')
    def test_get_cluster_host_iface(self, get_interface_network_query, *_):
        """Tests querying of cluster host network interfaces."""
        fake_host = mock.Mock(id=1)
        result = self.helm._get_cluster_host_iface(fake_host, 3)
        self.assertEqual(result.id, 2)
        get_interface_network_query.assert_called_once_with(2, 3)

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_host_interfaces',
                return_value={1: [mock.Mock(id=2)]})
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_interface_network_query',
                side_effect=exception.InterfaceNetworkNotFoundByHostInterfaceNetwork("test_error"))
    def test_get_cluster_host_iface_fails(self, get_interface_network_query, *_):
        """Tests querying of cluster host network interfaces."""
        fake_host = mock.Mock(id=1)
        result = self.helm._get_cluster_host_iface(fake_host, 3)
        assert result is None
        get_interface_network_query.assert_called_once_with(2, 3)

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_cluster_host_iface',
                return_value=mock.Mock(id=3))
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi.network_get_by_type',
                return_value=mock.Mock(id=2))
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi', new=mock.Mock())
    def test_get_cluster_host_ip(self, *_):
        """Tests the querying the network address of cluster hosts."""
        fake_host = mock.Mock(id=1)
        fake_addr = mock.Mock(interface_id=3, address="10.0.0.1")
        addresses_by_hostid = {1: [fake_addr]}
        result = self.helm._get_cluster_host_ip(fake_host, addresses_by_hostid)
        self.assertEqual(result, "10.0.0.1")

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_cluster_host_iface',
                return_value=None)
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi.network_get_by_type',
                return_value=mock.Mock(id=2))
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi', new=mock.Mock())
    def test_get_cluster_host_ip_none_iface_found(self, *_):
        """Tests the querying the network address of cluster hosts, for none cluster-host interface
        found"""
        fake_host = mock.Mock(id=1)
        fake_addr = mock.Mock(interface_id=3, address="10.0.0.1")
        addresses_by_hostid = {1: [fake_addr]}
        result = self.helm._get_cluster_host_ip(fake_host, addresses_by_hostid)
        assert result is None

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._is_enabled', return_value=False)
    def test_execute_kustomize_updates(self, *_):
        """Asserts on the deletion of disabled cluster resources."""
        operator = mock.Mock(APP="app")
        self.helm.execute_kustomize_updates(operator)
        operator.helm_release_resource_delete.assert_called_once_with(self.helm.HELM_RELEASE)

    @mock.patch('sysinv.common.kubernetes.KubeOperator.kube_get_secret',
                return_value=mock.Mock(data={'key': base64.b64encode(b'secret\n')}))
    def test_get_rook_ceph_admin_keyring(self, *_):
        """Matches the retrieval of the Rook Ceph keyring password."""
        result = self.helm._get_rook_ceph_admin_keyring()
        self.assertEqual(result, "secret\n")

    @mock.patch('sysinv.common.kubernetes.KubeOperator.kube_get_secret',
                side_effect=Exception("test case: error"))
    def test_get_rook_ceph_admin_keyring_fails(self, *_):
        """Matches an error on retrieval of the Rook Ceph keyring password, Catching an Exception
        should make this method returns 'null'."""
        result = self.helm._get_rook_ceph_admin_keyring()
        self.assertEqual(result, 'null')

    def test_get_ca_file(self):
        """Matches the default certificate authority file path."""
        self.assertEqual(self.helm.get_ca_file(), "/etc/ssl/certs/openstack-helm.crt")

    def test_get_chart_operator_with_plugin_manager_class(self, *_):
        """Tests the retrieval of an operator for a given chart name
        using Plugin Manager _get_chart_operator method"""
        with mock.patch.object(
                self.operator,
                'get_chart_operator',
                return_value="operator_from_plugin_manager") as mock_get_chart_operator:
            chart_operator = self.helm._get_chart_operator("valid_chart_name")
            self.assertEqual(chart_operator, "operator_from_plugin_manager")
            mock_get_chart_operator.assert_called_once_with("valid_chart_name")

    def test_get_chart_operator_without_plugin_manager_class(self, *_):
        """Tests the retrieval of an operator for a given chart name using _operator.chart_operators
        attribute, asserts that, for this test environment, trying to recover chart name using
        _operator attribute "chart_operator[]" is not supported, and should raise an exception"""
        with mock.patch.object(
                self.operator,
                'get_chart_operator',
                side_effect=AttributeError(
                    "Old versions of starlingx does not include Plugin Manager class")):
            self.operator.chart_operators = {}
            self.assertRaises(KeyError,
                              self.helm._get_chart_operator,
                              "valid_chart_name")

    def test__update_image_tag_overrides_for_empty_overrides(self):
        """Tests the flow of execution for image tag overrides config, in this case it receives
        empty overrides as parameter and should create and return expected dictionary"""
        overrides = {}
        images = ['image1', 'image2', 'image3']
        tag = 'test.io/tag:v2.3.4'

        result = self.helm._update_image_tag_overrides(overrides, images, tag)

        self.assertOverridesParameters(result, {
            'images': {
                'tags': {
                    'image1': 'test.io/tag:v2.3.4',
                    'image2': 'test.io/tag:v2.3.4',
                    'image3': 'test.io/tag:v2.3.4'
                }
            }
        })

    def test__update_image_tag_overrides_for_existing_overrides(self):
        """Tests the flow of execution for image tag overrides config, in this case it receives
        existing overrides as parameter and should merge and return expected dictionary"""
        overrides = {
            'key1': 'value1',
            'key2': {
                'key3': 'value2',
                'key4': 'value3'
            },
            'images': {
                'tags': {
                    'test_image': 'test.io/tag:v1.2.3'
                }
            }
        }

        images = ['image1']
        tag = 'test.io/tag:v2.3.4'

        result = self.helm._update_image_tag_overrides(overrides, images, tag)

        self.assertOverridesParameters(result, {
            'key1': 'value1',
            'key2': {
                'key3': 'value2',
                'key4': 'value3'
            },
            'images': {
                'tags': {
                    'test_image': 'test.io/tag:v1.2.3',
                    'image1': 'test.io/tag:v2.3.4'
                }
            }
        })

    def test__update_image_tag_overrides_for_existing_image(self):
        """Tests the flow of execution for image tag overrides config, in this case it receives
        existing overrides with the image that is also passed as parameter and should replace
        its tag and return the expected dictionary"""
        overrides = {
            'images': {
                'tags': {
                    'test_image': 'test.io/tag:deprecated_version'
                }
            }
        }

        images = ['test_image']
        tag = 'test.io/tag:latest_version'

        result = self.helm._update_image_tag_overrides(overrides, images, tag)

        self.assertOverridesParameters(result, {
            'images': {
                'tags': {
                    'test_image': 'test.io/tag:latest_version'
                }
            }
        })

    def test__update_image_tag_overrides_for_empty_image_list(self):
        """Tests the flow of execution for image tag overrides config, in this case it receives
        as parameter a empty list o images, and should return the same unaltered overrides  """
        overrides = {
            'images': {
                'tags': {
                    'test_image': 'test.io/tag:deprecated_version'
                }
            }
        }

        images = []
        tag = 'test.io/tag:latest_version'

        result = self.helm._update_image_tag_overrides(overrides, images, tag)

        self.assertOverridesParameters(result, overrides)

    @mock.patch('k8sapp_openstack.helm.openstack.app_utils.is_ceph_backend_available',
                return_value=(True, ""))
    def test_is_rook_ceph_is_available(self, *_):
        """Tests method that checks rook_ceph availability"""
        is_rook_ceph = self.helm._is_rook_ceph()
        assert is_rook_ceph is True

    @mock.patch('k8sapp_openstack.helm.openstack.app_utils.is_ceph_backend_available',
                return_value=(False, "test: rook ceph not available"))
    def test_is_rook_ceph_is_unavailable(self, *_):
        """Tests method that checks rook_ceph availability"""
        is_rook_ceph = self.helm._is_rook_ceph()
        assert is_rook_ceph is False

    @mock.patch(
            'k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi.interface_datanetwork_get_all',
            return_value=[])
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi', new=mock.Mock())
    def test_get_interface_datanets_empty(self, *_):
        """Tests interface datanets with no datanets returned from database."""
        result = self.helm._get_interface_datanets()
        self.assertEqual(result, {})

    @mock.patch(
            'k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi.interface_datanetwork_get_all',
            return_value=[
                mock.Mock(interface_id=1),
                mock.Mock(interface_id=2),
                mock.Mock(interface_id=3),
                mock.Mock(interface_id=1),
                mock.Mock(interface_id=3)
            ])
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi', new=mock.Mock())
    def test_get_interface_datanets_grouped(self, *_):
        """Tests interface datanets grouping by interface id."""
        result = self.helm._get_interface_datanets()
        self.assertIn(1, result)
        self.assertIn(2, result)
        self.assertIn(3, result)
        self.assertEqual(len(result[1]), 2)
        self.assertEqual(len(result[2]), 1)
        self.assertEqual(len(result[3]), 2)

    def test_oslo_multistring_override_empty_values_or_name(self, *_):
        """Tests oslo multistring override with empty values or name."""
        result = self.helm._oslo_multistring_override(None, ["test"])
        assert result is None

        result = self.helm._oslo_multistring_override("test", [])
        assert result is None

        result = self.helm._oslo_multistring_override(None, [])
        assert result is None

    def test_oslo_multistring_override_strings(self, *_):
        """Tests oslo multistring override configuration for simple type, like strings"""
        result = self.helm._oslo_multistring_override('test', ['value1', 'value2'])
        self.assertOverridesParameters(result, {
            'test': {
                'type': 'multistring',
                'values': ['value1', 'value2']
            }
        })

    def test_oslo_multistring_override_complex_types(self, *_):
        """Tests oslo multistring override configurationfor simple and for complex types,
        like dict and set for example"""
        values = [['set_value1', 'set_value2'], {'dict_key1': 'dict_value1'}, 'value1', 'value2']
        result = self.helm._oslo_multistring_override('test', values)
        self.assertOverridesParameters(result, {
            'test': {
                'type': 'multistring',
                'values': [jsonutils.dumps(values[0]), jsonutils.dumps(values[1]), 'value1', 'value2']
            }})

    @mock.patch('k8sapp_openstack.helm.openstack.app_utils.get_available_volume_backends')
    @mock.patch('k8sapp_openstack.helm.openstack.app_utils.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.helm.openstack.app_utils.get_enabled_storage_backends_from_override')
    def test_resolve_nova_pvc_overrides_skips_when_effective_backend_is_not_pvc(
        self,
        mock_get_enabled_storage_backends,
        mock_get_storage_backends_priority_list,
        mock_get_available_volume_backends
    ):
        mock_get_enabled_storage_backends.return_value = [
            app_constants.HOST_PATH_BACKEND_NAME,
            app_constants.PVC_BACKEND_NAME,
        ]
        mock_get_storage_backends_priority_list.return_value = [
            app_constants.HOST_PATH_BACKEND_NAME,
            app_constants.PVC_BACKEND_NAME,
        ]

        result = self.helm._resolve_nova_pvc_overrides()

        self.assertEqual(result, {})
        mock_get_available_volume_backends.assert_not_called()

    @mock.patch('k8sapp_openstack.helm.openstack.app_utils.get_nova_pvc_instances_path',
                return_value='/var/lib/nova/instances')
    @mock.patch('k8sapp_openstack.helm.openstack.app_utils.get_nova_pvc_name',
                return_value='nova-instances')
    @mock.patch('k8sapp_openstack.helm.openstack.app_utils.get_available_volume_backends',
                return_value={app_constants.NETAPP_NFS_BACKEND_NAME: 'netapp-nas-backend'})
    @mock.patch('k8sapp_openstack.helm.openstack.app_utils.get_storage_backends_priority_list')
    @mock.patch('k8sapp_openstack.helm.openstack.app_utils.get_enabled_storage_backends_from_override',
                return_value=[app_constants.PVC_BACKEND_NAME])
    def test_resolve_nova_pvc_overrides_resolves_values(
        self,
        _mock_get_enabled_storage_backends,
        mock_get_storage_backends_priority_list,
        _mock_get_available_volume_backends,
        _mock_get_nova_pvc_name,
        _mock_get_nova_pvc_instances_path
    ):
        mock_get_storage_backends_priority_list.side_effect = [
            [app_constants.HOST_PATH_BACKEND_NAME, app_constants.PVC_BACKEND_NAME],
            [app_constants.NETAPP_NFS_BACKEND_NAME],
        ]

        result = self.helm._resolve_nova_pvc_overrides()

        self.assertEqual(result, {
            'enabled': True,
            'name': 'nova-instances',
            'instances_path': '/var/lib/nova/instances',
            'storage_class': 'netapp-nas-backend',
        })
