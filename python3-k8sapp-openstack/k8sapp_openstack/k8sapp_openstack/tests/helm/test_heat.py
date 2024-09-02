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
from k8sapp_openstack.helm import heat
from k8sapp_openstack.tests import test_plugins


class HeatHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                       base.HelmTestCaseMixin):
    def setUp(self):
        super(HeatHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class HeatGetOverrideTest(HeatHelmTestCase,
                            dbbase.ControllerHostTestCase):
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_heat_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_HEAT,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {},
            'endpoints': {
                'cloudformation': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
                'orchestration': {
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
        'k8sapp_openstack.utils.get_openstack_certificate_files',
        return_value={
            app_constants.OPENSTACK_CERT: '/etc/ssl/private/openstack/cert.pem',
            app_constants.OPENSTACK_CERT_KEY: '/etc/ssl/private/openstack/key.pem',
            app_constants.OPENSTACK_CERT_CA: '/etc/ssl/private/openstack/ca-cert.pem'
        }
    )
    def test_heat_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_HEAT,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'conf': {
                'heat': {
                    'keystone_authtoken': {
                        'cafile': heat.HeatHelm.get_ca_file()
                    },
                    'ssl': {
                        'ca_file': heat.HeatHelm.get_ca_file()
                    },
                    'clients': {
                        'ca_file': heat.HeatHelm.get_ca_file()
                    },
                    'clients_aodh': {
                        'ca_file': heat.HeatHelm.get_ca_file()
                    },
                    'clients_neutron': {
                        'ca_file': heat.HeatHelm.get_ca_file()
                    },
                    'clients_cinder': {
                        'ca_file': heat.HeatHelm.get_ca_file()
                    },
                    'clients_glance': {
                        'ca_file': heat.HeatHelm.get_ca_file()
                    },
                    'clients_nova': {
                        'ca_file': heat.HeatHelm.get_ca_file()
                    },
                    'clients_swift': {
                        'ca_file': heat.HeatHelm.get_ca_file()
                    },
                    'clients_heat': {
                        'ca_file': heat.HeatHelm.get_ca_file()
                    },
                    'clients_keystone': {
                        'ca_file': heat.HeatHelm.get_ca_file()
                    },
                },
            },
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': heat.HeatHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'heat': {
                            'cacert': heat.HeatHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'heat_trustee': {
                            'cacert': heat.HeatHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'heat_stack_user': {
                            'cacert': heat.HeatHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'test': {
                            'cacert': heat.HeatHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                },
                'cloudformation': {
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
                'orchestration': {
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
            'secrets': {
                'tls': {
                    'orchestration': {
                        'api': {
                            'internal': 'heat-tls-public',
                        },
                    },
                    'cloudformation': {
                        'cfn': {
                            'internal': 'cloudformation-tls-public',
                        },
                    },
                },
            },
            'manifests': {
                'certificates': True,
            },
        })
