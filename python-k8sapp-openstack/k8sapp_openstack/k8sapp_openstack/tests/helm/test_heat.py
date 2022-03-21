#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
import mock

from oslo_utils import uuidutils
from sysinv.common import constants
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
    def test_heat_overrides(self):
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
    @mock.patch.object(heat.HeatHelm, "_https_enabled",
                       return_value=True)
    def test_heat_overrides_https_enabled(self, *_):
        self.dbapi.certificate_create(
            {
                "id": 1,
                "uuid": uuidutils.generate_uuid(),
                "certtype": constants.CERT_MODE_OPENSTACK,
                "signature": "abcdef",
            }
        )

        self.dbapi.certificate_create(
            {
                "id": 2,
                "uuid": uuidutils.generate_uuid(),
                "certtype": constants.CERT_MODE_OPENSTACK_CA,
                "signature": "abcdef",
            }
        )

        self.dbapi.certificate_create(
            {
                "id": 3,
                "uuid": uuidutils.generate_uuid(),
                "certtype": constants.CERT_MODE_SSL_CA,
                "signature": "abcdef",
            }
        )

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
