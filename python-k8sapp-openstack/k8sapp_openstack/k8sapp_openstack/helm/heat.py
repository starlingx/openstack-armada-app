#
# Copyright (c) 2019-2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class HeatHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the heat chart"""

    CHART = app_constants.HELM_CHART_HEAT
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_HEAT

    SERVICE_NAME = app_constants.HELM_CHART_HEAT
    AUTH_USERS = ['heat', 'heat_trustee', 'heat_stack_user']

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': self._get_pod_overrides(),
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

    def _get_pod_overrides(self):
        return {
            'replicas': {
                'api': self._num_provisioned_controllers(),
                'cfn': self._num_provisioned_controllers(),
                'cloudwatch': self._num_provisioned_controllers(),
                'engine': self._num_provisioned_controllers()
            }
        }

    def _get_endpoints_overrides(self):
        return {
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS),
            },
            'cloudformation': {
                'host_fqdn_override':
                    self._get_endpoints_host_fqdn_overrides(
                        'cloudformation'),
                'port': self._get_endpoints_port_api_public_overrides(),
                'scheme': self._get_endpoints_scheme_public_overrides(),
            },
            'orchestration': {
                'host_fqdn_override':
                    self._get_endpoints_host_fqdn_overrides(
                        self.SERVICE_NAME),
                'port': self._get_endpoints_port_api_public_overrides(),
                'scheme': self._get_endpoints_scheme_public_overrides(),
            },
            'oslo_db': {
                'auth': self._get_endpoints_oslo_db_overrides(
                    self.SERVICE_NAME, [self.SERVICE_NAME])
            },
            'oslo_messaging': {
                'auth': self._get_endpoints_oslo_messaging_overrides(
                    self.SERVICE_NAME, [self.SERVICE_NAME])
            },
        }

    def get_region_name(self):
        return self._get_service_region_name(self.SERVICE_NAME)

    def _get_conf_overrides(self):
        return {
            'heat': {
                'keystone_authtoken': {
                    'cafile': self.get_ca_file()
                },
                'ssl': {
                    'ca_file': self.get_ca_file()
                },
                'clients': {
                    'ca_file': self.get_ca_file()
                },
                'clients_aodh': {
                    'ca_file': self.get_ca_file()
                },
                'clients_neutron': {
                    'ca_file': self.get_ca_file()
                },
                'clients_cinder': {
                    'ca_file': self.get_ca_file()
                },
                'clients_glance': {
                    'ca_file': self.get_ca_file()
                },
                'clients_nova': {
                    'ca_file': self.get_ca_file()
                },
                'clients_swift': {
                    'ca_file': self.get_ca_file()
                },
                'clients_heat': {
                    'ca_file': self.get_ca_file()
                },
                'clients_keystone': {
                    'ca_file': self.get_ca_file()
                },
            }
        }

    def _get_secrets_overrides(self):
        return {
            'tls': {
                'orchestration': {
                    'api': {
                        'internal': 'heat-tls-public',
                    },
                },
                'cloudformation': {
                    'cfn': {
                        'internal': 'cloudformation-tls-public',
                    }
                }
            }
        }
