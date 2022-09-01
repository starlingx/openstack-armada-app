#
# Copyright (c) 2019-2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class AodhHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the aodh chart"""

    CHART = app_constants.HELM_CHART_AODH
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_AODH

    SERVICE_NAME = app_constants.HELM_CHART_AODH
    AUTH_USERS = ['aodh']

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': self._get_pod_overrides(),
                'conf': self._get_conf_overrides(),
                'endpoints': self._get_endpoints_overrides()
            }
        }

        if self._is_openstack_https_ready():
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
        overrides = {
            'replicas': {
                'api': self._num_provisioned_controllers(),
                'evaluator': self._num_provisioned_controllers(),
                'listener': self._num_provisioned_controllers(),
                'notifier': self._num_provisioned_controllers()
            }
        }
        return overrides

    def _get_conf_overrides(self):
        conf_overrides = {
            'aodh': {
                'service_credentials': {
                    'region_name': self._region_name()
                }
            }
        }
        if self._is_openstack_https_ready():
            conf_overrides = self._update_overrides(conf_overrides, {
                'aodh': {
                    'keystone_authtoken': {
                        'cafile': self.get_ca_file()
                    }
                }
            })

        return conf_overrides

    def _get_endpoints_overrides(self):
        return {
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS),
            },
            'alarming': {
                'host_fqdn_override':
                    self._get_endpoints_host_fqdn_overrides(
                        self.SERVICE_NAME),
                'port': self._get_endpoints_port_api_public_overrides(),
                'scheme': self._get_endpoints_scheme_public_overrides(),
            },
            'oslo_cache': {
                'auth': {
                    'memcache_secret_key':
                        self._get_common_password('auth_memcache_key')
                }
            },
            'oslo_db': {
                'auth': self._get_endpoints_oslo_db_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS)
            },
            'oslo_messaging': {
                'auth': self._get_endpoints_oslo_messaging_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS)
            },
        }
