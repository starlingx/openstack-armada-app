#
# Copyright (c) 2025-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack import utils as app_utils
from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class PrometheusOpenstackExporterHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the Openstack Exporter chart"""

    CHART = app_constants.HELM_CHART_PROMETHEUS_OPENSTACK_EXPORTER
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_PROMETHEUS_OPENSTACK_EXPORTER

    SERVICE_NAME = app_constants.HELM_CHART_PROMETHEUS_OPENSTACK_EXPORTER
    AUTH_USERS = ['user']

    def _is_enabled(self, app_name, chart_name, namespace):
        """Determine whether this chart should be enabled.

        For Central Cloud (SystemController), this function ensures that the
        chart is always considered enabled. This is required so that all
        container images are included during the download the charts, allowing
        subclouds to deploy .

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
        return super(PrometheusOpenstackExporterHelm, self)._is_enabled(
            app_name, chart_name, namespace)

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': self._get_pod_overrides(),
                'endpoints': self._get_endpoints_overrides(),
            }
        }

        if self._is_openstack_https_ready():
            self._enable_certificates(
                overrides[common.HELM_NS_OPENSTACK])
            overrides[common.HELM_NS_OPENSTACK] = \
                self._update_overrides(
                    overrides[common.HELM_NS_OPENSTACK], {
                        'secrets': {
                            'tls': {
                                'identity': {
                                    'api': {
                                        'internal':
                                            'keystone-tls-public',
                                    }
                                }
                            }
                        }
                    })

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides

    def _get_pod_overrides(self):
        return {
            'replicas': {
                'prometheus_openstack_exporter':
                    self._num_provisioned_controllers()
            }
        }

    def _get_endpoints_overrides(self):
        return {
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS)
            }
        }
