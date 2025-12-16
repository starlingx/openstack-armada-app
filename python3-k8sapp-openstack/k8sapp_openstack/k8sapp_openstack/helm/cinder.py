#
# Copyright (c) 2019-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging
from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import storage_backend_conf
from sysinv.helm import common
from tsconfig import tsconfig as tsc

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack
from k8sapp_openstack.utils import discover_netapp_configs
from k8sapp_openstack.utils import discover_netapp_credentials
from k8sapp_openstack.utils import get_available_volume_backends
from k8sapp_openstack.utils import get_ceph_fsid
from k8sapp_openstack.utils import get_image_rook_ceph
from k8sapp_openstack.utils import get_storage_backends_priority_list
from k8sapp_openstack.utils import is_ceph_backend_available

LOG = logging.getLogger(__name__)


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
        self.VOLUME_PRIORITY_LIST = get_storage_backends_priority_list(self.CHART)
        self._rook_ceph = False
        ceph_overrides = dict()
        ceph_client_overrides = dict()
        self.available_backends = get_available_volume_backends()
        self.available_netapp_backends = [
            be for be in self.available_backends
            if be.startswith('netapp') and self.available_backends[be]
        ]
        self._ceph_enabled = bool(
            self.available_backends.get(app_constants.CEPH_BACKEND_NAME, False)
        )
        self._netapp_nfs_enabled = bool(
            self.available_backends.get(app_constants.NETAPP_NFS_BACKEND_NAME, False)
        )
        self._netapp_iscsi_enabled = bool(
            self.available_backends.get(app_constants.NETAPP_ISCSI_BACKEND_NAME, False)
        )
        self._netapp_fc_enabled = bool(
            self.available_backends.get(app_constants.NETAPP_FC_BACKEND_NAME, False)
        )
        LOG.info(f"Cinder available backends: {self.available_backends}")
        LOG.info(f"Cinder available NetApp backends: {self.available_backends}")
        LOG.info(f"Cinder volume priority list: {self.VOLUME_PRIORITY_LIST}")
        LOG.info(f"Cinder Ceph enabled: {self._ceph_enabled}")
        LOG.info(f"Cinder NetApp NFS enabled: {self._netapp_nfs_enabled}")
        LOG.info(f"Cinder NetApp iSCSI enabled: {self._netapp_iscsi_enabled}")
        LOG.info(f"Cinder NetApp FC enabled: {self._netapp_fc_enabled}")

        # Check if ceph is enabled by the user or if there are no user overrides (default)
        if self._ceph_enabled:
            self._rook_ceph, _ = is_ceph_backend_available(ceph_type=constants.SB_TYPE_CEPH_ROOK)
            # Ceph and Rook Ceph are mutually exclusive, so it's either one or the other
            if self._rook_ceph:
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
        cinder_backup_privileged = False
        if any(self.available_netapp_backends):
            # If NetApp is using NFS, the cinder-volume pod cannot have a readOnly filesystem,
            # as the NFS will be mounted into the pod during initialization
            cinder_volume_read_only_filesystem = self._netapp_nfs_enabled

            # For NetApp iSCSI the backup container needs to run in privileged
            # mode [1][2]
            # [1] https://review.opendev.org/c/openstack/tripleo-heat-templates/+/538272
            # [2] https://review.opendev.org/c/openstack/openstack-helm/+/770008
            cinder_backup_privileged = self._netapp_iscsi_enabled

            cinder_overrides = self._get_conf_netapp_cinder_overrides(cinder_overrides)
            backend_overrides = self._get_conf_netapp_backends_overrides(backend_overrides)

        # Setting default volume type based on the priority list.
        # It will be the first available backend following the priority order.
        default_volume_type = app_constants.BACKEND_DEFAULT_BACKEND_NAME
        for priority in self.VOLUME_PRIORITY_LIST:
            if self.available_backends.get(priority, ""):
                default_volume_type = priority
                break
        if default_volume_type != "ceph":   # Only set if not ceph, as ceph is handled
                                            # separately by _get_conf_ceph_cinder_overrides
                                            # and _get_conf_rook_ceph_cinder_overrides
            cinder_overrides['DEFAULT']['default_volume_type'] = default_volume_type

        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': {
                    # Following the same approach as the OSH community did for
                    # Pure Storage integration [1], we use host network for
                    # to support Netapp iSCSI.
                    # [1] https://review.opendev.org/c/openstack/openstack-helm/+/770008
                    # [2] https://review.opendev.org/c/openstack/openstack-helm/+/709378
                    'useHostNetwork': {
                        'volume': self._netapp_iscsi_enabled,
                        'backup': self._netapp_iscsi_enabled
                    },
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
                        },
                        'cinder_backup': {
                            'container': {
                                'cinder_backup': {
                                    'privileged': cinder_backup_privileged
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

        # Remove unused Ceph overrides
        if not self._ceph_enabled:
            overrides[common.HELM_NS_OPENSTACK]['conf'].pop('ceph', 0)
            overrides[common.HELM_NS_OPENSTACK].pop('ceph_client', 0)

        if self._netapp_nfs_enabled:
            overrides[common.HELM_NS_OPENSTACK] = self._update_overrides(
                overrides[common.HELM_NS_OPENSTACK],
                {
                    'conf': {
                        'nfs_shares': app_constants.NETAPP_DEFAULT_NFS_SHARES,
                    }
                }
            )

        if self._is_openstack_https_ready(self.SERVICE_NAME):
            overrides[common.HELM_NS_OPENSTACK] = \
                self._enable_certificates(overrides[common.HELM_NS_OPENSTACK])

        # The ceph client versions supported by baremetal and rook ceph backends
        # are not necessarily the same. Therefore, the ceph client image must be
        # dynamically configured based on the ceph backend currently deployed.
        if self._rook_ceph:
            overrides[common.HELM_NS_OPENSTACK] =\
                self._update_image_tag_overrides(
                    overrides[common.HELM_NS_OPENSTACK],
                    ['cinder_backup_storage_init', 'cinder_storage_init'],
                    get_image_rook_ceph())

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

        # Add NetApp backends to Cinder enabled_backends list, ensuring no duplicates
        existing_backends = cinder_overrides['DEFAULT'].get('enabled_backends', '').split(',')
        backends_list = list(filter(None, set(existing_backends + self.available_netapp_backends)))
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
                'rbd_user': app_constants.CEPH_RBD_POOL_USER_CINDER,
                'rbd_ceph_conf':
                    (constants.CEPH_CONF_PATH +
                     constants.SB_TYPE_CEPH_CONF_FILENAME),
            }

            ceph_uuid = get_ceph_fsid()
            if ceph_uuid:
                backend_overrides[bk_name]['rbd_secret_uuid'] = ceph_uuid

        return backend_overrides

    def _get_conf_netapp_backends_overrides(self, backend_overrides):
        nfs_constant_configs = {
            'nfs_shares_config': app_constants.NFS_SHARES_CONFIG,
            'nfs_mount_options': app_constants.NFS_MOUNT_OPTIONS,
        }
        for backend in self.available_netapp_backends:
            netaapp_credentials = discover_netapp_credentials(backend)
            if not netaapp_credentials:
                LOG.warning(f"No NetApp credentials found for backend {backend}. "
                            "The user needs to set them through user overrides")
            netapp_storage_configs = discover_netapp_configs(backend)
            if not netapp_storage_configs:
                LOG.warning(f"No NetApp storage configs found for backend {backend}. "
                            "The user needs to set them through user overrides")
            backend_overrides[backend] = {
                'volume_backend_name': backend,
            } | netaapp_credentials | netapp_storage_configs
            if backend == app_constants.NETAPP_NFS_BACKEND_NAME:
                backend_overrides[backend] |= nfs_constant_configs

        # TODO: For full FC support, we'll need to include Zoning config, as it's described
        # in the documentation
        # https://netapp-openstack-dev.github.io/openstack-docs/wallaby/cinder/configuration/cinder_config_files/unified_driver_ontap/section_cinder-conf-fcp.html
        # https://netapp-openstack-dev.github.io/openstack-docs/wallaby/cinder/configuration/cinder_config_files/section_fibre-channel.html

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
        # We don't use the chart's default backends.
        return dict()

    def _get_conf_rook_ceph_cinder_overrides(self, cinder_overrides):
        # Ensure 'DEFAULT' key exists in cinder_overrides and update it
        cinder_overrides.setdefault('DEFAULT', {})

        # Retrieve the existing enabled_backends value, or set it to an empty string if not present
        existing_backends = cinder_overrides['DEFAULT'].get('enabled_backends', '')

        # Append 'ceph-rook-store' if it's not already in the enabled_backends list
        backends_list = existing_backends.split(',') if existing_backends else []
        if app_constants.CEPH_ROOK_BACKEND_NAME not in backends_list:
            backends_list.append(app_constants.CEPH_ROOK_BACKEND_NAME)

        # Update Cinder overrides
        cinder_overrides['DEFAULT'].update({
            'enabled_backends': ','.join(backends_list),
            # If the user doesn't want Ceph Rook to be the default backend,
            # he can pass a Helm override changing this value, which will
            # override this value
            'default_volume_type': app_constants.CEPH_ROOK_BACKEND_NAME,
        })
        return cinder_overrides

    def _get_conf_rook_ceph_overrides(self):
        rook_backend = storage_backend_conf.StorageBackendConfig\
            .get_configured_backend(self.dbapi, constants.SB_TYPE_CEPH_ROOK)
        if not rook_backend:
            LOG.error("No rook ceph backend configured")
            return {}
        replication, _ = storage_backend_conf\
            .StorageBackendConfig\
            .get_ceph_pool_replication(self.dbapi, ceph_backend=rook_backend)
        pools = {
            f'{app_constants.CEPH_POOL_VOLUMES_NAME}': {
                'app_name': app_constants.CEPH_POOL_VOLUMES_APP_NAME,
                'chunk_size': app_constants.ROOK_CEPH_POOL_CINDER_VOLUME_CHUNK_SIZE,
                'crush_rule': app_constants.CEPH_ROOK_POLL_CRUSH_RULE,
                'replication': replication,
            },
            f'{app_constants.CEPH_POOL_BACKUP_NAME}': {
                'app_name': app_constants.CEPH_POOL_BACKUP_APP_NAME,
                'chunk_size': app_constants.ROOK_CEPH_POOL_CINDER_BACKUP_CHUNK_SIZE,
                'crush_rule': app_constants.CEPH_ROOK_POLL_CRUSH_RULE,
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
        backend_overrides[app_constants.CEPH_ROOK_BACKEND_NAME] = {
            'image_volume_cache_enabled': 'True',
            'volume_backend_name': app_constants.CEPH_ROOK_BACKEND_NAME,
            'volume_driver': 'cinder.volume.drivers.rbd.RBDDriver',
            'rbd_pool': app_constants.CEPH_POOL_VOLUMES_NAME,
            'rbd_user': app_constants.CEPH_RBD_POOL_USER_CINDER,
            'rbd_ceph_conf':
                (constants.CEPH_CONF_PATH +
                 constants.SB_TYPE_CEPH_CONF_FILENAME),
        }

        ceph_uuid = get_ceph_fsid()
        if ceph_uuid:
            backend_overrides[app_constants.CEPH_ROOK_BACKEND_NAME]['rbd_secret_uuid'] = ceph_uuid

        return backend_overrides

    def _get_ceph_client_rook_overrides(self):
        return {
            'user_secret_name': constants.K8S_RBD_PROV_ADMIN_SECRET_NAME,
            'internal_ceph_backend': app_constants.CEPH_ROOK_BACKEND_NAME,
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
