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
from k8sapp_openstack.helm import glance
from k8sapp_openstack.tests import test_plugins


class GlanceHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                         base.HelmTestCaseMixin):
    def setUp(self):
        super(GlanceHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class GlanceGetOverrideTest(GlanceHelmTestCase,
                               dbbase.ControllerHostTestCase):
    def test_glance_overrides(self):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_GLANCE,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'pod': {},
            'endpoints': {
                'image': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            },
            'storage': {},
            'conf': {},
            'bootstrap': {},
            'ceph_client': {},
        })

    @mock.patch('os.path.exists', return_value=True)
    @mock.patch('six.moves.builtins.open', mock.mock_open(read_data="fake"))
    @mock.patch('k8sapp_openstack.utils.https_enabled', return_value=True)
    def test_glance_overrides_https_enabled(self, *_):
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
            app_constants.HELM_CHART_GLANCE,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'conf': {
                'glance': {
                    'keystone_authtoken': {
                        'cafile': glance.GlanceHelm.get_ca_file()
                    },
                    'glance_store': {
                        'https_ca_certificates_file': glance.GlanceHelm.get_ca_file(),
                        'chunk_size': mock.ANY,
                        'filesystem_store_datadir': mock.ANY,
                        'rbd_store_pool': mock.ANY,
                        'rbd_store_user': mock.ANY,
                        'rbd_store_replication': mock.ANY,
                        'rbd_store_crush_rule': mock.ANY,
                    },
                    'DEFAULT': mock.ANY
                },
                'glance_registry': {
                    'keystone_authtoken': {
                        'cafile': glance.GlanceHelm.get_ca_file()
                    },
                },
            },
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': glance.GlanceHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'glance': {
                            'cacert': glance.GlanceHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'test': {
                            'cacert': glance.GlanceHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                },
                'image': {
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
