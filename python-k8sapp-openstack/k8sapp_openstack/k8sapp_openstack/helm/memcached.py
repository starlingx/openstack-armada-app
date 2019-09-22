#
# Copyright (c) 2019-2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from k8sapp_openstack.common import constants as app_constants
from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm import common
from sysinv.helm import base


class MemcachedHelm(base.BaseHelm):
    """Class to encapsulate helm operations for the memcached chart"""

    CHART = app_constants.HELM_CHART_MEMCACHED
    SUPPORTED_NAMESPACES = \
        base.BaseHelm.SUPPORTED_NAMESPACES + [common.HELM_NS_OPENSTACK]
    SUPPORTED_APP_NAMESPACES = {
        constants.HELM_APP_OPENSTACK:
            base.BaseHelm.SUPPORTED_NAMESPACES + [common.HELM_NS_OPENSTACK]
    }

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
