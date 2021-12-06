#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class PSPRolebindingHelm(openstack.BaseHelm):
    """Class to encapsulate helm operations for the psp rolebinding chart"""

    CHART = app_constants.HELM_CHART_PSP_ROLEBINDING
    SERVICE_NAME = 'psp-rolebinding'

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
