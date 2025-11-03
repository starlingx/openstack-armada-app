#
# Copyright (c) 2019-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import constants


HELM_APP_OPENSTACK = constants.HELM_APP_OPENSTACK
HELM_NS_OPENSTACK = 'openstack'

HELM_OVERRIDE_GROUP_SYSTEM = 'system_overrides'
HELM_OVERRIDE_GROUP_USER = 'user_overrides'

# Helm: Supported charts:
# These values match the names in the chart package's Chart.yaml
HELM_CHART_AODH = 'aodh'
HELM_CHART_BARBICAN = 'barbican'
HELM_CHART_CEILOMETER = 'ceilometer'
HELM_CHART_CINDER = 'cinder'
HELM_CHART_CLIENTS = 'clients'
HELM_CHART_FM_REST_API = 'fm-rest-api'
HELM_CHART_GARBD = 'garbd'
HELM_CHART_GLANCE = 'glance'
HELM_CHART_GNOCCHI = 'gnocchi'
HELM_CHART_HEAT = 'heat'
HELM_CHART_HELM_TOOLKIT = 'openstack-helm-toolkit'
HELM_CHART_HORIZON = 'horizon'
HELM_CHART_INGRESS = 'ingress-nginx-openstack'
HELM_CHART_IRONIC = 'ironic'
HELM_CHART_KEYSTONE = 'keystone'
HELM_CHART_KEYSTONE_API_PROXY = 'keystone-api-proxy'
HELM_CHART_LIBVIRT = 'libvirt'
HELM_CHART_MAGNUM = 'magnum'
HELM_CHART_MARIADB = 'mariadb'
HELM_CHART_MEMCACHED = 'memcached'
HELM_CHART_NEUTRON = 'neutron'
HELM_CHART_NGINX_PORTS_CONTROL = "nginx-ports-control"
HELM_CHART_NOVA = 'nova'
HELM_CHART_NOVA_API_PROXY = 'nova-api-proxy'
HELM_CHART_PCI_IRQ_AFFINITY_AGENT = 'pci-irq-affinity-agent'
HELM_CHART_OPENVSWITCH = 'openvswitch'
HELM_CHART_PLACEMENT = 'placement'
HELM_CHART_RABBITMQ = 'rabbitmq'
HELM_CHART_SWIFT = 'ceph-rgw'
HELM_CHART_DCDBSYNC = 'dcdbsync'

# Helm Release constants
FLUXCD_HELMRELEASE_AODH = 'aodh'
FLUXCD_HELMRELEASE_BARBICAN = 'barbican'
FLUXCD_HELMRELEASE_CEILOMETER = 'ceilometer'
FLUXCD_HELMRELEASE_CINDER = 'cinder'
FLUXCD_HELMRELEASE_CLIENTS = 'clients'
FLUXCD_HELMRELEASE_FM_REST_API = 'fm-rest-api'
FLUXCD_HELMRELEASE_GARBD = 'garbd'
FLUXCD_HELMRELEASE_GLANCE = 'glance'
FLUXCD_HELMRELEASE_GNOCCHI = 'gnocchi'
FLUXCD_HELMRELEASE_HEAT = 'heat'
FLUXCD_HELMRELEASE_HELM_TOOLKIT = 'openstack-helm-toolkit'
FLUXCD_HELMRELEASE_HORIZON = 'horizon'
FLUXCD_HELMRELEASE_INGRESS = 'ingress-nginx-openstack'
FLUXCD_HELMRELEASE_IRONIC = 'ironic'
FLUXCD_HELMRELEASE_KEYSTONE = 'keystone'
FLUXCD_HELMRELEASE_KEYSTONE_API_PROXY = 'keystone-api-proxy'
FLUXCD_HELMRELEASE_LIBVIRT = 'libvirt'
FLUXCD_HELMRELEASE_MAGNUM = 'magnum'
FLUXCD_HELMRELEASE_MARIADB = 'mariadb'
FLUXCD_HELMRELEASE_MEMCACHED = 'memcached'
FLUXCD_HELMRELEASE_NEUTRON = 'neutron'
FLUXCD_HELMRELEASE_NGINX_PORTS_CONTROL = "nginx-ports-control"
FLUXCD_HELMRELEASE_NOVA = 'nova'
FLUXCD_HELMRELEASE_NOVA_API_PROXY = 'nova-api-proxy'
FLUXCD_HELMRELEASE_PCI_IRQ_AFFINITY_AGENT = 'pci-irq-affinity-agent'
FLUXCD_HELMRELEASE_OPENVSWITCH = 'openvswitch'
FLUXCD_HELMRELEASE_PLACEMENT = 'placement'
FLUXCD_HELMRELEASE_RABBITMQ = 'rabbitmq'
FLUXCD_HELMRELEASE_SWIFT = 'ceph-rgw'
FLUXCD_HELMRELEASE_DCDBSYNC = 'dcdbsync'

# Nova PCI Alias types and names
# NOTE: Generic GPU and QAT definitions reside in sysinv/common/constants.py
# and are required by sysinv-agent and puppet for PCI devices inventory.
NOVA_PCI_ALIAS_DEVICE_TYPE_PCI = "type-PCI"
NOVA_PCI_ALIAS_DEVICE_TYPE_PF = "type-PF"
NOVA_PCI_ALIAS_DEVICE_TYPE_VF = "type-VF"
NOVA_PCI_ALIAS_GPU_MATROX_VENDOR = "102b"
NOVA_PCI_ALIAS_GPU_MATROX_G200E_DEVICE = "0522"
NOVA_PCI_ALIAS_GPU_MATROX_G200E_NAME = "matrox-g200e"
NOVA_PCI_ALIAS_GPU_NVIDIA_VENDOR = "10de"
NOVA_PCI_ALIAS_GPU_NVIDIA_TESLA_M60_DEVICE = "13f2"
NOVA_PCI_ALIAS_GPU_NVIDIA_TESLA_M60_NAME = "nvidia-tesla-m60"
NOVA_PCI_ALIAS_GPU_NVIDIA_TESLA_P40_DEVICE = "1b38"
NOVA_PCI_ALIAS_GPU_NVIDIA_TESLA_P40_NAME = "nvidia-tesla-p40"
NOVA_PCI_ALIAS_GPU_NVIDIA_TESLA_T4_PF_DEVICE = "1eb8"
NOVA_PCI_ALIAS_GPU_NVIDIA_TESLA_T4_PF_NAME = "nvidia-tesla-t4-pf"

# Ceph constants
HELM_APP_ROOK_CEPH = constants.HELM_APP_ROOK_CEPH
HELM_NS_ROOK_CEPH = 'rook-ceph'

CEPH_ROOK_BACKEND_NAME = constants.SB_DEFAULT_NAMES[constants.SB_TYPE_CEPH_ROOK]
CEPH_ROOK_IMAGE_DEFAULT_REPO = 'docker.io/openstackhelm/ceph-config-helper'
CEPH_ROOK_IMAGE_DEFAULT_TAG = 'ubuntu_jammy_18.2.2-1-20240312'
CEPH_ROOK_IMAGE_OVERRIDE = 'rook_ceph_config_helper'
CEPH_ROOK_MANAGER_APP = 'rook-ceph-mgr'
CEPH_ROOK_POLL_CRUSH_RULE = 'kube-rbd'
CEPH_ROOK_RBD_SECRET_NAME = 'rook-csi-rbd-provisioner'
CEPH_ROOK_RBD_DRIVER = 'rook-ceph.rbd.csi.ceph.com'

CEPH_RBD_SECRET_NAME = 'ceph-pool-kube-rbd'
CEPH_RBD_DRIVER = 'rbd.csi.ceph.com'
CEPH_RBD_SNAPSHOT_PREFIX = 'rbd-snap-'

CEPH_RBD_POOL_USER_CINDER = "cinder"
CEPH_RBD_POOL_USER_GLANCE = 'images'

CEPH_POOL_IMAGES_NAME = constants.CEPH_POOL_IMAGES_NAME
CEPH_POOL_IMAGES_CHUNK_SIZE = 256

CEPH_POOL_EPHEMERAL_NAME = constants.CEPH_POOL_EPHEMERAL_NAME
CEPH_POOL_EPHEMERAL_CHUNK_SIZE = 256

CEPH_POOL_VOLUMES_NAME = constants.CEPH_POOL_VOLUMES_NAME
CEPH_POOL_VOLUMES_APP_NAME = 'cinder-volumes'
CEPH_POOL_VOLUMES_CHUNK_SIZE = 512

CEPH_POOL_BACKUP_NAME = 'backup'
CEPH_POOL_BACKUP_APP_NAME = 'cinder-backup'
CEPH_POOL_BACKUP_CHUNK_SIZE = 256

# Rook ceph constants
ROOK_CEPH_POOL_CINDER_VOLUME_CHUNK_SIZE = 0
ROOK_CEPH_POOL_CINDER_BACKUP_CHUNK_SIZE = 0
ROOK_CEPH_POOL_GLANCE_CHUNK_SIZE = 0
ROOK_CEPH_POOL_NOVA_RBD_CHUNK_SIZE = 0

# Cinder version used as the default value when getting service name and type
CINDER_CURRENT_VERSION = 'v3'

CLIENTS_VOLUME_NAME = "clients-working-directory"
CLIENTS_WORKING_DIR = "/var/opt/openstack"
CLIENTS_WORKING_DIR_GROUP = "openstack"
CLIENTS_WORKING_DIR_USER = "sysadmin"

# NetApp definitions
NETAPP_CONTROLLER_LABEL = "controller.csi.trident.netapp.io"
NETAPP_MAIN_CONTAINER_NAME = "trident-main"

# STX-Openstack configuration values
OPENSTACK_CERT = "openstack-cert"
OPENSTACK_CERT_KEY = "openstack-cert-key"
OPENSTACK_CERT_CA = "openstack-cert-ca"
FORCE_READ_CERT_FILES = False
SERVICES_FQDN_PATTERN = "{service_name}.{endpoint_domain}"
OPENSTACK_NETAPP_NAMESPACE = "trident"

# Kubernetes
POD_SELECTOR_RUNNING = "status.phase==Running"

# Vswitch type node labels
OPENVSWITCH_LABEL = "openvswitch=enabled"
DPDK_LABEL = "dpdk=enabled"

# Placeholder label when none is found
VSWITCH_LABEL_NONE = "none"

# List of allowed vswitch label combinations
VSWITCH_ALLOWED_COMBINATIONS = [
    # OVS only
    {OPENVSWITCH_LABEL},
    # OVS-DPDK
    {OPENVSWITCH_LABEL, DPDK_LABEL},
]

# Return messages from ceph configmap creation
CEPH_BACKEND_NOT_CONFIGURED = "Not configured"
DB_API_NOT_AVAILABLE = "Database API is not available"

# StarlingX applications:
OIDC_AUTH_APP = constants.HELM_APP_OIDC_AUTH
