#
# Copyright (c) 2019-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class OpenvswitchHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the openvswitch chart"""

    CHART = app_constants.HELM_CHART_OPENVSWITCH
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_OPENVSWITCH

    def _is_enabled(self, app_name, chart_name, namespace):
        # First, see if this chart is enabled by the user then adjust based on
        # system conditions
        if not super(OpenvswitchHelm, self)._is_enabled(app_name, chart_name, namespace):
            return False

        # Chart is enabled, let's check the node label
        return self.is_openvswitch_enabled() and not self.is_openvswitch_dpdk_enabled()

    def execute_manifest_updates(self, operator):
        # On application load, this chart in not included in the compute-kit
        # chart group . Insert as needed.
        if self._is_enabled(operator.APP,
                            self.CHART, common.HELM_NS_OPENSTACK):
            operator.chart_group_chart_insert(
                operator.CHART_GROUPS_LUT[self.CHART],
                operator.CHARTS_LUT[self.CHART],
                before_chart=operator.CHARTS_LUT[app_constants.HELM_CHART_NOVA])

    def execute_kustomize_updates(self, operator):
        if not self._is_enabled(operator.APP, self.CHART,
                            common.HELM_NS_OPENSTACK):
            operator.helm_release_resource_delete(self.CHART)

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
                'conf': {
                    'ovs_dpdk': {
                        'enabled': self.is_openvswitch_dpdk_enabled()
                    }
                }
            }
        }

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides
