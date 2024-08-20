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
from k8sapp_openstack.helm import fm_rest_api
from k8sapp_openstack.tests import test_plugins


class FmRestApiHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                            base.HelmTestCaseMixin):
    def setUp(self):
        super(FmRestApiHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class FmRestApiGetOverrideTest(FmRestApiHelmTestCase,
                               dbbase.ControllerHostTestCase):
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_fm_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_FM_REST_API,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'endpoints': {
                'faultmanagement': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            },
            'pod': {
                'replicas': {
                    'api': {}
                }
            }
        })

    @mock.patch('os.path.exists', return_value=True)
    @mock.patch('six.moves.builtins.open', mock.mock_open(read_data="fake"))
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=True)
    @mock.patch(
        'k8sapp_openstack.utils.get_certificate_file',
        return_value='/var/opt/openstack/ssl/openstack-helm.crt'
    )
    def test_fm_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_FM_REST_API,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'conf': {
                'fm': {
                    'keystone_authtoken': {
                        'cafile': fm_rest_api.FmRestApiHelm.get_ca_file()
                    },
                }
            },
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': fm_rest_api.FmRestApiHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'fm': {
                            'cacert': fm_rest_api.FmRestApiHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                },
                'faultmanagement': {
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
            'secrets': {
                'tls': {
                    'faultmanagement': {
                        'fm_api': {
                            'internal': 'keystone-tls-public',
                            'public': 'keystone-tls-public',
                        },
                        'faultmanagement': {
                            'public': 'keystone-tls-public',
                        },
                    },
                },
            },
        })
