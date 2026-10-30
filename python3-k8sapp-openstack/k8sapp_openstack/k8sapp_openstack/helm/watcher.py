#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


class WatcherHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the watcher chart"""

    CHART = app_constants.HELM_CHART_WATCHER
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_WATCHER

    SERVICE_NAME = app_constants.HELM_CHART_WATCHER
    AUTH_USERS = ['watcher']

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': self._get_pod_overrides(),
                'conf': self._get_conf_overrides(),
                'endpoints': self._get_endpoints_overrides()
            }
        }

        if self._is_openstack_https_ready(self.SERVICE_NAME):
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
        # Floored at 1: the raw controller count is 0 during bootstrap,
        # which would scale Watcher to zero replicas.
        replicas = self._num_replicas_for_platform_app()
        return {
            'replicas': {
                'api': replicas,
                'applier': replicas,
                'decision_engine': replicas,
            }
        }

    def _get_conf_overrides(self):
        conf_overrides = {
            'watcher': {
                'watcher_clients_auth': {
                    'auth_type': app_constants.WATCHER_CLIENTS_AUTH_TYPE,
                    'username': self.SERVICE_NAME,
                    'password': self._get_service_user_password(),
                    'project_name':
                        app_constants.WATCHER_CLIENTS_AUTH_PROJECT_NAME,
                    'user_domain_name':
                        app_constants.WATCHER_CLIENTS_AUTH_USER_DOMAIN_NAME,
                    'project_domain_name':
                        app_constants.WATCHER_CLIENTS_AUTH_PROJECT_DOMAIN_NAME,
                    'region_name': self.get_region_name(),
                },
                'oslo_messaging_notifications': {
                    'transport_url': self._get_notification_transport_url()
                },
            }
        }

        if self._is_openstack_https_ready(self.SERVICE_NAME):
            conf_overrides = self._update_overrides(conf_overrides, {
                'watcher': {
                    'keystone_authtoken': {
                        'cafile': self.get_ca_file()
                    }
                }
            })

        return conf_overrides

    def _get_notification_transport_url(self):
        # The chart has no oslo_messaging_notifications section, so the
        # fallback points at Watcher's own vhost, not where Nova publishes.
        return self._get_rabbit_notification_url('/nova')

    def _get_service_user_password(self):
        """Same (chart, namespace, field) triple as the identity override,
        so this matches endpoints.identity.auth.watcher.password.
        """
        return self._get_or_generate_password(
            self.SERVICE_NAME, common.HELM_NS_OPENSTACK, self.SERVICE_NAME)

    def get_region_name(self):
        return self._get_service_region_name(self.SERVICE_NAME)

    def _get_endpoints_overrides(self):
        return {
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS),
            },
            'infra_optim': {
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
