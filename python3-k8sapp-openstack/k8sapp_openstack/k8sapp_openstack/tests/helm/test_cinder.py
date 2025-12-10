#
# Copyright (c) 2020-2024 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.common import constants
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

    @mock.patch(
        'k8sapp_openstack.utils.is_openstack_https_ready',
        return_value=False
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_storage_backends_priority_list',
        return_value=["ceph"]
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_available_volume_backends',
        return_value={"ceph": "general",
                      app_constants.NETAPP_ISCSI_BACKEND_NAME: "",
                      app_constants.NETAPP_NFS_BACKEND_NAME: "",
                      app_constants.NETAPP_FC_BACKEND_NAME: ""}
    )
    def test_cinder_overrides(self, *_):
        """
        Test if cinder overrides are loaded correctly
        """
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

    @mock.patch(
            'os.path.exists',
            return_value=True
    )
    @mock.patch(
        'six.moves.builtins.open',
        mock.mock_open(read_data="fake")
    )
    @mock.patch(
        'k8sapp_openstack.utils.is_openstack_https_ready',
        return_value=True
    )
    @mock.patch(
        'k8sapp_openstack.helm.openstack.OpenstackBaseHelm.get_ca_file',
        return_value='/etc/ssl/private/openstack/ca-cert.pem'
    )
    @mock.patch(
        'k8sapp_openstack.utils.get_openstack_certificate_values',
        return_value={
            app_constants.OPENSTACK_CERT: 'fake',
            app_constants.OPENSTACK_CERT_KEY: 'fake',
            app_constants.OPENSTACK_CERT_CA: 'fake'
        }
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_storage_backends_priority_list',
        return_value=["ceph"]
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_available_volume_backends',
        return_value={"ceph": "general",
                      app_constants.NETAPP_ISCSI_BACKEND_NAME: "",
                      app_constants.NETAPP_NFS_BACKEND_NAME: "",
                      app_constants.NETAPP_FC_BACKEND_NAME: ""}
    )
    def test_cinder_overrides_https_enabled(self, *_):
        """
        Test if cinder overrides with the additional HTTPS
        certificate parameters are loaded correctly
        """
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

    @mock.patch(
        'k8sapp_openstack.utils.is_openstack_https_ready',
        return_value=False
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_storage_backends_priority_list',
        return_value=["ceph", "netapp-nfs", "netapp-iscsi", "netapp-fc"]
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.is_ceph_backend_available',
        return_value=(False, "")
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_cinder_overrides',
        return_value={'DEFAULT': {'enabled_backends': 'ceph', 'default_volume_type': 'ceph'}}
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_overrides',
        return_value={
            'monitors': [],
            'admin_keyring': 'AQCr/DJpZLb4MxAAPXEg+LMODSJ+AB0mb/D+Rg==',
            'pools': {
                'backup': {
                    'app_name': 'cinder-backup',
                    'chunk_size': 0,
                    'crush_rule': 'kube-rbd',
                    'replication': 1
                },
                'cinder-volumes': {
                    'app_name': 'cinder-volumes',
                    'chunk_size': 0,
                    'crush_rule': 'kube-rbd',
                    'replication': 1
                }
            }
        }
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_backends_overrides',
        return_value={
            'ceph': {
                'image_volume_cache_enabled': 'True',
                'volume_backend_name': 'ceph',
                'volume_driver': 'cinder.volume.drivers.rbd.RBDDriver',
                'rbd_pool': constants.CEPH_POOL_VOLUMES_NAME,
                'rbd_user': app_constants.CEPH_RBD_POOL_USER_CINDER,
                'rbd_ceph_conf': (constants.CEPH_CONF_PATH +
                                  constants.SB_TYPE_CEPH_CONF_FILENAME),
            }
        }
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_available_volume_backends',
        return_value={"ceph": "general",
                      app_constants.NETAPP_ISCSI_BACKEND_NAME: "",
                      app_constants.NETAPP_NFS_BACKEND_NAME: "",
                      app_constants.NETAPP_FC_BACKEND_NAME: ""}
    )
    def test_set_default_storage_backend_ceph(self, *_):
        """
        Test if ceph is defined as the default storage backend
        if we don't specify any user overrides
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CINDER,
            cnamespace=common.HELM_NS_OPENSTACK)

        enabled_backends = overrides['conf']['cinder']['DEFAULT']['enabled_backends']
        default_backend = overrides['conf']['cinder']['DEFAULT']['default_volume_type']
        backend_overrides = overrides['conf']['backends']

        pass_condition_1 = set(enabled_backends.split(',')) == {'ceph'}
        pass_condition_2 = default_backend == 'ceph'
        pass_condition_3 = (('ceph' in backend_overrides) and
                            ('netapp-iscsi' not in backend_overrides) and
                            ('netapp-nfs' not in backend_overrides) and
                            ('netapp-fc' not in backend_overrides))

        assert pass_condition_1 and pass_condition_2 and pass_condition_3

    @mock.patch(
        'k8sapp_openstack.utils.is_openstack_https_ready',
        return_value=False
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_storage_backends_priority_list',
        return_value=["ceph", "netapp-nfs", "netapp-iscsi", "netapp-fc"]
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.discover_netapp_credentials',
        return_value={"netapp_login": "user", "netapp_password": "pwd"}
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.discover_netapp_configs',
        return_value={
            "volume_driver": app_constants.NETAPP_CINDER_VOLUME_DRIVER,
            "netapp_storage_family": app_constants.NETAPP_STORAGE_FAMILY,
            "netapp_storage_protocol": app_constants.NETAPP_BACKEND_TO_OPENSTACK_PROTOCOL[
                app_constants.NETAPP_NFS_BACKEND_NAME
            ],
            "netapp_vserver": "svm_nfs",
            "netapp_server_hostname": "10.0.0.20",
            "netapp_server_port": app_constants.NETAPP_DEFAULT_SERVER_PORT,
            "netapp_transport_type": (
                app_constants.NETAPP_DEFAULT_SERVER_TRANSPORT_TYPE
            ),
        }
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_available_volume_backends',
        return_value={"ceph": "",
                      app_constants.NETAPP_ISCSI_BACKEND_NAME: "",
                      app_constants.NETAPP_NFS_BACKEND_NAME: "netapp-nas-backend",
                      app_constants.NETAPP_FC_BACKEND_NAME: ""}
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.is_ceph_backend_available',
        return_value=(False, "")
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_cinder_overrides',
        return_value={'DEFAULT': {'enabled_backends': 'ceph', 'default_volume_type': 'ceph'}}
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_overrides',
        return_value=dict()
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_backends_overrides',
        return_value=dict()
    )
    def test_set_default_storage_backend_netapp_ceph_disabled(self, *_):
        """
        Test if netapp is defined as the default storage backend
        if we disable ceph and enable netapp via user overrides
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CINDER,
            cnamespace=common.HELM_NS_OPENSTACK)

        enabled_backends = overrides['conf']['cinder']['DEFAULT']['enabled_backends']
        default_backend = overrides['conf']['cinder']['DEFAULT']['default_volume_type']
        backend_overrides = overrides['conf']['backends']

        pass_condition_1 = set(enabled_backends.split(',')) == {'netapp-nfs'}
        pass_condition_2 = default_backend == 'netapp-nfs'
        pass_condition_3 = (('ceph' not in backend_overrides) and
                            ('netapp-iscsi' not in backend_overrides) and
                            ('netapp-nfs' in backend_overrides) and
                            ('netapp-fc' not in backend_overrides))

        assert pass_condition_1 and pass_condition_2 and pass_condition_3

    @mock.patch(
        'k8sapp_openstack.utils.is_openstack_https_ready',
        return_value=False
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_storage_backends_priority_list',
        return_value=["netapp-nfs", "ceph", "netapp-iscsi", "netapp-fc"]
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_available_volume_backends',
        return_value={"ceph": "general",
                      app_constants.NETAPP_ISCSI_BACKEND_NAME: "",
                      app_constants.NETAPP_NFS_BACKEND_NAME: "netapp-nas-backend",
                      app_constants.NETAPP_FC_BACKEND_NAME: ""}
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.is_ceph_backend_available',
        return_value=(False, "")
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_cinder_overrides',
        return_value={'DEFAULT': {'enabled_backends': 'ceph', 'default_volume_type': 'ceph'}}
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_overrides',
        return_value={
            'monitors': [],
            'admin_keyring': 'AQCr/DJpZLb4MxAAPXEg+LMODSJ+AB0mb/D+Rg==',
            'pools': {
                'backup': {
                    'app_name': 'cinder-backup',
                    'chunk_size': 0,
                    'crush_rule': 'kube-rbd',
                    'replication': 1
                },
                'cinder-volumes': {
                    'app_name': 'cinder-volumes',
                    'chunk_size': 0,
                    'crush_rule': 'kube-rbd',
                    'replication': 1
                }
            }
        }
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_backends_overrides',
        return_value={
            'ceph': {
                'image_volume_cache_enabled': 'True',
                'volume_backend_name': 'ceph',
                'volume_driver': 'cinder.volume.drivers.rbd.RBDDriver',
                'rbd_pool': constants.CEPH_POOL_VOLUMES_NAME,
                'rbd_user': app_constants.CEPH_RBD_POOL_USER_CINDER,
                'rbd_ceph_conf': (constants.CEPH_CONF_PATH +
                                  constants.SB_TYPE_CEPH_CONF_FILENAME),
            }
        }
    )
    def test_set_default_storage_backend_netapp_ceph_enabled(self, *_):
        """
        Test if netapp is defined as the default storage backend
        if change the priority via user overrides, while both ceph and
        netapp backends are enabled
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CINDER,
            cnamespace=common.HELM_NS_OPENSTACK)

        enabled_backends = overrides['conf']['cinder']['DEFAULT']['enabled_backends']
        default_backend = overrides['conf']['cinder']['DEFAULT']['default_volume_type']
        backend_overrides = overrides['conf']['backends']

        pass_condition_1 = set(enabled_backends.split(',')) == {'ceph', 'netapp-nfs'}
        pass_condition_2 = default_backend == 'netapp-nfs'
        pass_condition_3 = (('ceph' in backend_overrides) and
                            ('netapp-iscsi' not in backend_overrides) and
                            ('netapp-nfs' in backend_overrides) and
                            ('netapp-fc' not in backend_overrides))

        assert pass_condition_1 and pass_condition_2 and pass_condition_3

    @mock.patch(
        'k8sapp_openstack.utils.is_openstack_https_ready',
        return_value=False
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_storage_backends_priority_list',
        return_value=["netapp-iscsi", "ceph", "netapp-nfs", "netapp-fc"]
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.discover_netapp_credentials',
        return_value={"netapp_login": "user", "netapp_password": "pwd"}
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.discover_netapp_configs',
        return_value={
            "volume_driver": app_constants.NETAPP_CINDER_VOLUME_DRIVER,
            "netapp_storage_family": app_constants.NETAPP_STORAGE_FAMILY,
            "netapp_storage_protocol": app_constants.NETAPP_BACKEND_TO_OPENSTACK_PROTOCOL[
                app_constants.NETAPP_NFS_BACKEND_NAME
            ],
            "netapp_vserver": "svm_nfs",
            "netapp_server_hostname": "10.0.0.20",
            "netapp_server_port": app_constants.NETAPP_DEFAULT_SERVER_PORT,
            "netapp_transport_type": (
                app_constants.NETAPP_DEFAULT_SERVER_TRANSPORT_TYPE
            ),
        }
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.get_available_volume_backends',
        return_value={"ceph": "general",
                      app_constants.NETAPP_ISCSI_BACKEND_NAME: "netapp-san-backend",
                      app_constants.NETAPP_NFS_BACKEND_NAME: "netapp-nas-backend",
                      app_constants.NETAPP_FC_BACKEND_NAME: ""}
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.is_ceph_backend_available',
        return_value=(False, "")
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_cinder_overrides',
        return_value={'DEFAULT': {'enabled_backends': 'ceph', 'default_volume_type': 'ceph'}}
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_overrides',
        return_value={
            'monitors': [],
            'admin_keyring': 'AQCr/DJpZLb4MxAAPXEg+LMODSJ+AB0mb/D+Rg==',
            'pools': {
                'backup': {
                    'app_name': 'cinder-backup',
                    'chunk_size': 0,
                    'crush_rule': 'kube-rbd',
                    'replication': 1
                },
                'cinder-volumes': {
                    'app_name': 'cinder-volumes',
                    'chunk_size': 0,
                    'crush_rule': 'kube-rbd',
                    'replication': 1
                }
            }
        }
    )
    @mock.patch(
        'k8sapp_openstack.helm.cinder.CinderHelm._get_conf_ceph_backends_overrides',
        return_value={
            'ceph': {
                'image_volume_cache_enabled': 'True',
                'volume_backend_name': 'ceph',
                'volume_driver': 'cinder.volume.drivers.rbd.RBDDriver',
                'rbd_pool': constants.CEPH_POOL_VOLUMES_NAME,
                'rbd_user': app_constants.CEPH_RBD_POOL_USER_CINDER,
                'rbd_ceph_conf': (constants.CEPH_CONF_PATH +
                                  constants.SB_TYPE_CEPH_CONF_FILENAME),
            }
        }
    )
    def test_set_default_storage_backend_multiple_netapp_ceph_enabled(self, *_):
        """
        Test if netapp-iscsi is defined as the default storage backend
        if change the priority via user overrides, while ceph and
        multiple netapp backends are enabled
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CINDER,
            cnamespace=common.HELM_NS_OPENSTACK)

        enabled_backends = overrides['conf']['cinder']['DEFAULT']['enabled_backends']
        default_backend = overrides['conf']['cinder']['DEFAULT']['default_volume_type']
        backend_overrides = overrides['conf']['backends']

        pass_condition_1 = set(enabled_backends.split(',')) == {
            'ceph', 'netapp-nfs', 'netapp-iscsi'}
        pass_condition_2 = default_backend == 'netapp-iscsi'
        pass_condition_3 = (('ceph' in backend_overrides) and
                            ('netapp-iscsi' in backend_overrides) and
                            ('netapp-nfs' in backend_overrides) and
                            ('netapp-fc' not in backend_overrides))

        assert pass_condition_1 and pass_condition_2 and pass_condition_3
