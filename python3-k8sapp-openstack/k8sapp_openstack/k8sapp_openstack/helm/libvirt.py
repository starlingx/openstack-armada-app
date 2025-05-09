#
# Copyright (c) 2019-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import utils
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack
from k8sapp_openstack.utils import get_ceph_fsid
from k8sapp_openstack.utils import get_image_rook_ceph
from k8sapp_openstack.utils import is_ceph_backend_available


class LibvirtHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the libvirt chart"""

    CHART = app_constants.HELM_CHART_LIBVIRT
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_LIBVIRT

    SERVICE_NAME = app_constants.HELM_CHART_LIBVIRT

    def __init__(self, operator):
        super(LibvirtHelm, self).__init__(operator)
        self.fallback_conf = {
            'listen_addr': '0.0.0.0',
        }
        self.labels_by_hostid = {}
        self.addresses_by_hostid = {}

    def get_overrides(self, namespace=None):
        self.labels_by_hostid = self._get_host_labels()
        self.addresses_by_hostid = self._get_host_addresses()

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

        # The ceph client versions supported by baremetal and rook ceph backends
        # are not necessarily the same. Therefore, the ceph client image must be
        # dynamically configured based on the ceph backend currently deployed.
        if is_ceph_backend_available(ceph_type=constants.SB_TYPE_CEPH_ROOK):
            overrides[common.HELM_NS_OPENSTACK] =\
                self._update_image_tag_overrides(
                    overrides[common.HELM_NS_OPENSTACK],
                    ['ceph_config_helper'],
                    get_image_rook_ceph())

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides

    def _get_conf_overrides(self):
        admin_keyring = 'null'
        if is_ceph_backend_available(ceph_type=constants.SB_TYPE_CEPH_ROOK):
            admin_keyring = self._get_rook_ceph_admin_keyring()

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
                'admin_keyring': admin_keyring,
            },
            'overrides': {
                'libvirt_libvirt': {
                    'hosts': self._get_per_host_overrides()
                }
            },
        }

        ceph_uuid = get_ceph_fsid()
        if ceph_uuid:
            overrides['ceph']['cinder'] = {
                'secret_uuid': ceph_uuid,
            }

        return overrides

    def _update_host_addresses(self, host, libvirt_config):
        cluster_host_ip = self._get_cluster_host_ip(
            host, self.addresses_by_hostid)
        if cluster_host_ip is None:
            return

        libvirt_config.update({'listen_addr': cluster_host_ip})

    def _get_per_host_overrides(self):
        host_list = []
        hosts = self.dbapi.ihost_get_list()

        for host in hosts:
            host_labels = self.labels_by_hostid.get(host.id, [])
            if (host.invprovision in [constants.PROVISIONED,
                                      constants.PROVISIONING] or
                    host.ihost_action in [constants.UNLOCK_ACTION,
                                          constants.FORCE_UNLOCK_ACTION]):
                if (constants.WORKER in utils.get_personalities(host) and
                        utils.has_openstack_compute(host_labels)):

                    hostname = str(host.hostname)
                    libvirt_conf = {}
                    self._update_host_addresses(host, libvirt_conf)
                    host_nova = {
                        'name': hostname,
                        'conf': {
                            'libvirt': libvirt_conf if libvirt_conf else self.fallback_conf,
                        }
                    }
                    host_list.append(host_nova)

        return host_list
