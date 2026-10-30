#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class WatcherHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the watcher chart"""

    CHART = app_constants.HELM_CHART_WATCHER
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_WATCHER

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
