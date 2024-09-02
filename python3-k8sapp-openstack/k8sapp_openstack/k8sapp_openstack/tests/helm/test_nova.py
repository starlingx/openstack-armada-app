#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.common import constants
from sysinv.helm import common
from sysinv.helm import helm
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import nova
from k8sapp_openstack.tests import test_plugins


class NovaHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                               base.HelmTestCaseMixin):
    def setUp(self):
        super(NovaHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class NovaGetOverrideTest(NovaHelmTestCase,
                          dbbase.ControllerHostTestCase):

    def setUp(self):
        super(NovaGetOverrideTest, self).setUp()
        self.operator = helm.HelmOperator(self.dbapi)
        self.nova = nova.NovaHelm(self.operator)
        self.worker = self._create_test_host(
            personality=constants.WORKER,
            administrative=constants.ADMIN_LOCKED)
        self.ifaces = self._create_test_host_platform_interface(self.worker)
        self.dbapi.address_create({
            'name': 'test',
            'family': self.oam_subnet.version,
            'prefix': self.oam_subnet.prefixlen,
            'address': str(self.oam_subnet[24]),
            'interface_id': self.ifaces[0].id,
            'enable_dad': self.oam_subnet.version == 6
        })

    def test_update_host_addresses(self):
        self.nova._update_host_addresses(self.worker, {}, {}, {})

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_nova_overrides(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
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
                'compute_novnc_proxy': {
                    'host_fqdn_override': {
                        'public': {},
                    },
                },
            },
        })

    @mock.patch('k8sapp_openstack.utils.is_openstack_https_ready', return_value=False)
    def test_nova_overrides_reuses_neutron_ironic_placement_users(self, *_):
        overrides_neutron = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NEUTRON,
            cnamespace=common.HELM_NS_OPENSTACK)
        overrides_ironic = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_IRONIC,
            cnamespace=common.HELM_NS_OPENSTACK)
        overrides_placement = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_PLACEMENT,
            cnamespace=common.HELM_NS_OPENSTACK)
        overrides_nova = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertEqual(
            overrides_nova["endpoints"]["identity"]["auth"]["neutron"],
            overrides_neutron["endpoints"]["identity"]["auth"]["neutron"],
        )
        self.assertEqual(
            overrides_nova["endpoints"]["identity"]["auth"]["ironic"],
            overrides_ironic["endpoints"]["identity"]["auth"]["ironic"],
        )
        self.assertEqual(
            overrides_nova["endpoints"]["identity"]["auth"]["placement"],
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
        'k8sapp_openstack.utils.get_openstack_certificate_files',
        return_value={
            app_constants.OPENSTACK_CERT: '/etc/ssl/private/openstack/cert.pem',
            app_constants.OPENSTACK_CERT_KEY: '/etc/ssl/private/openstack/key.pem',
            app_constants.OPENSTACK_CERT_CA: '/etc/ssl/private/openstack/ca-cert.pem'
        }
    )
    def test_nova_overrides_https_enabled(self, *_):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_NOVA,
            cnamespace=common.HELM_NS_OPENSTACK)

        self.assertOverridesParameters(overrides, {
            'conf': {
                'nova': {
                    'keystone_authtoken': {
                        'cafile': nova.NovaHelm.get_ca_file()
                    },
                    'libvirt': {
                        'virt_type': mock.ANY,
                    },
                    'vnc': {
                        'novncproxy_base_url': mock.ANY,
                    },
                    'pci': mock.ANY,
                },
                'ceph': {
                    'ephemeral_storage': mock.ANY,
                    'admin_keyring': mock.ANY,
                },
                'overrides': {
                    'nova_compute': mock.ANY,
                },
            },
            'endpoints': {
                'identity': {
                    'auth': {
                        'admin': {
                            'cacert': nova.NovaHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'nova': {
                            'cacert': nova.NovaHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'neutron': {
                            'cacert': nova.NovaHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'placement': {
                            'cacert': nova.NovaHelm.get_ca_file(),
                            'password': mock.ANY,
                            'region_name': mock.ANY,
                        },
                        'test': {
                            'cacert': nova.NovaHelm.get_ca_file(),
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
                'compute_novnc_proxy': {
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
                    'compute_metadata': {
                        'metadata': {
                            'public': 'nova-tls-public',
                        },
                    },
                },
            },
        })
