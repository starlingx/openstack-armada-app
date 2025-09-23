# Copyright (c) 2020-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import base64

import mock
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
        self.operator = helm.HelmOperator(self.dbapi)
        self.helm = MockOpenstackHelm(self.operator)

    def test_get_namespaces(self):
        """Tests that namespaces match the list of supported namespaces."""
        self.assertEqual(self.helm.get_namespaces(), self.helm.SUPPORTED_NAMESPACES)

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

    def test_get_service_default_dns_name(self):
        """Tests the formatting of services' DNS names."""
        result = self.helm._get_service_default_dns_name(app_constants.HELM_CHART_KEYSTONE)
        self.assertIn(app_constants.HELM_CHART_KEYSTONE, result)

    @mock.patch('sysinv.common.kubernetes.KubeOperator.kube_get_secret',
                return_value=mock.Mock(data={'key': base64.b64encode(b'secret\n')}))
    def test_get_rook_ceph_admin_keyring(self, *_):
        """Matches the retrieval of the Rook Ceph keyring password."""
        result = self.helm._get_rook_ceph_admin_keyring()
        self.assertEqual(result, "secret\n")

    def test_get_ca_file(self):
        """Matches the default certificate authority file path."""
        self.assertEqual(self.helm.get_ca_file(), "/etc/ssl/certs/openstack-helm.crt")
