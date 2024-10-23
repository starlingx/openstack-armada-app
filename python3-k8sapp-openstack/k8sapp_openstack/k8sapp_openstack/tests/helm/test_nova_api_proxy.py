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
from k8sapp_openstack.helm import nova_api_proxy
from k8sapp_openstack.tests import test_plugins


class NovaApiProxyHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                               base.HelmTestCaseMixin):
    def setUp(self):
        super(NovaApiProxyHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class NovaApiProxyGetOverrideTest(NovaApiProxyHelmTestCase,
                                  dbbase.ControllerHostTestCase):
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_nova_api_proxy_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA_API_PROXY,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {},
            'conf': {},
            'endpoints': {
                'compute': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            },
        })

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_nova_api_proxy_overrides_reuses_neutron_placement_users(self, *_):
        overrides_neutron = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NEUTRON,
            cnamespace=common.HELM_NS_OPENSTACK)
        overrides_placement = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_PLACEMENT,
            cnamespace=common.HELM_NS_OPENSTACK)
        overrides_n_api_prx = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA_API_PROXY,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertEqual(
            overrides_n_api_prx["endpoints"]["identity"]["auth"]["neutron"],
            overrides_neutron["endpoints"]["identity"]["auth"]["neutron"],
        )
        self.assertEqual(
            overrides_n_api_prx["endpoints"]["identity"]["auth"]["placement"],
            overrides_placement["endpoints"]["identity"]["auth"]["placement"],
        )

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
    def test_nova_api_proxy_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA_API_PROXY,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'conf': {
                'nova_api_proxy': {
                    'keystone_authtoken': {
                        'cafile': nova_api_proxy.NovaApiProxyHelm.get_ca_file()
                    },
                }
            },
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': nova_api_proxy.NovaApiProxyHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'nova': {
                            'cacert': nova_api_proxy.NovaApiProxyHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'neutron': {
                            'cacert': nova_api_proxy.NovaApiProxyHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'placement': {
                            'cacert': nova_api_proxy.NovaApiProxyHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'test': {
                            'cacert': nova_api_proxy.NovaApiProxyHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                },
                'compute': {
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
                    'compute': {
                        'api_proxy': {
                            'public': 'nova-tls-public',
                        },
                    },
                },
            },
        })
