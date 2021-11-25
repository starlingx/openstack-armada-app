#
# Copyright (c) 2019-2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

# Helm: Supported charts:
# These values match the names in the chart package's Chart.yaml
HELM_CHART_AODH = 'aodh'
HELM_CHART_BARBICAN = 'barbican'
HELM_CHART_CEILOMETER = 'ceilometer'
HELM_CHART_CINDER = 'cinder'
HELM_CHART_FM_REST_API = 'fm-rest-api'
HELM_CHART_GARBD = 'garbd'
HELM_CHART_GLANCE = 'glance'
HELM_CHART_GNOCCHI = 'gnocchi'
HELM_CHART_HEAT = 'heat'
HELM_CHART_HELM_TOOLKIT = 'openstack-helm-toolkit'
HELM_CHART_HORIZON = 'horizon'
HELM_CHART_INGRESS = 'ingress'
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
HELM_CHART_PSP_ROLEBINDING = 'openstack-psp-rolebinding'

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

CEPH_POOL_IMAGES_NAME = 'images'
CEPH_POOL_IMAGES_CHUNK_SIZE = 256

CEPH_POOL_EPHEMERAL_NAME = 'ephemeral'
CEPH_POOL_EPHEMERAL_CHUNK_SIZE = 256

CEPH_POOL_VOLUMES_NAME = 'cinder-volumes'
CEPH_POOL_VOLUMES_APP_NAME = 'cinder-volumes'
CEPH_POOL_VOLUMES_CHUNK_SIZE = 512

CEPH_POOL_BACKUP_APP_NAME = 'cinder-backup'
CEPH_POOL_BACKUP_CHUNK_SIZE = 256
