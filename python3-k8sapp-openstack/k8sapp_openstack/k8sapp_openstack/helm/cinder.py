#
# Copyright (c) 2019-2024 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import storage_backend_conf
from sysinv.common import utils
from sysinv.helm import common
from tsconfig import tsconfig as tsc

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack
from k8sapp_openstack.utils import check_netapp_backends
from k8sapp_openstack.utils import get_ceph_uuid
from k8sapp_openstack.utils import get_image_rook_ceph
from k8sapp_openstack.utils import is_netapp_available
from k8sapp_openstack.utils import is_rook_ceph_backend_available


ROOK_CEPH_BACKEND_NAME = app_constants.CEPH_ROOK_BACKEND_NAME
NETAPP_NFS_BACKEND_NAME = 'netapp-nfs'
NETAPP_ISCSI_BACKEND_NAME = 'netapp-iscsi'


class CinderHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the cinder chart"""

    CHART = app_constants.HELM_CHART_CINDER
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_CINDER

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
        # Create general Cinder overrides before checking
        # the configuration for the specific backends
        cinder_overrides = self._get_common_cinder_overrides()
        backend_overrides = self._get_common_backend_overrides()

        # Ceph and Rook Ceph are mutually exclusive, so it's either one or the other
        if self._is_rook_ceph():
            cinder_overrides = self._get_conf_rook_ceph_cinder_overrides(cinder_overrides)
            backend_overrides = self._get_conf_rook_ceph_backends_overrides(backend_overrides)
            ceph_overrides = self._get_conf_rook_ceph_overrides()
            ceph_client_overrides = self._get_ceph_client_rook_overrides()
        else:
            cinder_overrides = self._get_conf_ceph_cinder_overrides(cinder_overrides)
            backend_overrides = self._get_conf_ceph_backends_overrides(backend_overrides)
            ceph_overrides = self._get_conf_ceph_overrides()
            ceph_client_overrides = self._get_ceph_client_overrides()

        # Add NetApp configuration
        cinder_volume_read_only_filesystem = True
        if is_netapp_available():
            # If NetApp is using NFS, the cinder-volume pod cannot have a readOnly filesystem,
            # as the NFS will be mounted into the pod during initialization
            netapp_backends = check_netapp_backends()
            cinder_volume_read_only_filesystem = not netapp_backends["nfs"]

            cinder_overrides = self._get_conf_netapp_cinder_overrides(cinder_overrides)
            backend_overrides = self._get_conf_netapp_backends_overrides(backend_overrides)

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
                    },
                    'security_context': {
                        'cinder_volume': {
                            'container': {
                                'cinder_volume': {
                                    'readOnlyRootFilesystem': cinder_volume_read_only_filesystem
                                }
                            }
                        }
                    },
                },
                'conf': {
                    'cinder': cinder_overrides,
                    'ceph': ceph_overrides,
                    'backends': backend_overrides,
                },
                'endpoints': self._get_endpoints_overrides(),
                'ceph_client': ceph_client_overrides
            }
        }

        if self._is_openstack_https_ready(self.SERVICE_NAME):
            overrides[common.HELM_NS_OPENSTACK] = \
                self._enable_certificates(overrides[common.HELM_NS_OPENSTACK])

        # The ceph client versions supported by baremetal and rook ceph backends
        # are not necessarily the same. Therefore, the ceph client image must be
        # dynamically configured based on the ceph backend currently deployed.
        if is_rook_ceph_backend_available():
            rook_ceph_config_helper = get_image_rook_ceph()
            overrides[common.HELM_NS_OPENSTACK] = self._update_overrides(
                overrides[common.HELM_NS_OPENSTACK],
                {
                    'images': {
                        'tags': {
                            'cinder_backup_storage_init': rook_ceph_config_helper,
                            'cinder_storage_init': rook_ceph_config_helper
                        }
                    }
                }
            )

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

        replication, min_replication = storage_backend_conf\
            .StorageBackendConfig.get_ceph_pool_replication(self.dbapi)

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

            chunk_size = self._estimate_ceph_pool_pg_num(self.dbapi.istor_get_all())

            pool = {
                'replication': replication,
                'crush_rule': rule_name.encode('utf8', 'strict'),
                'chunk_size': min(chunk_size, app_constants.CEPH_POOL_VOLUMES_CHUNK_SIZE),
                'app_name': app_constants.CEPH_POOL_VOLUMES_APP_NAME
            }
            pools[pool_name.encode('utf8', 'strict')] = pool
            if backend.name == constants.SB_DEFAULT_NAMES[constants.SB_TYPE_CEPH]:
                # Backup uses the same replication and crush rule as
                # the default storage backend
                pool_backup = {
                    'replication': replication,
                    'crush_rule': rule_name.encode('utf8', 'strict'),
                    'chunk_size': min(chunk_size, app_constants.CEPH_POOL_BACKUP_CHUNK_SIZE),
                    'app_name': app_constants.CEPH_POOL_BACKUP_APP_NAME
                }
                pools['backup'] = dict(pool_backup)

        return {
            'monitors': self._get_formatted_ceph_monitor_ips(),
            'admin_keyring': 'null',
            'pools': pools
        }

    def _get_conf_ceph_cinder_overrides(self, cinder_overrides):
        # Ensure 'DEFAULT' key exists in cinder_overrides
        cinder_overrides.setdefault('DEFAULT', {})

        # Get all the internal CEPH backends and construct enabled_backends string
        backends = self.dbapi.storage_backend_get_list_by_type(
            backend_type=constants.SB_TYPE_CEPH)
        new_backends_list = [
            str(b.name.encode('utf8', 'strict').decode('utf-8')) for b in backends
        ]

        # Retrieve existing enabled_backends, merge with new_backends_list, and remove duplicates
        existing_backends = cinder_overrides['DEFAULT'].get('enabled_backends', '').split(',')
        backends_list = list(filter(None, set(existing_backends + new_backends_list)))
        cinder_overrides['DEFAULT']['enabled_backends'] = ','.join(backends_list)

        # Check if conversion overrides should be generated
        current_host_fs_list = self.dbapi.host_fs_get_list()
        chosts = self.dbapi.ihost_get_by_personality(constants.CONTROLLER)
        chosts_fs = [fs for fs in current_host_fs_list
                            if fs['name'] == constants.FILESYSTEM_NAME_IMAGE_CONVERSION]

        # conversion overrides should be generated only if each controller node
        # configured has the conversion partition added
        if len(chosts) == len(chosts_fs):
            cinder_overrides['DEFAULT']['image_conversion_dir'] = tsc.IMAGE_CONVERSION_PATH

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
            cinder_overrides['DEFAULT']['default_volume_type'] = \
                default.encode('utf8', 'strict')

        return cinder_overrides

    def _get_conf_netapp_cinder_overrides(self, cinder_overrides):
        # Ensure 'DEFAULT' key exists in cinder_overrides
        cinder_overrides.setdefault('DEFAULT', {})

        # Get available NetApp backends
        netapp_backends = check_netapp_backends()
        netapp_array = [
            NETAPP_NFS_BACKEND_NAME if netapp_backends.get("nfs") else None,
            NETAPP_ISCSI_BACKEND_NAME if netapp_backends.get("iscsi") else None,
        ]

        # Remove None values
        netapp_array = [item for item in netapp_array if item]

        # Add NetApp backends to Cinder enabled_backends list, ensuring no duplicates
        existing_backends = cinder_overrides['DEFAULT'].get('enabled_backends', '').split(',')
        backends_list = list(filter(None, set(existing_backends + netapp_array)))
        cinder_overrides['DEFAULT']['enabled_backends'] = ','.join(backends_list)

        return cinder_overrides

    def _get_conf_ceph_backends_overrides(self, backend_overrides):
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

            backend_overrides[bk_name] = {
                'image_volume_cache_enabled': 'True',
                'volume_backend_name': bk_name,
                'volume_driver': 'cinder.volume.drivers.rbd.RBDDriver',
                'rbd_pool': rbd_pool.encode('utf8', 'strict'),
                'rbd_user': 'cinder',
                'rbd_ceph_conf':
                    (constants.CEPH_CONF_PATH +
                     constants.SB_TYPE_CEPH_CONF_FILENAME),
            }

            ceph_uuid = get_ceph_uuid()
            if ceph_uuid:
                backend_overrides[bk_name]['rbd_secret_uuid'] = ceph_uuid

        return backend_overrides

    def _get_conf_netapp_backends_overrides(self, backend_overrides):
        cinder_netapp_driver = 'cinder.volume.drivers.netapp.common.NetAppDriver'

        backend_overrides[NETAPP_NFS_BACKEND_NAME] = {
            'volume_driver': cinder_netapp_driver,
            'volume_backend_name': NETAPP_NFS_BACKEND_NAME,
            'netapp_storage_family': 'ontap_cluster',
            'netapp_storage_protocol': 'nfs',
            'nfs_shares_config': '/etc/cinder/nfs.shares'
        }
        backend_overrides[NETAPP_ISCSI_BACKEND_NAME] = {
            'volume_driver': cinder_netapp_driver,
            'volume_backend_name': NETAPP_ISCSI_BACKEND_NAME,
            'netapp_storage_family': 'ontap_cluster',
            'netapp_storage_protocol': 'iscsi',
        }

        return backend_overrides

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

    def get_service_name(self, version=app_constants.CINDER_CURRENT_VERSION):
        return self._get_configured_service_name(self.SERVICE_NAME, version)

    def get_service_type(self, version=app_constants.CINDER_CURRENT_VERSION):
        service_type = self._get_configured_service_type(
            self.SERVICE_NAME, version)
        if service_type is None:
            return self.SERVICE_TYPE + version
        else:
            return service_type

    def _get_common_cinder_overrides(self):
        cinder_overrides = {
            'DEFAULT': {
                'os_region_name': self.get_region_name(),
            },
        }

        if self._is_openstack_https_ready(self.SERVICE_NAME):
            cinder_overrides["keystone_authtoken"] = {
                'cafile': self.get_ca_file()
            }

        return cinder_overrides

    def _get_common_backend_overrides(self):
        backend_overrides = {}

        # We don't use the chart's default backends.
        backend_overrides['rbd1'] = {
            'volume_driver': ''
        }

        return backend_overrides

    def _get_conf_rook_ceph_cinder_overrides(self, cinder_overrides):
        # Ensure 'DEFAULT' key exists in cinder_overrides and update it
        cinder_overrides.setdefault('DEFAULT', {})

        # Retrieve the existing enabled_backends value, or set it to an empty string if not present
        existing_backends = cinder_overrides['DEFAULT'].get('enabled_backends', '')

        # Append 'ceph-store' if it's not already in the enabled_backends list
        backends_list = existing_backends.split(',') if existing_backends else []
        if ROOK_CEPH_BACKEND_NAME not in backends_list:
            backends_list.append(ROOK_CEPH_BACKEND_NAME)

        # Update Cinder overrides
        cinder_overrides['DEFAULT'].update({
            'enabled_backends': ','.join(backends_list),
            # If the user doesn't want Ceph Rook to be the default backend,
            # he can pass a Helm override changing this value, which will
            # override this value
            'default_volume_type': ROOK_CEPH_BACKEND_NAME,
        })
        return cinder_overrides

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

    def _get_conf_rook_ceph_backends_overrides(self, backend_overrides):
        backend_overrides[ROOK_CEPH_BACKEND_NAME] = {
            'image_volume_cache_enabled': 'True',
            'volume_backend_name': ROOK_CEPH_BACKEND_NAME,
            'volume_driver': 'cinder.volume.drivers.rbd.RBDDriver',
            'rbd_pool': 'cinder-volumes',
            'rbd_user': 'cinder',
            'rbd_ceph_conf':
                (constants.CEPH_CONF_PATH +
                 constants.SB_TYPE_CEPH_CONF_FILENAME),
        }

        ceph_uuid = get_ceph_uuid()
        if ceph_uuid:
            backend_overrides['rbd1']['rbd_secret_uuid'] = ceph_uuid
            backend_overrides[ROOK_CEPH_BACKEND_NAME]['rbd_secret_uuid'] = ceph_uuid

        return backend_overrides

    def _get_ceph_client_rook_overrides(self):
        return {
            'user_secret_name': constants.K8S_RBD_PROV_ADMIN_SECRET_NAME,
            'internal_ceph_backend': ROOK_CEPH_BACKEND_NAME,
        }

    def _get_ceph_client_overrides(self):
        # A secret is required by the chart for ceph client access. Use the
        # secret for the kube-rbd pool associated with the primary ceph tier
        ceph_backend_name = constants.SB_DEFAULT_NAMES[constants.SB_TYPE_CEPH]
        user_secret_name = storage_backend_conf.K8RbdProvisioner\
            .get_user_secret_name({'name': ceph_backend_name})
        return {
            'user_secret_name': user_secret_name,
            'internal_ceph_backend': ceph_backend_name,
        }
