#
# Copyright (c) 2019-2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack

import tsconfig.tsconfig as tsc
from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import utils
from sysinv.common.storage_backend_conf import StorageBackendConfig

from sysinv.helm import common


class CinderHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the cinder chart"""

    CHART = app_constants.HELM_CHART_CINDER

    SERVICE_NAME = app_constants.HELM_CHART_CINDER
    SERVICE_TYPE = 'volume'
    AUTH_USERS = ['cinder']

    def _get_mount_overrides(self):
        overrides = {
            'volumes': [],
            'volumeMounts': []
        }
        overrides['volumes'].append({
            'name': 'newvolume',
            'hostPath': {'path': tsc.IMAGE_CONVERSION_PATH}
        })
        overrides['volumeMounts'].append({
            'name': 'newvolume',
            'mountPath': tsc.IMAGE_CONVERSION_PATH
        })
        return overrides

    def get_overrides(self, namespace=None):
        if self._is_rook_ceph():
            cinder_override = self._get_conf_rook_cinder_overrides()
            ceph_override = self._get_conf_rook_ceph_overrides()
            backend_override = self._get_conf_rook_backends_overrides()
        else:
            cinder_override = self._get_conf_cinder_overrides()
            ceph_override = self._get_conf_ceph_overrides()
            backend_override = self._get_conf_backends_overrides()

        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': {
                    'mounts': {
                        'cinder_volume': {
                            'cinder_volume': self._get_mount_overrides()
                        }
                    },
                    'replicas': {
                        'api': self._num_provisioned_controllers(),
                        'volume': self._num_provisioned_controllers(),
                        'scheduler': self._num_provisioned_controllers(),
                        'backup': self._num_provisioned_controllers()
                    }
                },
                'conf': {
                    'cinder': cinder_override,
                    'ceph': ceph_override,
                    'backends': backend_override,
                },
                'endpoints': self._get_endpoints_overrides(),
                'ceph_client': self._get_ceph_client_overrides()
            }
        }

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides

    def _get_conf_ceph_overrides(self):
        ceph_backend = self._get_primary_ceph_backend()
        if not ceph_backend:
            return {}

        primary_tier_name =\
            constants.SB_TIER_DEFAULT_NAMES[constants.SB_TIER_TYPE_CEPH]

        replication, min_replication =\
            StorageBackendConfig.get_ceph_pool_replication(self.dbapi)

        pools = {}
        for backend in self.dbapi.storage_ceph_get_list():
            if backend.tier_name == primary_tier_name:
                pool_name = app_constants.CEPH_POOL_VOLUMES_NAME
            else:
                pool_name = "%s-%s" % (app_constants.CEPH_POOL_VOLUMES_NAME,
                                      backend.tier_name)
            rule_name = "{0}{1}{2}".format(
                backend.tier_name, constants.CEPH_CRUSH_TIER_SUFFIX,
                "-ruleset").replace('-', '_')
            pool = {
                'replication': replication,
                'crush_rule': rule_name.encode('utf8', 'strict'),
                'chunk_size': app_constants.CEPH_POOL_VOLUMES_CHUNK_SIZE,
                'app_name': app_constants.CEPH_POOL_VOLUMES_APP_NAME
            }
            pools[pool_name.encode('utf8', 'strict')] = pool
            if backend.name == constants.SB_DEFAULT_NAMES[constants.SB_TYPE_CEPH]:
                # Backup uses the same replication and crush rule as
                # the default storage backend
                pool_backup = {
                    'replication': replication,
                    'crush_rule': rule_name.encode('utf8', 'strict'),
                    'chunk_size': app_constants.CEPH_POOL_BACKUP_CHUNK_SIZE,
                    'app_name': app_constants.CEPH_POOL_BACKUP_APP_NAME
                }
                pools['backup'] = dict(pool_backup)

        return {
            'monitors': self._get_formatted_ceph_monitor_ips(),
            'admin_keyring': 'null',
            'pools': pools
        }

    def _get_conf_cinder_overrides(self):
        # Get all the internal CEPH backends.
        backends = self.dbapi.storage_backend_get_list_by_type(
            backend_type=constants.SB_TYPE_CEPH)
        conf_cinder = {
            'DEFAULT': {
                'enabled_backends': ','.join(
                    str(b.name.encode('utf8', 'strict').decode('utf-8')) for b in backends)
            },
        }
        current_host_fs_list = self.dbapi.host_fs_get_list()

        chosts = self.dbapi.ihost_get_by_personality(constants.CONTROLLER)
        chosts_fs = [fs for fs in current_host_fs_list
                            if fs['name'] == constants.FILESYSTEM_NAME_IMAGE_CONVERSION]

        # conversion overrides should be generated only if each controller node
        # configured has the conversion partition added
        if len(chosts) == len(chosts_fs):
            conf_cinder['DEFAULT']['image_conversion_dir'] = \
                tsc.IMAGE_CONVERSION_PATH

        # Always set the default_volume_type to the volume type associated with the
        # primary Ceph backend/tier which is available on all StarlingX platform
        # configurations. This will guarantee that any Cinder API requests for
        # this value will be fulfilled as part of determining a safe volume type to
        # use during volume creation. This can be overrides by the user when/if
        # additional backends are added to the platform.
        default = next(
            (b.name for b in backends
                if b.name == constants.SB_DEFAULT_NAMES[constants.SB_TYPE_CEPH]), None)
        if default:
            conf_cinder['DEFAULT']['default_volume_type'] = \
                default.encode('utf8', 'strict')

        return conf_cinder

    def _get_conf_backends_overrides(self):
        conf_backends = {}

        # We don't use the chart's default backends.
        conf_backends['rbd1'] = {
            'volume_driver': ''
        }

        # Get tier info.
        tiers = self.dbapi.storage_tier_get_list()
        primary_tier_name =\
            constants.SB_TIER_DEFAULT_NAMES[constants.SB_TIER_TYPE_CEPH]

        # We support primary and secondary CEPH tiers.
        backends = self.dbapi.storage_backend_get_list_by_type(
            backend_type=constants.SB_TYPE_CEPH)

        # No data if there are no CEPH backends.
        if not backends:
            return {}

        for bk in backends:
            bk_name = bk.name.encode('utf8', 'strict')
            tier = next((t for t in tiers if t.forbackendid == bk.id), None)
            if not tier:
                raise Exception("No tier present for backend %s" % bk_name)

            if tier.name == primary_tier_name:
                rbd_pool = app_constants.CEPH_POOL_VOLUMES_NAME
            else:
                rbd_pool = "%s-%s" % (app_constants.CEPH_POOL_VOLUMES_NAME,
                                      tier.name)

            conf_backends[bk_name] = {
                'image_volume_cache_enabled': 'True',
                'volume_backend_name': bk_name,
                'volume_driver': 'cinder.volume.drivers.rbd.RBDDriver',
                'rbd_pool': rbd_pool.encode('utf8', 'strict'),
                'rbd_user': 'cinder',
                'rbd_ceph_conf':
                    (constants.CEPH_CONF_PATH +
                     constants.SB_TYPE_CEPH_CONF_FILENAME),
            }

        return conf_backends

    def _get_endpoints_overrides(self):
        return {
            'identity': {
                'auth':
                self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS),
            },
            'oslo_db': {
                'auth': self._get_endpoints_oslo_db_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS)
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
            'volume': {
                'host_fqdn_override':
                    self._get_endpoints_host_fqdn_overrides(
                        self.SERVICE_NAME),
                'port': self._get_endpoints_port_api_public_overrides(),
                'scheme': self._get_endpoints_scheme_public_overrides(),
            },
            'volumev2': {
                'host_fqdn_override':
                    self._get_endpoints_host_fqdn_overrides(
                        self.SERVICE_NAME),
                'port': self._get_endpoints_port_api_public_overrides(),
                'scheme': self._get_endpoints_scheme_public_overrides(),
            },
            'volumev3': {
                'host_fqdn_override':
                    self._get_endpoints_host_fqdn_overrides(
                        self.SERVICE_NAME),
                'port': self._get_endpoints_port_api_public_overrides(),
                'scheme': self._get_endpoints_scheme_public_overrides(),
            },

        }

    def _get_primary_ceph_backend(self):
        try:
            backend = self.dbapi.storage_backend_get_by_name(
                constants.SB_DEFAULT_NAMES[constants.SB_TYPE_CEPH])
        except Exception:
            backend = None
            pass

        return backend

    def get_region_name(self):
        return self._get_service_region_name(self.SERVICE_NAME)

    def get_service_name_v2(self):
        return self._get_configured_service_name(self.SERVICE_NAME, 'v2')

    def get_service_type_v2(self):
        service_type = self._get_configured_service_type(
            self.SERVICE_NAME, 'v2')
        if service_type is None:
            return self.SERVICE_TYPE + 'v2'
        else:
            return service_type

    def _get_conf_rook_cinder_overrides(self):
        conf_cinder = {
            'DEFAULT': {
                'enabled_backends': 'ceph-store',
                'default_volume_type': 'ceph-store'
            },
        }

        return conf_cinder

    def _get_conf_rook_ceph_overrides(self):
        replication = 2
        if utils.is_aio_simplex_system(self.dbapi):
            replication = 1

        pools = {
            'cinder-volumes': {
                'app_name': 'cinder-volumes',
                'chunk_size': 8,
                'crush_rule': 'kube-rbd',
                'replication': replication,
            },
            'backup': {
                'app_name': 'cinder-volumes',
                'chunk_size': 8,
                'crush_rule': 'kube-rbd',
                'replication': replication,
            },
        }

        ceph_override = {
            'admin_keyring': self._get_rook_ceph_admin_keyring(),
            'monitors': [],
            'pools': pools,
        }
        return ceph_override

    def _get_conf_rook_backends_overrides(self):
        conf_backends = {}

        # We don't use the chart's default backends.
        conf_backends['rbd1'] = {
            'volume_driver': ''
        }

        conf_backends['ceph-store'] = {
            'image_volume_cache_enabled': 'True',
            'volume_backend_name': 'ceph-store',
            'volume_driver': 'cinder.volume.drivers.rbd.RBDDriver',
            'rbd_pool': 'cinder-volumes',
            'rbd_user': 'cinder',
            'rbd_ceph_conf':
                (constants.CEPH_CONF_PATH +
                 constants.SB_TYPE_CEPH_CONF_FILENAME),
        }
        return conf_backends
