#
# Copyright (c) 2019-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging
from sysinv.common import constants
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

        if not enabled:
            return enabled

        # Garbd requires at least 2 controllers (for 2 mariadb replicas).
        if self._num_controllers() < 2:
            enabled = False
        elif utils.is_aio_duplex_system(self.dbapi):
            # On AIO-DX, enable garbd only when at least one OpenStack
            # enabled dedicated worker is unlocked. AIO controllers
            # are themselves reported as OpenStack enabled compute
            # nodes since they carry the openstack-compute-node label
            # and report the worker subfunction, so they are excluded
            # by the personality check. Locked workers are excluded
            # because garbd cannot be scheduled on a cordoned node.
            labels_by_host = app_utils.get_labels_by_host(
                self.dbapi.label_get_all())
            compute_nodes = (
                app_utils.get_openstack_enabled_compute_nodes(
                    self.dbapi.ihost_get_list(), labels_by_host))
            if not any(
                h.personality == constants.WORKER
                and h.administrative == constants.ADMIN_UNLOCKED
                for h in compute_nodes
            ):
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
