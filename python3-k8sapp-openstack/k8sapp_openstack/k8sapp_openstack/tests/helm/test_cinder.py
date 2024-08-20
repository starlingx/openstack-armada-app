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
import tsconfig.tsconfig as tsc

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import cinder
from k8sapp_openstack.tests import test_plugins


class CinderConversionTestCase(test_plugins.K8SAppOpenstackAppMixin,
                               base.HelmTestCaseMixin):
    def setUp(self):
        super(CinderConversionTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class CinderGetOverrideTest(CinderConversionTestCase,
                            dbbase.ControllerHostTestCase):
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_cinder_overrides(self, *_):
        dbutils.create_test_host_fs(name='image-conversion',
                                    forihostid=self.host.id)
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CINDER,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'conf': {
                'cinder': {
                    'DEFAULT': {
                        'image_conversion_dir': tsc.IMAGE_CONVERSION_PATH}}},
            'endpoints': {
                'volume': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
                'volumev2': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
                'volumev3': {
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
        'k8sapp_openstack.utils.get_certificate_file',
        return_value='/var/opt/openstack/ssl/openstack-helm.crt'
    )
    def test_cinder_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CINDER,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'conf': {
                'cinder': {
                    'keystone_authtoken': {
                        'cafile': cinder.CinderHelm.get_ca_file()
                    },
                }
            },
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': cinder.CinderHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'cinder': {
                            'cacert': cinder.CinderHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'test': {
                            'cacert': cinder.CinderHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                },
                'volume': {
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
                'volumev2': {
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
                'volumev3': {
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
