#
# Copyright (c) 2019-2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack

from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import utils
from sysinv.helm import common


class OpenvswitchHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the openvswitch chart"""

    CHART = app_constants.HELM_CHART_OPENVSWITCH

    def _is_enabled(self, app_name, chart_name, namespace):
        # First, see if this chart is enabled by the user then adjust based on
        # system conditions
        enabled = super(OpenvswitchHelm, self)._is_enabled(
            app_name, chart_name, namespace)
        if enabled and (utils.get_vswitch_type(self.dbapi) !=
                        constants.VSWITCH_TYPE_NONE):
            enabled = False
        return enabled

    def execute_manifest_updates(self, operator):
        # On application load, this chart in not included in the compute-kit
        # chart group . Insert as needed.
        if self._is_enabled(operator.APP,
                            self.CHART, common.HELM_NS_OPENSTACK):
            operator.chart_group_chart_insert(
                operator.CHART_GROUPS_LUT[self.CHART],
                operator.CHARTS_LUT[self.CHART],
                before_chart=operator.CHARTS_LUT[app_constants.HELM_CHART_NOVA])

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {}
        }

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides
