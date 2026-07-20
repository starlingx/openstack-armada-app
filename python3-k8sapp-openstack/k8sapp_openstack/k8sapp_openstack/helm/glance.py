#
# Copyright (c) 2019-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from typing import Optional

from oslo_log import log as logging
from sysinv.common import constants
from sysinv.common import exception
from sysinv.common.storage_backend_conf import StorageBackendConfig
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack
from k8sapp_openstack.utils import _get_value_from_application
from k8sapp_openstack.utils import get_available_volume_backends
from k8sapp_openstack.utils import get_backend_protocol
from k8sapp_openstack.utils import get_backends_conf
from k8sapp_openstack.utils import get_external_service_url
from k8sapp_openstack.utils import get_image_rook_ceph
from k8sapp_openstack.utils import get_storage_backends_priority_list
from k8sapp_openstack.utils import is_ceph_backend_available
from k8sapp_openstack.utils import is_strict_backend
from k8sapp_openstack.utils import is_user_overrides_available
from k8sapp_openstack.utils import resolve_backend_storage_class

LOG = logging.getLogger(__name__)


class GlanceHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the glance chart"""

    CHART = app_constants.HELM_CHART_GLANCE
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_GLANCE

    SERVICE_NAME = app_constants.HELM_CHART_GLANCE
    SERVICE_TYPE = 'image'
    AUTH_USERS = ['glance']

    def get_overrides(self, namespace=None):
        self._rook_ceph, _ = is_ceph_backend_available(
            ceph_type=constants.SB_TYPE_CEPH_ROOK
        )
        self._priority_list = _get_value_from_application(
            chart_name=self.CHART,
            override_name=app_constants.OVERRIDE_STORAGE_PRIORITY,
            default_value=app_constants.DEFAULT_IMAGE_PRIORITY_LIST
        )
        self._migrated_pvc_priority = None  # Reset each run

        # Runtime migration: netapp-* → pvc
        self._migrate_legacy_priority_list()

        # From this point, only the new schema exists in self._priority_list
        self._available_backends = get_available_volume_backends(
            chart_name=app_constants.HELM_CHART_GLANCE,
            override_name=app_constants.OVERRIDE_STORAGE_BACKENDS
        )
        # Adding Cinder as it's always available in any openstack deployment and
        # can be used as Glance backend
        self._available_backends[app_constants.GLANCE_BACKEND_CINDER] = \
            app_constants.GLANCE_BACKEND_CINDER
        self._available_netapp_backends = [
            be for be in self._available_backends
            if be.startswith('netapp') and self._available_backends[be]
        ]
        self._ceph_enabled = bool(
            self._available_backends.get(app_constants.CEPH_BACKEND_NAME, False)
        )
        self._netapp_enabled = any(self._available_netapp_backends)
        self._backend, self._storage_class = self._get_storage()
        self._image_store = app_constants.GLANCE_BACKEND_TO_IMAGE_STORE[
            self._backend
        ]

        if self._backend == app_constants.GLANCE_BACKEND_CINDER:
            cinder_default = self._get_cinder_default_backend()
            self._cinder_default_backend = cinder_default
            self._cinder_uses_ceph = cinder_default in [
                app_constants.CEPH_BACKEND_NAME,
                app_constants.CEPH_ROOK_BACKEND_NAME
            ]
            if self._cinder_uses_ceph:
                cinder_ceph_type = self._get_cinder_ceph_type(cinder_default)
                self._ceph_enabled = True
                self._rook_ceph = (
                    self._rook_ceph or
                    (cinder_ceph_type == constants.SB_TYPE_CEPH_ROOK)
                )
        else:
            self._cinder_default_backend = None
            self._cinder_uses_ceph = False

        LOG.info(f"Glance available backends: {self._available_backends}")
        LOG.info(f"Glance available NetApp backends: {self._available_netapp_backends}")
        LOG.info(f"Glance priority list: {self._priority_list}")
        LOG.info(f"Glance Ceph enabled: {self._ceph_enabled}")
        LOG.info(f"Glance NetApp enabled: {self._netapp_enabled}")
        LOG.info(f"Glance backend: {self._backend}")
        if self._backend == app_constants.GLANCE_BACKEND_PVC:
            LOG.info(f"Glance storage class: {self._storage_class}")
        if self._backend == app_constants.GLANCE_BACKEND_CINDER:
            LOG.info(f"Glance Cinder uses Ceph: {self._cinder_uses_ceph}")

        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': self._get_pod_overrides(),
                'endpoints': self._get_endpoints_overrides(),
                'storage': self._backend,
                'conf': self._get_conf_overrides(),
                'bootstrap': self._get_bootstrap_overrides(),
                'ceph_client': self._get_ceph_client_overrides(),
            }
        }

        if self._backend == app_constants.GLANCE_BACKEND_PVC:
            if not self._storage_class:
                LOG.error(
                    f"The {app_constants.HELM_CHART_GLANCE} chart resolved to "
                    f"the \"{app_constants.GLANCE_BACKEND_PVC}\" image store "
                    f"but no Kubernetes StorageClass could be resolved from "
                    f"the configured priority list {self._priority_list}. "
                    f"Update storage_conf.volume_storage_class_priority to "
                    f"reference a backend with a valid k8s_storage_class."
                )

            volume_size = _get_value_from_application(
                chart_name=self.CHART,
                override_name=app_constants.OVERRIDE_GLANCE_PVC_VOLUME_SIZE,
                default_value=app_constants.DEFAULT_GLANCE_PVC_VOLUME_SIZE,
            )
            access_modes = self._get_pvc_access_modes()
            overrides[common.HELM_NS_OPENSTACK]['volume'] = {
                'class_name': self._storage_class,
                'size': volume_size,
                'accessModes': access_modes,
            }

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
                    ['glance_storage_init'],
                    get_image_rook_ceph())

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides

    def _get_pvc_access_modes(self):
        """Get PVC access modes while preserving legacy NFS semantics.

        The 26.03 NetApp NFS backend always rendered ReadWriteMany. A legacy
        priority migrated to the generic PVC schema has no access_modes
        override, so using the new ReadWriteOnce default would attempt an
        immutable change to an existing claim during application-update.

        Only the migration path inherits ReadWriteMany. New generic PVC
        configurations retain the ReadWriteOnce default, and an explicit
        operator access_modes override always takes precedence.
        """
        default_access_modes = (
            app_constants.DEFAULT_GLANCE_PVC_VOLUME_ACCESS_MODES
        )
        netapp_nfs_storage_class = getattr(
            self, "_available_backends", {}
        ).get(
            app_constants.NETAPP_NFS_BACKEND_NAME
        )
        if (getattr(self, "_migrated_pvc_priority", None) and
                netapp_nfs_storage_class and
                self._storage_class == netapp_nfs_storage_class):
            default_access_modes = ["ReadWriteMany"]

        return _get_value_from_application(
            chart_name=self.CHART,
            override_name=(
                app_constants.OVERRIDE_GLANCE_PVC_VOLUME_ACCESS_MODES
            ),
            default_value=default_access_modes,
        )

    def _get_pod_overrides(self):
        if self._backend == app_constants.GLANCE_BACKEND_PVC:
            # Access modes drive replica count
            access_modes = self._get_pvc_access_modes()
            if "ReadWriteMany" not in access_modes:
                replicas_count = 1
            else:
                replicas_count = self._num_provisioned_controllers()
        else:
            replicas_count = self._num_provisioned_controllers()

        overrides = {
            'replicas': {
                'api': replicas_count,
            },
        }

        if self._image_store == app_constants.GLANCE_IMAGE_STORE_CINDER:
            # Drive pod security context from the Cinder default backend
            # protocol via the shared protocol-to-pod-config helper.
            protocol = get_backend_protocol(self._cinder_default_backend)
            if protocol is None:
                LOG.warning(
                    f"Could not resolve protocol for backend "
                    f"'{self._cinder_default_backend}', skipping "
                    f"hostNetwork config"
                )
            else:
                pod_config = self._get_protocol_pod_config({protocol})
                if pod_config['use_host_network']:
                    overrides['security_context'] = {
                        'glance': {
                            'container': {
                                'glance_api': {
                                    'readOnlyRootFilesystem': False,
                                    'privileged': True,
                                    'allowPrivilegeEscalation': True,
                                },
                            },
                        },
                    }
                    overrides['useHostNetwork'] = {
                        'api': True
                    }

        return overrides

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
        if not ceph_backend and not self._rook_ceph and not self._cinder_uses_ceph:
            rbd_store_pool = ""
            rbd_store_user = ""
            replication = 1
        else:
            rbd_store_pool = app_constants.CEPH_POOL_IMAGES_NAME
            rbd_store_user = app_constants.CEPH_RBD_POOL_USER_GLANCE
            target = constants.SB_TYPE_CEPH_ROOK if self._rook_ceph\
                else constants.SB_TYPE_CEPH
            backend = StorageBackendConfig.get_configured_backend(self.dbapi,
                                                                  target)
            replication, _ = StorageBackendConfig.get_ceph_pool_replication(
                api=self.dbapi,
                ceph_backend=backend)

        if not self._rook_ceph:
            # Only the primary Ceph tier is used for the glance images pool
            rule_name = "{0}{1}{2}".format(
                constants.SB_TIER_DEFAULT_NAMES[
                    constants.SB_TIER_TYPE_CEPH],
                constants.CEPH_CRUSH_TIER_SUFFIX,
                "-ruleset").replace('-', '_')
        else:
            rule_name = app_constants.CEPH_ROOK_POLL_CRUSH_RULE

        if self._rook_ceph:
            chunk_size = app_constants.ROOK_CEPH_POOL_GLANCE_CHUNK_SIZE
        else:
            chunk_size = self._estimate_ceph_pool_pg_num(self.dbapi.istor_get_all())

        rbd_conf = {
            'chunk_size': min(chunk_size, app_constants.CEPH_POOL_IMAGES_CHUNK_SIZE),
            'rbd_store_pool': rbd_store_pool,
            'rbd_store_user': rbd_store_user,
            'rbd_store_replication': replication,
            'rbd_store_crush_rule': rule_name,
        }

        conf = {
            'cinder': {
                'cinder_uses_ceph': self._cinder_uses_ceph
            },
            'glance': {
                'DEFAULT': {
                    'graceful_shutdown': True,
                    'show_image_direct_url': False,
                    'show_multiple_locations': False,
                    'enabled_backends': f"{self._image_store}:{self._image_store}"
                },
                'cinder': {
                    'cinder_api_insecure': not self._is_openstack_https_ready(self.SERVICE_NAME),
                    'cinder_catalog_info': app_constants.GLANCE_CINDER_CATALOG_INFO,
                    'cinder_store_auth_address': self._get_service_public_endpoint(
                        app_constants.HELM_CHART_KEYSTONE,
                        path="v3"
                    ),
                    'cinder_store_user_name': self._get_admin_user_name(),
                    'cinder_store_password': self._get_admin_password(),
                    'cinder_store_project_name': self._get_admin_project_name(),
                    'cinder_store_user_domain_name': self._get_admin_user_domain(),
                    'cinder_store_project_domain_name': self._get_admin_project_domain(),
                },
                'file': {
                    'filesystem_store_datadir': constants.GLANCE_IMAGE_PATH,
                },
                'rbd': rbd_conf,
                'glance_store': {
                    'default_backend': self._image_store
                }
            }
        }

        if ceph_backend or (self._cinder_uses_ceph and not self._rook_ceph):
            conf['ceph'] = self._get_ceph_overrides()
        elif self._rook_ceph:
            conf['ceph'] = {
                'admin_keyring': self._get_rook_ceph_admin_keyring()
            }

        if self._is_openstack_https_ready(self.SERVICE_NAME):
            # Configure the proper Keystone URL for the certificate in use
            external_keystone_url = get_external_service_url(self.dbapi, 'keystone', True)
            if external_keystone_url:
                keystone_versioned_url = f"{external_keystone_url}/{app_constants.KEYSTONE_CURRENT_VERSION}"
                conf = self._update_overrides(conf, {
                    'glance': {
                        'cinder': {
                            'cinder_store_auth_address': keystone_versioned_url,
                        },
                    },
                })

            conf = self._update_overrides(conf, {
                'glance': {
                    'keystone_authtoken': {
                        'cafile': self.get_ca_file(),
                    },
                    'glance_store': {
                        'https_ca_certificates_file': self.get_ca_file(),
                    },
                    'cinder': {
                        'cinder_ca_certificates_file': self.get_ca_file(),
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

    def _migrate_legacy_priority_list(self):
        """Runtime migration: rewrite netapp-* entries into the generic
        pvc backend.

        26.03 schema:
            volume_storage_class_priority:
                [ceph, netapp-nfs, netapp-iscsi, netapp-fc, cinder]

        26.09 schema:
            volume_storage_class_priority: [ceph, pvc, cinder]
            storage_conf.pvc.storage_class_priority:
                [netapp-nfs, netapp-iscsi, netapp-fc]

        When legacy netapp-* entries are detected in self._priority_list,
        they are replaced with a single 'pvc' meta-entry (at the position
        of the first one). The extracted entries become the PVC
        sub-priority if the operator hasn't explicitly configured
        storage_conf.pvc.storage_class_priority.

        Deprecated in 26.09. Planned removal in 27.03.
        """
        legacy_entries = [
            p for p in self._priority_list
            if p in app_constants.GLANCE_LEGACY_NETAPP_BACKENDS
        ]
        if not legacy_entries:
            return

        # Replace netapp-* entries with a single 'pvc' entry
        migrated = []
        pvc_inserted = False
        for p in self._priority_list:
            if p in app_constants.GLANCE_LEGACY_NETAPP_BACKENDS:
                if not pvc_inserted:
                    migrated.append(app_constants.GLANCE_BACKEND_PVC)
                    pvc_inserted = True
                # Drop individual netapp-* entry
            else:
                migrated.append(p)
        self._priority_list = migrated

        # If operator hasn't explicitly set pvc.storage_class_priority,
        # use the extracted legacy entries as the PVC sub-priority
        has_explicit_pvc_priority = is_user_overrides_available(
            chart_name=app_constants.HELM_CHART_GLANCE,
            override_name=(
                app_constants.OVERRIDE_GLANCE_PVC_STORAGE_PRIORITY
            ),
        )
        if not has_explicit_pvc_priority:
            self._migrated_pvc_priority = legacy_entries

        LOG.info(
            "Glance legacy migration: rewrote %s into generic pvc "
            "backend. Priority list is now: %s",
            legacy_entries, self._priority_list
        )

    def _resolve_glance_pvc_storage_class(self) -> Optional[str]:
        """Resolve the StorageClass for the Glance PVC backend.

        Reads storage_conf.pvc.storage_class_priority (Glance-owned list)
        and resolves each entry to its k8s_storage_class via
        get_available_volume_backends(), keyed by backend name.

        When runtime migration has populated self._migrated_pvc_priority
        (legacy netapp-* entries detected in the top-level priority list),
        that migrated list is used instead of reading from user overrides.

        Storage class resolution follows this priority order:
        1. Strict backends returned by get_available_volume_backends()
           (Ceph, NetApp NFS/iSCSI/FC).
        2. ESB backends from the Cinder chart's backends_conf, identified
           by their k8s_storage_class field (skipped when set to 'none').

        Delegates to the shared resolve_backend_storage_class() utility to
        keep resolution logic consistent with Nova and the pre-apply
        semantic checks.

        Returns:
            str | None: The resolved StorageClass name, or None if no
                backend in the priority list resolves to an available
                StorageClass.
        """
        pvc_available_backends = get_available_volume_backends(
            chart_name=app_constants.HELM_CHART_GLANCE,
            override_name=app_constants.OVERRIDE_GLANCE_PVC_STORAGE_BACKENDS,
        )

        # Use migrated priority if available (legacy schema detected),
        # otherwise read from user overrides / defaults
        if self._migrated_pvc_priority:
            pvc_priority_list = self._migrated_pvc_priority
        else:
            pvc_priority_list = get_storage_backends_priority_list(
                app_constants.HELM_CHART_GLANCE,
                app_constants.OVERRIDE_GLANCE_PVC_STORAGE_PRIORITY,
                app_constants.DEFAULT_GLANCE_PVC_PRIORITY_LIST,
            )

        cinder_backends_conf = get_backends_conf()

        return resolve_backend_storage_class(
            priority_list=pvc_priority_list,
            available_backends=pvc_available_backends,
            backends_conf=cinder_backends_conf,
        )

    def _get_storage(self) -> tuple[str, str]:
        """
        Get the glance backend and storage class based on available backends
        and their priorities.

        After runtime migration (_migrate_legacy_priority_list), the priority
        list only contains canonical entries: 'ceph', 'pvc', 'cinder'.
        The generic 'pvc' entry triggers secondary resolution via
        storage_conf.pvc.storage_class_priority (Glance-owned list).

        Returns:
            tuple[str, str]: A tuple containing:
                - The glance backend name.
                - The corresponding storage class name (empty for non-PVC).

        Example:
            >>> backend, storage_class = self._get_storage()
            >>> print(backend, storage_class)
            pvc general
            >>> backend, storage_class = self._get_storage()
            >>> print(backend, storage_class)
            rbd
            >>> backend, storage_class = self._get_storage()
            >>> print(backend, storage_class)
            cinder
        """
        backend = app_constants.GLANCE_DEFAULT_BACKEND
        storage_class = ""
        for priority in self._priority_list:
            if priority == app_constants.GLANCE_BACKEND_PVC:
                # Generic PVC backend: resolve via Glance-owned
                # storage_conf.pvc.storage_class_priority.
                resolved_class = self._resolve_glance_pvc_storage_class()
                if resolved_class:
                    backend = app_constants.GLANCE_BACKEND_PVC
                    storage_class = resolved_class
                    break
                # Resolution failed. If 'pvc' is the only entry (no
                # fallback declared), select it anyway so that
                # get_overrides() logs an error and the pre-apply
                # semantic check blocks deployment with a clear message.
                # If other entries follow, honor the priority-list
                # fallback semantics — the operator declared alternatives.
                if len(self._priority_list) == 1:
                    backend = app_constants.GLANCE_BACKEND_PVC
                    break
                # Otherwise, fall through to the next priority entry.
            elif self._available_backends.get(priority, ""):
                backend = app_constants.VOLUME_BACKEND_TO_GLANCE_BACKEND[
                    priority
                ]
                break
        return backend, storage_class

    def _get_cinder_default_backend(self) -> str:
        """
        Get the default storage backend configured for Cinder.
        The default Cinder backend is the one enabled with the highest priority
        in the Cinder configuration.

        Returns:
            str: default Cinder backend name or None if not found.

        Example:
            >>> cinder_default = self._get_cinder_default_backend()
        """
        cinder_priority_list = get_storage_backends_priority_list(
            app_constants.HELM_CHART_CINDER
        )
        cinder_available_backends = get_available_volume_backends(
            chart_name=app_constants.HELM_CHART_CINDER,
            override_name=app_constants.OVERRIDE_STORAGE_BACKENDS
        )
        for priority in cinder_priority_list:
            value = cinder_available_backends.get(priority)
            # Strict backends need a non-empty storage class to be available;
            # ESB backends are valid even with k8s_storage_class: none (value="")
            if value or (value == "" and not is_strict_backend(priority)):
                return priority
        LOG.error("No available storage backends found for Cinder.")
        return None

    def _get_cinder_ceph_type(self, cinder_backend: str) -> str:
        """
        Get the Ceph type used by Cinder backend.

        Args:
            cinder_backend: The Cinder backend name.

        Returns:
            str: Ceph type constant (SB_TYPE_CEPH_ROOK or SB_TYPE_CEPH).

        Example:
            >>> ceph_type = self._get_cinder_ceph_type('ceph-rook')
        """
        if cinder_backend == app_constants.CEPH_ROOK_BACKEND_NAME:
            return constants.SB_TYPE_CEPH_ROOK
        return constants.SB_TYPE_CEPH

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
