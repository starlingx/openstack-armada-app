#
# Copyright (c) 2019-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class DcdbsyncHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the dcdbsync chart"""

    CHART = app_constants.HELM_CHART_DCDBSYNC
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_DCDBSYNC
    AUTH_USERS = ['dcdbsync']
    SERVICE_NAME = app_constants.HELM_CHART_DCDBSYNC

    def _is_enabled(self, app_name, chart_name, namespace):
        """Determine whether this chart should be enabled.

        This function verifies that the chart will be downloaded if the
        user enabled the chart and it's Central Cloud. This is required
        so that all container images are included during the download the
        charts, allowing subclouds to apply the stx-openstack application
        successfully.

        Args:
            app_name (str): Name of the application (e.g., 'stx-openstack').
            chart_name (str): Helm chart name.
            namespace (str): Kubernetes namespace where the chart
                would be deployed.

        Returns:
            bool: "True" only for enabled chart in Central Cloud.
        """
        # See if this chart is enabled by the user and block if isn't DC.
        enabled = super(DcdbsyncHelm, self)._is_enabled(
            app_name, chart_name, namespace)
        if enabled and (self._distributed_cloud_role() !=
                        constants.DISTRIBUTED_CLOUD_ROLE_SYSTEMCONTROLLER):
            enabled = False
        return enabled

    def execute_manifest_updates(self, operator):
        if self._is_enabled(operator.APP,
                            self.CHART, common.HELM_NS_OPENSTACK):
            operator.manifest_chart_groups_insert(
                operator.ARMADA_MANIFEST,
                operator.CHART_GROUPS_LUT[self.CHART])

    def execute_kustomize_updates(self, operator):
        if not self._is_enabled(operator.APP, self.CHART,
                                common.HELM_NS_OPENSTACK):
            operator.helm_release_resource_delete(self.CHART)

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
                'endpoints': self._get_endpoints_overrides(),
            }
        }

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides

    def _get_endpoints_overrides(self):
        return {
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS),
            },
            'dcorch_dbsync': {
                'host_fqdn_override':
                    self._get_endpoints_host_fqdn_overrides(
                        self.SERVICE_NAME),
            },
        }
