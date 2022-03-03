#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
import mock

from oslo_utils import uuidutils
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

    def test_nova_overrides(self):
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

    def test_nova_overrides_reuses_neutron_ironic_placement_users(self):
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

        self.assertEquals(
            overrides_nova["endpoints"]["identity"]["auth"]["neutron"],
            overrides_neutron["endpoints"]["identity"]["auth"]["neutron"],
        )
        self.assertEquals(
            overrides_nova["endpoints"]["identity"]["auth"]["ironic"],
            overrides_ironic["endpoints"]["identity"]["auth"]["ironic"],
        )
        self.assertEquals(
            overrides_nova["endpoints"]["identity"]["auth"]["placement"],
            overrides_placement["endpoints"]["identity"]["auth"]["placement"],
        )

    @mock.patch('os.path.exists', return_value=True)
    @mock.patch('six.moves.builtins.open', mock.mock_open(read_data="fake"))
    @mock.patch.object(nova.NovaHelm, "_https_enabled",
                       return_value=True)
    def test_nova_overrides_https_enabled(self, *_):
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
