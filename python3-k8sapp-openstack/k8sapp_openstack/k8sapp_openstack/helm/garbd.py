#
# Copyright (c) 2019-2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import utils
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class GarbdHelm(openstack.BaseHelm):
    """Class to encapsulate helm operations for the galera arbitrator chart"""

    # The service name is used to build the standard docker image location.
    # It is intentionally "mariadb" and not "garbd" as they both use the
    # same docker image.
    SERVICE_NAME = app_constants.HELM_CHART_MARIADB
    CHART = app_constants.HELM_CHART_GARBD
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_GARBD

    def _is_enabled(self, app_name, chart_name, namespace):
        # First, see if this chart is enabled by the user then adjust based on
        # system conditions
        enabled = super(GarbdHelm, self)._is_enabled(
            app_name, chart_name, namespace)

        # If there are fewer than 2 controllers or we're on AIO-DX or we are on
        # distributed cloud system controller, we'll use a single mariadb server
        # and so we don't want to run garbd.
        if enabled and (self._num_controllers() < 2 or
                        utils.is_aio_duplex_system(self.dbapi) or
                        (self._distributed_cloud_role() ==
                         constants.DISTRIBUTED_CLOUD_ROLE_SYSTEMCONTROLLER)):
            enabled = False
        return enabled

    def execute_manifest_updates(self, operator):
        # On application load this chart is enabled in the mariadb chart group
        if not self._is_enabled(operator.APP,
                                self.CHART, common.HELM_NS_OPENSTACK):
            operator.chart_group_chart_delete(
                operator.CHART_GROUPS_LUT[self.CHART],
                operator.CHARTS_LUT[self.CHART])

    def execute_kustomize_updates(self, operator):
        # On application load this chart is enabled
        if not self._is_enabled(operator.APP, self.CHART,
                                common.HELM_NS_OPENSTACK):
            operator.helm_release_resource_delete(self.CHART)

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
            }
        }

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides
