#
# Copyright (c) 2019-2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

""" System inventory Armada manifest operator."""

from copy import deepcopy
import os

from oslo_log import log as logging
import ruamel.yaml as yaml
from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm import manifest_base as base

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm.aodh import AodhHelm
from k8sapp_openstack.helm.barbican import BarbicanHelm
from k8sapp_openstack.helm.ceilometer import CeilometerHelm
from k8sapp_openstack.helm.cinder import CinderHelm
from k8sapp_openstack.helm.dcdbsync import DcdbsyncHelm
from k8sapp_openstack.helm.fm_rest_api import FmRestApiHelm
from k8sapp_openstack.helm.garbd import GarbdHelm
from k8sapp_openstack.helm.glance import GlanceHelm
from k8sapp_openstack.helm.gnocchi import GnocchiHelm
from k8sapp_openstack.helm.heat import HeatHelm
from k8sapp_openstack.helm.horizon import HorizonHelm
from k8sapp_openstack.helm.ingress import IngressHelm
from k8sapp_openstack.helm.ironic import IronicHelm
from k8sapp_openstack.helm.keystone import KeystoneHelm
from k8sapp_openstack.helm.keystone_api_proxy import KeystoneApiProxyHelm
from k8sapp_openstack.helm.libvirt import LibvirtHelm
from k8sapp_openstack.helm.magnum import MagnumHelm
from k8sapp_openstack.helm.mariadb import MariadbHelm
from k8sapp_openstack.helm.memcached import MemcachedHelm
from k8sapp_openstack.helm.neutron import NeutronHelm
from k8sapp_openstack.helm.nginx_ports_control import NginxPortsControlHelm
from k8sapp_openstack.helm.nova import NovaHelm
from k8sapp_openstack.helm.nova_api_proxy import NovaApiProxyHelm
from k8sapp_openstack.helm.openvswitch import OpenvswitchHelm
from k8sapp_openstack.helm.pci_irq_affinity_agent import PciIrqAffinityAgentHelm
from k8sapp_openstack.helm.placement import PlacementHelm
from k8sapp_openstack.helm.psp_rolebinding import PSPRolebindingHelm
from k8sapp_openstack.helm.rabbitmq import RabbitmqHelm
from k8sapp_openstack.helm.swift import SwiftHelm


KEY_SCHEMA = "schema"
VAL_SCHEMA_CHART_GROUP = "armada/ChartGroup/v"
VAL_SCHEMA_MANIFEST = "armada/Manifest/v"
KEY_METADATA = "metadata"
KEY_METADATA_NAME = "name"
KEY_DATA = "data"
KEY_DATA_CHART_GROUP = "chart_group"  # for chart group doc updates
KEY_DATA_CHART_GROUPS = "chart_groups"  # for manifest doc updates
KEY_DATA_SEQUENCED = "sequenced"

LOG = logging.getLogger(__name__)


class OpenstackArmadaManifestOperator(base.ArmadaManifestOperator):
    APP = app_constants.HELM_APP_OPENSTACK
    ARMADA_MANIFEST = "openstack-manifest"

    CHART_GROUP_PSP_ROLEBINDING = "openstack-psp-rolebinding"
    CHART_GROUP_INGRESS_OS = "openstack-ingress"
    CHART_GROUP_MAGNUM = "openstack-magnum"
    CHART_GROUP_MARIADB = "openstack-mariadb"
    CHART_GROUP_MEMCACHED = "openstack-memcached"
    CHART_GROUP_RABBITMQ = "openstack-rabbitmq"
    CHART_GROUP_KEYSTONE = "openstack-keystone"
    CHART_GROUP_KS_API_PROXY = "openstack-keystone-api-proxy"
    CHART_GROUP_BARBICAN = "openstack-barbican"
    CHART_GROUP_GLANCE = "openstack-glance"
    CHART_GROUP_SWIFT = "openstack-ceph-rgw"
    CHART_GROUP_CINDER = "openstack-cinder"
    CHART_GROUP_FM_REST_API = "openstack-fm-rest-api"
    CHART_GROUP_COMPUTE_KIT = "openstack-compute-kit"
    CHART_GROUP_HEAT = "openstack-heat"
    CHART_GROUP_HORIZON = "openstack-horizon"
    CHART_GROUP_TELEMETRY = "openstack-telemetry"
    CHART_GROUP_DCDBSYNC = "openstack-dcdbsync"

    CHART_GROUPS_LUT = {
        AodhHelm.CHART: CHART_GROUP_TELEMETRY,
        BarbicanHelm.CHART: CHART_GROUP_BARBICAN,
        CeilometerHelm.CHART: CHART_GROUP_TELEMETRY,
        CinderHelm.CHART: CHART_GROUP_CINDER,
        FmRestApiHelm.CHART: CHART_GROUP_FM_REST_API,
        GarbdHelm.CHART: CHART_GROUP_MARIADB,
        GlanceHelm.CHART: CHART_GROUP_GLANCE,
        GnocchiHelm.CHART: CHART_GROUP_TELEMETRY,
        HeatHelm.CHART: CHART_GROUP_HEAT,
        HorizonHelm.CHART: CHART_GROUP_HORIZON,
        IngressHelm.CHART: CHART_GROUP_INGRESS_OS,
        IronicHelm.CHART: CHART_GROUP_COMPUTE_KIT,
        KeystoneHelm.CHART: CHART_GROUP_KEYSTONE,
        KeystoneApiProxyHelm.CHART: CHART_GROUP_KS_API_PROXY,
        LibvirtHelm.CHART: CHART_GROUP_COMPUTE_KIT,
        MagnumHelm.CHART: CHART_GROUP_MAGNUM,
        MariadbHelm.CHART: CHART_GROUP_MARIADB,
        MemcachedHelm.CHART: CHART_GROUP_MEMCACHED,
        NeutronHelm.CHART: CHART_GROUP_COMPUTE_KIT,
        NginxPortsControlHelm.CHART: CHART_GROUP_INGRESS_OS,
        NovaHelm.CHART: CHART_GROUP_COMPUTE_KIT,
        NovaApiProxyHelm.CHART: CHART_GROUP_COMPUTE_KIT,
        PciIrqAffinityAgentHelm.CHART: CHART_GROUP_COMPUTE_KIT,
        OpenvswitchHelm.CHART: CHART_GROUP_COMPUTE_KIT,
        PlacementHelm.CHART: CHART_GROUP_COMPUTE_KIT,
        PSPRolebindingHelm.CHART: CHART_GROUP_PSP_ROLEBINDING,
        RabbitmqHelm.CHART: CHART_GROUP_RABBITMQ,
        SwiftHelm.CHART: CHART_GROUP_SWIFT,
        DcdbsyncHelm.CHART: CHART_GROUP_DCDBSYNC,
    }

    CHARTS_LUT = {
        AodhHelm.CHART: "openstack-aodh",
        BarbicanHelm.CHART: "openstack-barbican",
        CeilometerHelm.CHART: "openstack-ceilometer",
        CinderHelm.CHART: "openstack-cinder",
        GarbdHelm.CHART: "openstack-garbd",
        FmRestApiHelm.CHART: "openstack-fm-rest-api",
        GlanceHelm.CHART: "openstack-glance",
        GnocchiHelm.CHART: "openstack-gnocchi",
        HeatHelm.CHART: "openstack-heat",
        HorizonHelm.CHART: "openstack-horizon",
        IngressHelm.CHART: "openstack-ingress",
        IronicHelm.CHART: "openstack-ironic",
        KeystoneHelm.CHART: "openstack-keystone",
        KeystoneApiProxyHelm.CHART: "openstack-keystone-api-proxy",
        LibvirtHelm.CHART: "openstack-libvirt",
        MagnumHelm.CHART: "openstack-magnum",
        MariadbHelm.CHART: "openstack-mariadb",
        MemcachedHelm.CHART: "openstack-memcached",
        NeutronHelm.CHART: "openstack-neutron",
        NginxPortsControlHelm.CHART: "openstack-nginx-ports-control",
        NovaHelm.CHART: "openstack-nova",
        NovaApiProxyHelm.CHART: "openstack-nova-api-proxy",
        PciIrqAffinityAgentHelm.CHART: "openstack-pci-irq-affinity-agent",
        OpenvswitchHelm.CHART: "openstack-openvswitch",
        PSPRolebindingHelm.CHART: "openstack-psp-rolebinding",
        PlacementHelm.CHART: "openstack-placement",
        RabbitmqHelm.CHART: "openstack-rabbitmq",
        SwiftHelm.CHART: "openstack-ceph-rgw",
        DcdbsyncHelm.CHART: "openstack-dcdbsync",
    }

    def __init__(self, *args, **kwargs):
        super(OpenstackArmadaManifestOperator, self).__init__(*args, **kwargs)

        self.delete_manifest_contents = []  # OS Armada app delete manifest

    def platform_mode_manifest_updates(self, dbapi, mode):
        """Update the application manifest based on the platform

        This is used for

        :param dbapi: DB api object
        :param mode: mode to control how to apply the application manifest
        """

        if mode == constants.OPENSTACK_RESTORE_DB:
            # During application restore, first bring up
            # MariaDB service.
            self.manifest_chart_groups_set(
                self.ARMADA_MANIFEST,
                [self.CHART_GROUP_INGRESS_OS, self.CHART_GROUP_MARIADB],
            )

        elif mode == constants.OPENSTACK_RESTORE_STORAGE:
            # After MariaDB data is restored, restore Keystone,
            # Glance and Cinder.
            self.manifest_chart_groups_set(
                self.ARMADA_MANIFEST,
                [
                    self.CHART_GROUP_INGRESS_OS,
                    self.CHART_GROUP_MARIADB,
                    self.CHART_GROUP_MEMCACHED,
                    self.CHART_GROUP_RABBITMQ,
                    self.CHART_GROUP_KEYSTONE,
                    self.CHART_GROUP_GLANCE,
                    self.CHART_GROUP_CINDER,
                ],
            )

        else:
            # When mode is OPENSTACK_RESTORE_NORMAL or None,
            # bring up all the openstack services.
            try:
                system = dbapi.isystem_get_one()
            except exception.NotFound:
                LOG.exception("System %s not found.")
                raise

            if (
                system.distributed_cloud_role
                == constants.DISTRIBUTED_CLOUD_ROLE_SYSTEMCONTROLLER
            ):
                # remove the chart_groups not needed in this configuration
                self.manifest_chart_groups_delete(
                    self.ARMADA_MANIFEST, self.CHART_GROUP_SWIFT
                )
                self.manifest_chart_groups_delete(
                    self.ARMADA_MANIFEST, self.CHART_GROUP_COMPUTE_KIT
                )
                self.manifest_chart_groups_delete(
                    self.ARMADA_MANIFEST, self.CHART_GROUP_HEAT
                )
                self.manifest_chart_groups_delete(
                    self.ARMADA_MANIFEST, self.CHART_GROUP_TELEMETRY
                )

    def save_delete_manifest(self):
        """Save an updated manifest for deletion

        This is an override method to reverse the OpenStack remove sequence,
        compared to the deployment sequence in OpenStack manifest

        armada delete doesn't support --values files as does the apply. To
        handle proper deletion of the conditional charts/chart groups that end
        up in the overrides files, create a unified file for use when deleting.

        NOTE #1: If we want to abandon using manifest overrides files,
        this generated file could probably be used on apply and delete.

        NOTE #2: Diffing the original manifest and this manifest provides a
        clear view of the conditional changes that were enforced by the system
        in the plugins
        """

        if os.path.exists(self.manifest_path):

            self.delete_manifest_contents = deepcopy(self.content)

            # Reverse the OpenStack remove sequence
            for i in self.delete_manifest_contents:

                if VAL_SCHEMA_MANIFEST in i[KEY_SCHEMA]:
                    i[KEY_DATA][KEY_DATA_CHART_GROUPS].reverse()

                if VAL_SCHEMA_CHART_GROUP in i[KEY_SCHEMA]:

                    # Neutron shall be first one to be deleted on (reversed)
                    # compute kit group
                    if (
                        i[KEY_METADATA][KEY_METADATA_NAME]
                        == self.CHART_GROUP_COMPUTE_KIT
                    ):

                        try:
                            lst = i[KEY_DATA][KEY_DATA_CHART_GROUP]
                            lst.append(
                                lst.pop(
                                    lst.index(
                                        self.CHARTS_LUT[NeutronHelm.CHART]))
                            )

                            # Compute-kit group shall be deleted sequentially
                            i[KEY_DATA][KEY_DATA_SEQUENCED] = "true"

                        except Exception as e:
                            LOG.error(
                                "Failed compute-kit delete manifest. %s" % e)

                    # Removal sequence is the reverse of deployment sequence
                    # (for all groups)
                    i[KEY_DATA][KEY_DATA_CHART_GROUP].reverse()

            # cleanup existing delete manifest
            self._cleanup_deletion_manifest()

            # Save overrides
            if self.delete_manifest:
                with open(self.delete_manifest, "w") as f:
                    try:
                        yaml.dump_all(
                            self.delete_manifest_contents,
                            f,
                            Dumper=yaml.RoundTripDumper,
                            explicit_start=True,
                            default_flow_style=False,
                        )
                        LOG.info(
                            "Delete manifest file %s is generated"
                            % self.delete_manifest
                        )
                    except Exception as e:
                        LOG.error(
                            "Failed to generate delete manifest file %s. %s"
                            % (self.delete_manifest, e)
                        )
            else:
                LOG.error("Delete manifest file does not exist.")
        else:
            LOG.error(
                "Manifest directory %s does not exist." % self.manifest_path)
