#
# Copyright (c) 2019-2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class SwiftHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the swift chart"""

    CHART = app_constants.HELM_CHART_SWIFT

    SERVICE_NAME = 'swift'
    SERVICE_TYPE = 'object-store'
    AUTH_USERS = ['swift']

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
                'endpoints': self._get_endpoints_overrides(),
            }
        }

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides

    def _get_object_store_overrides(self):
        return {
            'hosts': {
                'default': 'null',
                'admin': self._get_management_address(),
                'internal': self._get_management_address(),
                'public': self._get_oam_address()
            },
        }

    def _get_endpoints_overrides(self):
        return {
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS),
            },
            'object_store': self._get_object_store_overrides(),
        }
