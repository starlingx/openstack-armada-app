#
# Copyright (c) 2019-2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import utils
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class SwiftHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the swift chart"""

    CHART = app_constants.HELM_CHART_SWIFT
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_SWIFT

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

        bind_host = (constants.CONTROLLER_FQDN
                     if utils.is_fqdn_ready_to_use()
                     else self._get_management_address())

        host_dict = {
            'hosts': {
                'default': 'null',
                'admin': bind_host,
                'internal': bind_host,
                'public': self._get_oam_address()
            },
        }
        return host_dict

    def _get_endpoints_overrides(self):
        return {
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS),
            },
            'object_store': self._get_object_store_overrides(),
        }
