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
from k8sapp_openstack.helm import neutron
from k8sapp_openstack.tests import test_plugins


class NeutronHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                          base.HelmTestCaseMixin):
    def setUp(self):
        super(NeutronHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class NeutronGetOverrideTest(NeutronHelmTestCase,
                             dbbase.ControllerHostTestCase):
    def test_neutron_overrides(self):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NEUTRON,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {},
            'conf': {},
            'endpoints': {
                'network': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            },
        })

    def test_neutron_reuses_nova_user(self):
        overrides_nova = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK)
        overrides_neutron = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NEUTRON,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertEqual(
            overrides_nova["endpoints"]["identity"]["auth"]["nova"],
            overrides_neutron["endpoints"]["identity"]["auth"]["nova"],
        )

    @mock.patch('os.path.exists', return_value=True)
    @mock.patch('six.moves.builtins.open', mock.mock_open(read_data="fake"))
    @mock.patch('k8sapp_openstack.utils.https_enabled', return_value=True)
    def test_neutron_overrides_https_enabled(self, *_):
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
            app_constants.HELM_CHART_NEUTRON,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'conf': {
                'neutron': {
                    'keystone_authtoken': {
                        'cafile': neutron.NeutronHelm.get_ca_file()
                    },
                    'nova': {
                        'cafile': neutron.NeutronHelm.get_ca_file()
                    },
                },
                'metadata_agent': {
                    'DEFAULT': {
                        'auth_ca_cert': neutron.NeutronHelm.get_ca_file()
                    },
                },
            },
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': neutron.NeutronHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'neutron': {
                            'cacert': neutron.NeutronHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'nova': {
                            'cacert': neutron.NeutronHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'test': {
                            'cacert': neutron.NeutronHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                },
                'network': {
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
