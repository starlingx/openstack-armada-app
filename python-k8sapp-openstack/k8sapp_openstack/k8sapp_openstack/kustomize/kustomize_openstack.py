#
# Copyright (c) 2022 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

""" System inventory Kustomization resource operator."""

from oslo_log import log as logging
from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm import kustomize_base as base

from k8sapp_openstack.common import constants as app_constants

LOG = logging.getLogger(__name__)


class OpenstackFluxCDKustomizeOperator(base.FluxCDKustomizeOperator):

    APP = constants.HELM_APP_OPENSTACK

    APP_GROUP_SWIFT = [
        app_constants.FLUXCD_HELMRELEASE_SWIFT
    ]
    APP_GROUP_COMPUTE_KIT = [
        app_constants.FLUXCD_HELMRELEASE_LIBVIRT,
        app_constants.FLUXCD_HELMRELEASE_PLACEMENT,
        app_constants.FLUXCD_HELMRELEASE_NOVA,
        app_constants.FLUXCD_HELMRELEASE_NOVA_API_PROXY,
        app_constants.FLUXCD_HELMRELEASE_PCI_IRQ_AFFINITY_AGENT,
        app_constants.FLUXCD_HELMRELEASE_NEUTRON
    ]
    APP_GROUP_HEAT = [
        app_constants.FLUXCD_HELMRELEASE_HEAT
    ]
    APP_GROUP_TELEMETRY = [
        app_constants.FLUXCD_HELMRELEASE_AODH,
        app_constants.FLUXCD_HELMRELEASE_GNOCCHI,
        app_constants.FLUXCD_HELMRELEASE_CEILOMETER
    ]

    def manifest_chart_groups_disable(self, dbapi, namespace, chart):
        """ Disable charts in chart group

        :param dbapi: DB api object
        :param namespace: cgroup namespace
        :param chart: the chart
        """

        app_id = dbapi.kube_app_get(self.APP).id

        db_helm_override = dbapi.helm_override_get(
            app_id, chart, namespace)

        db_helm_override.system_overrides.update({'enabled': False})
        dbapi.helm_override_update(
            app_id, chart, namespace,
            {app_constants.HELM_OVERRIDE_GROUP_SYSTEM: db_helm_override.system_overrides})

    def chart_remove(self, dbapi, namespace, chart):
        self.helm_release_resource_delete(chart)
        self.manifest_chart_groups_disable(dbapi, namespace, chart)

    def platform_mode_kustomize_updates(self, dbapi, mode):
        """ Update the top-level kustomization resource list

        Make changes to the top-level kustomization resource list based on the
        openstack mode

        :param dbapi: DB api object
        :param mode: mode to control when to update the resource list
        """

        if mode == constants.OPENSTACK_RESTORE_DB:
            # During application restore, first bring up
            # MariaDB service.
            # TODO
            pass

        elif mode == constants.OPENSTACK_RESTORE_STORAGE:
            # After MariaDB data is restored, restore Keystone,
            # Glance and Cinder.
            # TODO
            pass

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
                for release in self.APP_GROUP_SWIFT:
                    self.chart_remove(dbapi,
                                      app_constants.HELM_NS_OPENSTACK,
                                      release)
                for release in self.APP_GROUP_COMPUTE_KIT:
                    self.chart_remove(dbapi,
                                      app_constants.HELM_NS_OPENSTACK,
                                      release)
                for release in self.APP_GROUP_HEAT:
                    self.chart_remove(dbapi,
                                      app_constants.HELM_NS_OPENSTACK,
                                      release)
                for release in self.APP_GROUP_TELEMETRY:
                    self.chart_remove(dbapi,
                                      app_constants.HELM_NS_OPENSTACK,
                                      release)

    def save_kustomize_for_deletion(self):
        # TODO: transcribe the manifest_openstack save_delete_manifest logic
        pass
