#
# Copyright (c) 2019-2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class MagnumHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the magnum chart"""

    CHART = app_constants.HELM_CHART_MAGNUM
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_MAGNUM

    SERVICE_NAME = app_constants.HELM_CHART_MAGNUM

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': {
                    'replicas': {
                        'api': self._num_provisioned_controllers(),
                        'conductor': self._num_provisioned_controllers()
                    }
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
