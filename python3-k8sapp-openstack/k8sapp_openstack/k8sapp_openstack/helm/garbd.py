#
# Copyright (c) 2019-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging
from sysinv.common import exception
from sysinv.common import utils
from sysinv.helm import common

from k8sapp_openstack import utils as app_utils
from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


LOG = logging.getLogger(__name__)


class GarbdHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the galera arbitrator chart"""

    # The service name is used to build the standard docker image location.
    # It is intentionally "mariadb" and not "garbd" as they both use the
    # same docker image.
    SERVICE_NAME = app_constants.HELM_CHART_MARIADB
    CHART = app_constants.HELM_CHART_GARBD
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_GARBD

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
        enabled = super(GarbdHelm, self)._is_enabled(
            app_name, chart_name, namespace)

        # If there are fewer than 2 controllers or we're on AIO-DX
        # we'll use a single mariadb server and so we don't want to run garbd.
        if enabled and (self._num_controllers() < 2 or
                        utils.is_aio_duplex_system(self.dbapi)):
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
