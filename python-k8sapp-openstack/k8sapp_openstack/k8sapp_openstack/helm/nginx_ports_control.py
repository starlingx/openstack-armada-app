#
# Copyright (c) 2019 Intel, Inc.
# Copyright (c) 2019-2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import base
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants


class NginxPortsControlHelm(base.BaseHelm):
    """Class to encapsulate helm operations for nginx-ports-control chart"""

    CHART = app_constants.HELM_CHART_NGINX_PORTS_CONTROL
    SUPPORTED_NAMESPACES = \
        base.BaseHelm.SUPPORTED_NAMESPACES + [common.HELM_NS_OPENSTACK]

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
