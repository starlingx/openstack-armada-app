#
# Copyright (c) 2020-2024 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.helm import common
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import keystone_api_proxy
from k8sapp_openstack.tests import test_plugins


class KeystoneApiProxyHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                                   base.HelmTestCaseMixin):
    def setUp(self):
        super(KeystoneApiProxyHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class KeystoneApiProxyGetOverrideTest(KeystoneApiProxyHelmTestCase,
                                      dbbase.ControllerHostTestCase):
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_keystone_api_proxy_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_KEYSTONE_API_PROXY,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {},
            'conf': {},
            'endpoints': {
                'keystone_api_proxy': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            },
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
    def test_keystone_api_proxy_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_KEYSTONE_API_PROXY,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'conf': {
                'keystone_api_proxy': {
                    'DEFAULT': {
                        'transport_url': mock.ANY,
                    },
                    'database': {
                        'connection': mock.ANY,
                    },
                    'identity': {
                        'remote_host': mock.ANY,
                    },
                }
            },
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': keystone_api_proxy.KeystoneApiProxyHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'test': {
                            'cacert': keystone_api_proxy.KeystoneApiProxyHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                },
                'keystone_api_proxy': {
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
        })
