# Copyright (c) 2020-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import base64

import mock
from sqlalchemy.orm.exc import NoResultFound
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

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_keyring_password',
                return_value=b"pw")
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.context', new={})
    def test_get_ceph_password(self, *_):
        """Tests the retrieval of Ceph password associated with a service."""
        pw = self.helm._get_ceph_password(app_constants.HELM_CHART_KEYSTONE, "user")
        self.assertEqual(pw, b"pw")
        self.assertEqual(self.helm.context['_ceph_passwords'][app_constants.HELM_CHART_KEYSTONE]["user"], b"pw")

    @mock.patch("sysinv.common.utils.find_openstack_app", return_value=mock.Mock(id=1))
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi.helm_override_get',
                return_value=mock.Mock(system_overrides={"privatekey": "priv", "publickey": "pub"}))
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.dbapi', new=mock.Mock())
    def test_get_or_generate_ssh_keys(self, *_):
        """Asserts on the contents of generated SSH keys."""
        priv, pub = self.helm._get_or_generate_ssh_keys("chart", "ns")
        self.assertEqual(priv, "priv")
        self.assertEqual(pub, "pub")

    def test_get_service_default_dns_name(self):
        """Tests the formatting of services' DNS names."""
        result = self.helm._get_service_default_dns_name(app_constants.HELM_CHART_KEYSTONE)
        self.assertIn(app_constants.HELM_CHART_KEYSTONE, result)

    @mock.patch("k8sapp_openstack.helm.openstack.app_utils.is_ceph_backend_available", return_value=True)
    def test_get_ceph_client_overrides_rook(self, *_):
        """Matches the default backend user secret name."""
        result = self.helm._get_ceph_client_overrides()
        self.assertIn("user_secret_name", result)

    @mock.patch("k8sapp_openstack.helm.openstack.app_utils.is_ceph_backend_available", return_value=False)
    @mock.patch("sysinv.common.storage_backend_conf.K8RbdProvisioner.get_user_secret_name", return_value="secret")
    def test_get_ceph_client_overrides_rbd(self, *_):
        """Matches the stored backend user secret name."""
        result = self.helm._get_ceph_client_overrides()
        self.assertEqual(result["user_secret_name"], "secret")

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

    def test_get_ca_file(self):
        """Matches the default certificate authority file path."""
        self.assertEqual(self.helm.get_ca_file(), "/etc/ssl/certs/openstack-helm.crt")
