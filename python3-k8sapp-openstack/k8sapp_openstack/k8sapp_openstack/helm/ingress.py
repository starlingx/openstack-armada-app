#
# Copyright (c) 2019-2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class IngressHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the ingress chart"""

    CHART = app_constants.HELM_CHART_INGRESS
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_INGRESS

    def get_overrides(self, namespace=None):
        limit_enabled, limit_cpus, limit_mem_mib = self._get_platform_res_limit()

        overrides = {
            common.HELM_NS_OPENSTACK: {
                'conf': {
                     'ingress': {
                         'proxy-connect-timeout': "30"
                     }
                },
                'pod': {
                    'replicas': {
                        'ingress': self._num_provisioned_controllers(),
                        'error_page': self._num_provisioned_controllers()
                    },
                    'resources': {
                        'enabled': limit_enabled,
                        'ingress': {
                            'limits': {
                                'cpu': "%d000m" % (limit_cpus),
                                'memory': "%dMi" % (limit_mem_mib)
                            }
                        },
                        'error_pages': {
                            'limits': {
                                'cpu': "%d000m" % (limit_cpus),
                                'memory': "%dMi" % (limit_mem_mib)
                            }
                        }
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
