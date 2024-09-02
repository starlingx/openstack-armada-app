#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.helm import common
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import barbican
from k8sapp_openstack.tests import test_plugins


class BarbicanHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                           base.HelmTestCaseMixin):
    def setUp(self):
        super(BarbicanHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class BarbicanGetOverrideTest(BarbicanHelmTestCase,
                              dbbase.ControllerHostTestCase):
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_barbican_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_BARBICAN,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {},
            'endpoints': {
                'key_manager': {
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
        'k8sapp_openstack.utils.get_openstack_certificate_files',
        return_value={
            app_constants.OPENSTACK_CERT: '/etc/ssl/private/openstack/cert.pem',
            app_constants.OPENSTACK_CERT_KEY: '/etc/ssl/private/openstack/key.pem',
            app_constants.OPENSTACK_CERT_CA: '/etc/ssl/private/openstack/ca-cert.pem'
        }
    )
    def test_barbican_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_BARBICAN,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'conf': {
                'barbican': {
                    'keystone_authtoken': {
                        'cafile': barbican.BarbicanHelm.get_ca_file()
                    },
                },
            },
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': barbican.BarbicanHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'barbican': {
                            'cacert': barbican.BarbicanHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                },
                'key_manager': {
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
