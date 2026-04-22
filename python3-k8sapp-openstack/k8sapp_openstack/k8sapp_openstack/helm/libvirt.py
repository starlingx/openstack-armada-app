#
# Copyright (c) 2019-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging
from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack
from k8sapp_openstack.utils import get_ceph_fsid
from k8sapp_openstack.utils import get_image_rook_ceph
from k8sapp_openstack.utils import is_ceph_backend_available

LOG = logging.getLogger(__name__)


class LibvirtHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the libvirt chart"""

    CHART = app_constants.HELM_CHART_LIBVIRT
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_LIBVIRT

    SERVICE_NAME = app_constants.HELM_CHART_LIBVIRT

    def __init__(self, operator):
        super(LibvirtHelm, self).__init__(operator)

    def get_overrides(self, namespace=None):
        nova_shares = self._get_instances_nfs_shares_config()

        pvc_resolution = self._resolve_nova_pvc_overrides()

        cinder_backends = self._get_cinder_volumes_backends()
        self._ceph_enabled = app_constants.CEPH_BACKEND_NAME in cinder_backends
        self._rook_ceph = False
        if self._ceph_enabled:
            self._rook_ceph, _ = is_ceph_backend_available(
                ceph_type=constants.SB_TYPE_CEPH_ROOK)

        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': {
                    'mounts': {
                        'libvirt': {
                            'libvirt': self._get_mount_uefi_overrides()
                        }
                    }
                },
                'conf': self._get_conf_overrides(),
            }
        }

        if pvc_resolution:
            overrides[common.HELM_NS_OPENSTACK] = self._update_overrides(
                overrides[common.HELM_NS_OPENSTACK],
                {
                    'storage_conf': {
                        'pvc': {
                            'enabled': pvc_resolution.get('enabled', False),
                            'name': pvc_resolution.get('name', app_constants.DEFAULT_NOVA_PVC_NAME),
                            'instances_path': pvc_resolution.get(
                                'instances_path',
                                app_constants.DEFAULT_NOVA_PVC_INSTANCES_PATH,
                            ),
                        }
                    }
                }
            )

        # The ceph client versions supported by baremetal and rook ceph backends
        # are not necessarily the same. Therefore, the ceph client image must be
        # dynamically configured based on the ceph backend currently deployed.
        if self._rook_ceph:
            overrides[common.HELM_NS_OPENSTACK] =\
                self._update_image_tag_overrides(
                    overrides[common.HELM_NS_OPENSTACK],
                    ['ceph_config_helper'],
                    get_image_rook_ceph())

        if nova_shares.get('enabled'):
            overrides[common.HELM_NS_OPENSTACK].update({
                'storage_conf': {
                    'nfs_shares': {
                        'enabled': nova_shares['enabled'],
                        'server': nova_shares['server'],
                        'path': nova_shares['path'],
                        'instances_path': nova_shares['instances_path'],
                    }
                }
            })

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides

    def _get_conf_overrides(self):
        cinder_overrides = {}

        LOG.info(f"Libvirt Ceph enabled: {self._ceph_enabled} ")
        admin_keyring = 'null'
        if self._ceph_enabled:
            if self._rook_ceph:
                admin_keyring = self._get_rook_ceph_admin_keyring()

                if admin_keyring == 'null':
                    LOG.error(
                        f"Libvirt: Rook Ceph admin keyring not available. "
                        f"The Kubernetes secret "
                        f"'{constants.K8S_RBD_PROV_ADMIN_SECRET_NAME}' in "
                        f"namespace '{app_constants.HELM_NS_ROOK_CEPH}' could "
                        f"not be read. Ceph will not be properly configured "
                        f"on compute nodes.")

        else:
            cinder_overrides = {
                'external_ceph': {
                    'enabled': self._ceph_enabled
                }
            }
            cinder_overrides['keyring'] = 'null'

        overrides = {
            'qemu': {
                'user': "root",
                'group': "root",
                'cgroup_controllers': [
                    "cpu", "cpuacct", "cpuset",
                    "freezer", "net_cls", "perf_event"
                ],
                'namespaces': [],
                'clear_emulator_capabilities': 0
            },
            'ceph': {
                'enabled': self._ceph_enabled,
                'admin_keyring': admin_keyring,
                'cinder': cinder_overrides,
            },
        }

        ceph_uuid = get_ceph_fsid()
        if ceph_uuid:
            overrides['ceph']['cinder'] = {
                'secret_uuid': ceph_uuid,
            }

        return overrides
