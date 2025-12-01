#
# Copyright (c) 2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class PrometheusOpenstackExporterHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the Openstack Exporter chart"""

    CHART = app_constants.HELM_CHART_PROMETHEUS_OPENSTACK_EXPORTER
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_PROMETHEUS_OPENSTACK_EXPORTER

    def get_overrides(self, namespace=None):

        overrides = {
            common.HELM_NS_OPENSTACK: {
                # TODO: add helm overrides
            }
        }

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides
