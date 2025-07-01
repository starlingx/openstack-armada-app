#
# Copyright (c) 2019 Intel, Inc.
# Copyright (c) 2019-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class NginxPortsControlHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for nginx-ports-control chart"""

    CHART = app_constants.HELM_CHART_NGINX_PORTS_CONTROL
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_NGINX_PORTS_CONTROL

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
                'manifests': {
                    'global_network_policy': True
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
