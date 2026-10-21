#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class MasakariHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the masakari chart"""

    CHART = app_constants.HELM_CHART_MASAKARI
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_MASAKARI

    SERVICE_NAME = app_constants.HELM_CHART_MASAKARI
    AUTH_USERS = ['masakari']

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
                'conf': self._get_conf_overrides(),
                'pod': self._get_pod_overrides(),
                'endpoints': self._get_endpoints_overrides(),
                'manifests': self._get_manifests_overrides(),
            }
        }

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides

    def _get_conf_overrides(self):
        # masakari-api defaults to binding 0.0.0.0, which is unreachable on an
        # IPv6-only deployment. Bind :: so the one socket serves both families
        # (the platform keeps net.ipv6.bindv6only=0).
        return {
            'masakari': {
                'DEFAULT': {
                    'masakari_api_listen': '::',
                },
            },
        }

    def _get_pod_overrides(self):
        return {
            'replicas': {
                'masakari_api': self._num_provisioned_controllers(),
                'masakari_engine': self._num_provisioned_controllers(),
            }
        }

    def _get_manifests_overrides(self):
        # The instance (VM/QEMU) monitor works through the libvirt hostPath
        # with no extra platform wiring.
        return {
            'instance_monitor': True,
            # TODO: enable host_monitor once the Node-read RBAC and the
            # taint-gate land. Process/introspective monitors are deferred.
        }

    def _get_endpoints_overrides(self):
        return {
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS),
            },
            'instance_ha': {
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
