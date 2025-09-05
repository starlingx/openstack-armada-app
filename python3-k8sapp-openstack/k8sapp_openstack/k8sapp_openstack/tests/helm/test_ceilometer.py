#
# Copyright (c) 2020-2024 Wind River Systems, Inc.
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
from k8sapp_openstack.helm import ceilometer
from k8sapp_openstack.tests import test_plugins


class CeilometerHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                             base.HelmTestCaseMixin):
    def setUp(self):
        super(CeilometerHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class CeilometerGetOverrideTest(CeilometerHelmTestCase,
                                dbbase.ControllerHostTestCase):
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_ceilometer_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CEILOMETER,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {},
            'conf': {},
            'manifests': {},
            'endpoints': {
                'metering': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            }
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
    def test_ceilometer_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CEILOMETER,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'conf': {
                'ceilometer': {
                    'keystone_authtoken': {
                        'cafile': ceilometer.CeilometerHelm.get_ca_file()
                    },
                    'notification': mock.ANY,
                    'meter': mock.ANY,
                },
            },
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': ceilometer.CeilometerHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'ceilometer': {
                            'cacert': ceilometer.CeilometerHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                },
                'metering': {
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
