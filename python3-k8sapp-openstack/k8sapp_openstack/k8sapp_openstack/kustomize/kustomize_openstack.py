#
# Copyright (c) 2022-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

""" System inventory Kustomization resource operator."""

from copy import deepcopy

from oslo_log import log as logging
from sysinv.common import constants
from sysinv.helm import kustomize_base as base

from k8sapp_openstack.common import constants as app_constants

LOG = logging.getLogger(__name__)


class OpenstackFluxCDKustomizeOperator(base.FluxCDKustomizeOperator):

    def __init__(self):
        super().__init__()
        self.resources_before_restore = []

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
        app_id = dbapi.kube_app_get_endswith(self.APP).id
        db_helm_override = dbapi.helm_override_get(
            app_id, chart, namespace)

        db_helm_override.system_overrides.update({'enabled': False})
        dbapi.helm_override_update(
            app_id, chart, namespace,
            {app_constants.HELM_OVERRIDE_GROUP_SYSTEM: db_helm_override.system_overrides})

    def chart_remove(self, dbapi, namespace, chart):
        self.helm_release_resource_delete(chart)
        self.manifest_chart_groups_disable(dbapi, namespace, chart)

    def enable_helmrelease_resource(self, resource):
        """ Enables a disabled resource that was moved from KustomizeOperator
        helmrelease_resource_map to helmrelease_cleanup list.

        :param resource: Helm Release resource to be enabled
        """
        LOG.debug('Enabling Helm Release Resource: [{}]'.format(resource))
        self.helmrelease_resource_map[resource] = {
            "name": resource,
            "namespace": app_constants.HELM_NS_OPENSTACK,
            "resource": resource,
        }

        self.kustomization_resources.append(
            self.helmrelease_resource_map[resource]['resource'])

        cleanup_res = deepcopy(self.helmrelease_resource_map[resource])
        cleanup_res.pop("resource", None)
        self.helmrelease_cleanup.remove(cleanup_res)

    def set_helm_releases(self, dbapi, namespace, helm_charts_list):
        """ Based on a list of required Helm Releases, ensure that those will be
        the only releases enabled on a given namespace. It is done by enabling
        only the necessary helm releases and removing any other release.

        :param dbapi: DB api object
        :param namespace: cgroup namespace
        :param helm_charts_list: list of the required charts
        """
        active_resources = list(self.helmrelease_resource_map.keys())
        cleaned_resources = [d['name'] for d in self.helmrelease_cleanup]

        # Disable unnecessary active Helm Releases
        for resource in active_resources:
            if resource not in helm_charts_list:
                LOG.debug('Deleting Helm Release Resource: [{}]'
                          .format(resource))
                self.chart_remove(dbapi,
                                  app_constants.HELM_NS_OPENSTACK,
                                  resource)
        # Enable necessary Helm Releases that were removed previously
        for resource in helm_charts_list:
            if (resource in cleaned_resources
                    and resource not in active_resources):
                self.enable_helmrelease_resource(resource)

    def platform_mode_kustomize_updates(self, dbapi, mode):
        """ Update the top-level kustomization resource list
        Make changes to the top-level kustomization resource list based on the
        openstack mode

        :param dbapi: DB api object
        :param mode: mode to control when to update the resource list
        """
        if mode == constants.OPENSTACK_RESTORE_DB:
            LOG.debug("Application apply mode: [{}]".format(mode))
            # Before updating the kustomization resources, save the original
            # resources to be reestablished after the Restore routine
            if not self.resources_before_restore:
                self.resources_before_restore = [
                    k for k in self.helmrelease_resource_map.keys()
                ]
                LOG.debug("HelmReleases before restore: {}"
                     .format(self.resources_before_restore))

            # During application restore, first bring up
            # MariaDB and dependencies.
            release_list = [
                app_constants.FLUXCD_HELMRELEASE_INGRESS,
                app_constants.FLUXCD_HELMRELEASE_NGINX_PORTS_CONTROL,
                app_constants.FLUXCD_HELMRELEASE_MARIADB
            ]
            # TODO: check app_constants.FLUXCD_HELMRELEASE_DCDBSYNC
            if (app_constants.FLUXCD_HELMRELEASE_GARBD
                    in self.resources_before_restore):
                release_list.append(app_constants.FLUXCD_HELMRELEASE_GARBD)
            self.set_helm_releases(dbapi,
                                   app_constants.HELM_NS_OPENSTACK,
                                   release_list)
        elif mode == constants.OPENSTACK_RESTORE_STORAGE:
            LOG.debug("Application apply mode: [{}]".format(mode))
            # After MariaDB data is restored, restore Keystone,
            # Glance and Cinder.
            release_list = [
                app_constants.FLUXCD_HELMRELEASE_INGRESS,
                app_constants.FLUXCD_HELMRELEASE_NGINX_PORTS_CONTROL,
                app_constants.FLUXCD_HELMRELEASE_MARIADB,
                app_constants.FLUXCD_HELMRELEASE_MEMCACHED,
                app_constants.FLUXCD_HELMRELEASE_RABBITMQ,
                app_constants.FLUXCD_HELMRELEASE_KEYSTONE,
                app_constants.FLUXCD_HELMRELEASE_GLANCE,
                app_constants.FLUXCD_HELMRELEASE_CINDER
            ]
            # TODO: check app_constants.FLUXCD_HELMRELEASE_DCDBSYNC
            if (app_constants.FLUXCD_HELMRELEASE_GARBD
                    in self.resources_before_restore):
                release_list.append(
                    app_constants.FLUXCD_HELMRELEASE_GARBD
                )
            if (app_constants.FLUXCD_HELMRELEASE_KEYSTONE_API_PROXY
                    in self.resources_before_restore):
                release_list.append(
                    app_constants.FLUXCD_HELMRELEASE_KEYSTONE_API_PROXY
                )
            self.set_helm_releases(dbapi,
                                   app_constants.HELM_NS_OPENSTACK,
                                   release_list)
        else:
            LOG.debug("Application apply mode: [{}]".format(mode))
            # In case this is the last step of a Restore routine the
            # resources_before_restore list will not be empty and will
            # contain the resources to be reestablished
            if self.resources_before_restore:
                LOG.debug("Restoring HelmReleases resources: [{}]"
                         .format(self.resources_before_restore))
                self.set_helm_releases(dbapi,
                                       app_constants.HELM_NS_OPENSTACK,
                                       self.resources_before_restore)
                self.resources_before_restore = []

    def save_kustomize_for_deletion(self):
        # TODO: transcribe the manifest_openstack save_delete_manifest logic
        pass
