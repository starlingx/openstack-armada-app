#
# Copyright (c) 2026 Wind River Systems, Inc.
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
from k8sapp_openstack.helm import masakari
from k8sapp_openstack.tests import test_plugins


class MasakariHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                           base.HelmTestCaseMixin):
    def setUp(self):
        super(MasakariHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class MasakariGetOverrideTest(MasakariHelmTestCase,
                              dbbase.ControllerHostTestCase):
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready',
                return_value=False)
    def test_masakari_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_MASAKARI,
            cnamespace=common.HELM_NS_OPENSTACK)

        # The instance monitor is enabled; the host monitor is left disabled
        # (it needs the Node-read RBAC and taint-gate).
        self.assertEqual(overrides['manifests']['instance_monitor'], True)

        # masakari-api binds :: so it is reachable on IPv6-only deployments.
        self.assertEqual(
            overrides['conf']['masakari']['DEFAULT']['masakari_api_listen'],
            '::')

        # api and engine replicas track the provisioned controller count.
        self.assertIn('masakari_api', overrides['pod']['replicas'])
        self.assertIn('masakari_engine', overrides['pod']['replicas'])

        # The endpoints must carry the auth blocks so the chart does not fall
        # back to its hardcoded defaults - oslo_db.auth.admin is what the
        # db-init job needs (the "Access denied for user root" fix).
        self.assertOverridesParameters(overrides, {
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'masakari': {
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                    },
                },
                'oslo_db': {
                    'auth': {
                        'admin': {
                            'password': mock.ANY,
                        },
                        'masakari': {
                            'password': mock.ANY,
                        },
                    },
                },
                'oslo_messaging': {
                    'auth': {
                        'admin': {
                            'password': mock.ANY,
                        },
                        'masakari': {
                            'password': mock.ANY,
                        },
                    },
                },
                'instance_ha': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            },
        })

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready',
                return_value=False)
    def test_masakari_overrides_invalid_namespace(self, *_):
        self.assertRaises(
            exception.InvalidHelmNamespace,
            self.operator.get_helm_chart_overrides,
            app_constants.HELM_CHART_MASAKARI,
            cnamespace=common.HELM_NS_DEFAULT)

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready',
                return_value=False)
    def test_masakari_overrides_missing_namespace(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_MASAKARI)

        # With no namespace the full override dict is returned, keyed by the
        # openstack namespace.
        self.assertIsInstance(overrides, dict)
        self.assertIn(common.HELM_NS_OPENSTACK, overrides)

    @mock.patch('os.path.exists', return_value=True)
    @mock.patch('six.moves.builtins.open', mock.mock_open(read_data="fake"))
    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready',
                return_value=True)
    @mock.patch(
        'k8sapp_openstack.utils.get_openstack_certificate_values',
        return_value={
            app_constants.OPENSTACK_CERT: 'fake',
            app_constants.OPENSTACK_CERT_KEY: 'fake',
            app_constants.OPENSTACK_CERT_CA: 'fake',
        })
    def test_masakari_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_MASAKARI,
            cnamespace=common.HELM_NS_OPENSTACK)

        # HTTPS only changes the public endpoint. The certificates manifest
        # stays off: in this chart it only enables backend MariaDB/RabbitMQ TLS.
        self.assertOverridesParameters(overrides, {
            'endpoints': {
                'instance_ha': {
                    'scheme': {'public': 'https'},
                    'port': {'api': {'public': 443}},
                },
            },
        })
        # conf carries only the api bind host, not a keystone_authtoken cafile.
        self.assertEqual(list(overrides['conf']['masakari']), ['DEFAULT'])
        self.assertNotIn('certificates', overrides['manifests'])


class MasakariBootstrapOverrideTest(dbbase.ControllerHostTestCase):
    def setUp(self):
        super(MasakariBootstrapOverrideTest, self).setUp()
        self.masakari = masakari.MasakariHelm(mock.Mock(dbapi=self.dbapi))

    @mock.patch('k8sapp_openstack.helm.masakari.get_hosts_uuids',
                return_value=[{'name': 'compute-1', 'uuid': 'b'},
                              {'name': 'compute-0', 'uuid': 'a'}])
    @mock.patch('sysinv.common.utils.is_aio_simplex_system',
                return_value=False)
    def test_bootstrap_segment(self, *_):
        bootstrap = self.masakari._get_bootstrap_overrides()

        # Only the host list comes from the plugin; the segment itself is
        # defined in the static overrides. Sorted, so the overrides only
        # change with the host list.
        self.assertEqual(bootstrap, {
            'enabled': True,
            'structured': {
                'segments': {
                    'stx_compute': {'hosts': ['compute-0', 'compute-1']},
                },
            },
        })

    @mock.patch('k8sapp_openstack.helm.masakari.get_hosts_uuids',
                return_value=[])
    @mock.patch('sysinv.common.utils.is_aio_simplex_system',
                return_value=False)
    def test_bootstrap_no_compute_hosts(self, *_):
        # An empty list is still passed so the Job removes the last host.
        bootstrap = self.masakari._get_bootstrap_overrides()

        self.assertTrue(bootstrap['enabled'])
        self.assertEqual(
            bootstrap['structured']['segments']['stx_compute']['hosts'], [])

    @mock.patch('k8sapp_openstack.helm.masakari.get_hosts_uuids')
    @mock.patch('sysinv.common.utils.is_aio_simplex_system',
                return_value=True)
    def test_bootstrap_disabled_on_aio_simplex(self, _simplex, get_hosts):
        self.assertEqual(self.masakari._get_bootstrap_overrides(),
                         {'enabled': False})
        get_hosts.assert_not_called()
