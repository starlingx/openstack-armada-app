#
# Copyright (c) 2019-2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#


from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import utils
from sysinv.common.storage_backend_conf import StorageBackendConfig
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


# Info used in the Glance Helm chart.
RBD_STORE_USER = 'images'


class GlanceHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the glance chart"""

    CHART = app_constants.HELM_CHART_GLANCE
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_GLANCE

    SERVICE_NAME = app_constants.HELM_CHART_GLANCE
    SERVICE_TYPE = 'image'
    AUTH_USERS = ['glance']

    def get_overrides(self, namespace=None):
        self._rook_ceph = self._is_rook_ceph()

        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': self._get_pod_overrides(),
                'endpoints': self._get_endpoints_overrides(),
                'storage': self._get_storage_overrides(),
                'conf': self._get_conf_overrides(),
                'bootstrap': self._get_bootstrap_overrides(),
                'ceph_client': self._get_ceph_client_overrides(),
            }
        }

        if self._is_openstack_https_ready():
            overrides[common.HELM_NS_OPENSTACK] = \
                self._enable_certificates(overrides[common.HELM_NS_OPENSTACK])

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides

    def _get_pod_overrides(self):
        replicas_count = 1
        ceph_backend = self._get_primary_ceph_backend()
        if ceph_backend:
            replicas_count = self._num_provisioned_controllers()

        return {
            'replicas': {
                'api': replicas_count,
            }
        }

    def _get_endpoints_overrides(self):
        return {
            'image': {
                'host_fqdn_override':
                    self._get_endpoints_host_fqdn_overrides(
                        app_constants.HELM_CHART_GLANCE),
                'scheme': self._get_endpoints_scheme_public_overrides(),
                'port': self._get_endpoints_port_api_public_overrides(),
            },
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS),
            },
            'oslo_cache': {
                'auth': {
                    'memcache_secret_key':
                        self._get_common_password('auth_memcache_key')
                }
            },
            'oslo_messaging': {
                'auth': self._get_endpoints_oslo_messaging_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS)
            },
            'oslo_db': {
                'auth': self._get_endpoints_oslo_db_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS)
            },

        }

    def _get_storage_overrides(self):
        if self._rook_ceph:
            return "rbd"

        ceph_backend = self._get_primary_ceph_backend()
        if not ceph_backend:
            return 'pvc'

        return constants.GLANCE_BACKEND_RBD  # radosgw| rbd | swift | pvc

    def _get_ceph_overrides(self):
        conf_ceph = {
            'admin_keyring': self._get_ceph_password(
                self.SERVICE_NAME, 'admin_keyring'
            ),
            'monitors': self._get_formatted_ceph_monitor_ips()
        }

        return conf_ceph

    def _get_conf_overrides(self):
        ceph_backend = self._get_primary_ceph_backend()
        if not ceph_backend and not self._rook_ceph:
            rbd_store_pool = ""
            rbd_store_user = ""
            replication = 1
        elif self._rook_ceph:
            rbd_store_pool = constants.CEPH_POOL_IMAGES_NAME
            rbd_store_user = RBD_STORE_USER

            replication = 2
            if utils.is_aio_simplex_system(self.dbapi):
                replication = 1
        else:
            rbd_store_pool = app_constants.CEPH_POOL_IMAGES_NAME
            rbd_store_user = RBD_STORE_USER
            replication, min_replication = \
                StorageBackendConfig.get_ceph_pool_replication(self.dbapi)

        if not self._rook_ceph:
            # Only the primary Ceph tier is used for the glance images pool
            rule_name = "{0}{1}{2}".format(
                constants.SB_TIER_DEFAULT_NAMES[
                    constants.SB_TIER_TYPE_CEPH],
                constants.CEPH_CRUSH_TIER_SUFFIX,
                "-ruleset").replace('-', '_')
        else:
            rule_name = "storage_tier_ruleset"

        chunk_size = self._estimate_ceph_pool_pg_num(self.dbapi.istor_get_all())

        conf = {
            'glance': {
                'DEFAULT': {
                    'graceful_shutdown': True,
                    'show_image_direct_url': True,
                },
                'glance_store': {
                    'chunk_size': min(chunk_size, app_constants.CEPH_POOL_IMAGES_CHUNK_SIZE),
                    'filesystem_store_datadir': constants.GLANCE_IMAGE_PATH,
                    'rbd_store_pool': rbd_store_pool,
                    'rbd_store_user': rbd_store_user,
                    'rbd_store_replication': replication,
                    'rbd_store_crush_rule': rule_name,
                }
            }
        }

        if ceph_backend:
            conf['ceph'] = self._get_ceph_overrides()
        elif self._rook_ceph:
            conf['ceph'] = {
                'admin_keyring': self._get_rook_ceph_admin_keyring()
            }

        if self._is_openstack_https_ready():
            conf = self._update_overrides(conf, {
                'glance': {
                    'keystone_authtoken': {
                        'cafile': self.get_ca_file(),
                    },
                    'glance_store': {
                        'https_ca_certificates_file': self.get_ca_file(),
                    },
                },
                'glance_registry': {
                    'keystone_authtoken': {
                        'cafile': self.get_ca_file(),
                    }
                },
            })

        return conf

    def _get_bootstrap_overrides(self):
        # By default, prevent the download and creation of the Cirros image.
        # TODO: Remove if/when pulling from external registries is supported.
        bootstrap = {
            'enabled': False
        }

        return bootstrap

    def _get_primary_ceph_backend(self):
        try:
            backend = self.dbapi.storage_backend_get_by_name(
                constants.SB_DEFAULT_NAMES[constants.SB_TYPE_CEPH])
        except exception.StorageBackendNotFoundByName:
            backend = None
            pass

        return backend

    def get_region_name(self):
        return self._get_service_region_name(self.SERVICE_NAME)

    def get_service_name(self):
        return self._get_configured_service_name(self.SERVICE_NAME)

    def get_service_type(self):
        service_type = self._get_configured_service_type(self.SERVICE_NAME)
        if service_type is None:
            return self.SERVICE_TYPE
        else:
            return service_type
