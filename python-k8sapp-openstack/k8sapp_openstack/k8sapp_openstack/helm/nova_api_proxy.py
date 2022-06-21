#
# Copyright (c) 2019-2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class NovaApiProxyHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the nova chart"""

    CHART = app_constants.HELM_CHART_NOVA_API_PROXY

    SERVICE_NAME = app_constants.HELM_CHART_NOVA_API_PROXY
    AUTH_USERS = ['nova']
    SERVICE_USERS = ['neutron', 'placement']

    def get_overrides(self, namespace=None):

        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': {
                    'user': {
                        'nova_api_proxy': {
                            'uid': 0
                        }
                    },
                    'replicas': {
                        'proxy': self._num_provisioned_controllers()
                    }
                },
                'conf': {
                    'nova_api_proxy': {
                        'DEFAULT': {
                            'nfvi_compute_listen': self._get_management_address()
                        },
                    }
                },
                'endpoints': self._get_endpoints_overrides(),
            }
        }

        if self._is_openstack_https_ready():
            overrides[common.HELM_NS_OPENSTACK] = self._update_overrides(
                overrides[common.HELM_NS_OPENSTACK],
                {
                    'conf': self._get_conf_overrides(),
                    'secrets': self._get_secrets_overrides(),
                }
            )

            overrides[common.HELM_NS_OPENSTACK] = \
                self._enable_certificates(overrides[common.HELM_NS_OPENSTACK])

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides

    def _get_endpoints_overrides(self):
        nova_service_name = self._operator.chart_operators[
            app_constants.HELM_CHART_NOVA].SERVICE_NAME

        return {
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    nova_service_name, self.AUTH_USERS, self.SERVICE_USERS),
            },
            'compute': {
                'host_fqdn_override':
                    self._get_endpoints_host_fqdn_overrides(
                        app_constants.HELM_CHART_NOVA),
                'port': self._get_endpoints_port_api_public_overrides(),
                'scheme': self._get_endpoints_scheme_public_overrides(),
            },
        }

    def _get_conf_overrides(self):
        return {
            'nova_api_proxy': {
                'keystone_authtoken': {
                    'cafile': self.get_ca_file(),
                },
            }
        }

    def _get_secrets_overrides(self):
        return {
            'tls': {
                'compute': {
                    'api_proxy': {
                        'public': 'nova-tls-public'
                    }
                }
            }
        }
