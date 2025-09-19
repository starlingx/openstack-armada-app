#
# Copyright (c) 2019-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging
from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack import utils as app_utils
from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


LOG = logging.getLogger(__name__)


class OpenvswitchHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the openvswitch chart"""

    CHART = app_constants.HELM_CHART_OPENVSWITCH
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_OPENVSWITCH

    def _is_enabled(self, app_name, chart_name, namespace):
        """Determine whether this chart should be enabled.

        For Central Cloud (SystemController), this function ensures that the
        chart is always considered enabled. This is required so that all
        container images are included during the download the charts, allowing
        subclouds to apply the stx-openstack application successfully.

        Args:
            app_name (str): Name of the application (e.g., 'stx-openstack').
            chart_name (str): Helm chart name.
            namespace (str): Kubernetes namespace where the chart
                would be deployed.

        Returns:
            bool: Always "True" for Central Cloud to ensure images are
            downloaded. For other environments, may defer to default logic.
        """
        # First, check if system's distributed cloud role is System Controller.
        # Chart must be enabled during "application-upload --images" if it is.
        if app_utils.is_central_cloud():
            return True

        # See if this chart is enabled by the user
        if not super(OpenvswitchHelm, self)._is_enabled(
                app_name, chart_name, namespace):
            return False

        # Enable chart only when standard Open vSwitch is used.
        # When OVS runs with DPDK, a different dataplane management is required
        # and enabling this chart would conflict with the DPDK deployment.
        return self.is_openvswitch_enabled() and \
            not self.is_openvswitch_dpdk_enabled()

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
