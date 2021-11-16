#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging
from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack

from sysinv.common import exception
from sysinv.helm import common

LOG = logging.getLogger(__name__)


class PciIrqAffinityAgentHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the PCI IRQ affinity agent chart"""

    CHART = app_constants.HELM_CHART_PCI_IRQ_AFFINITY_AGENT

    def __init__(self, operator):
        super(PciIrqAffinityAgentHelm, self).__init__(operator)

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
                'conf': {
                    'endpoints': self._get_endpoints_overrides()
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

    def _get_endpoints_overrides(self):
        nova_oslo_messaging_data = self._get_endpoints_oslo_messaging_overrides(
            'nova',
            ['nova']
        )['nova']

        overrides = {
            'rabbit': {
                'rabbit_userid': nova_oslo_messaging_data['username'],
                'rabbit_password': nova_oslo_messaging_data['password'],
            },
        }

        return overrides
