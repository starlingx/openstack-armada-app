#
# Copyright (c) 2019-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging
from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack

LOG = logging.getLogger(__name__)


class CeilometerHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the ceilometer chart"""

    CHART = app_constants.HELM_CHART_CEILOMETER
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_CEILOMETER

    SERVICE_NAME = app_constants.HELM_CHART_CEILOMETER
    AUTH_USERS = ['ceilometer']

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': self._get_pod_overrides(),
                'conf': self._get_conf_overrides(),
                'manifests': self._get_manifests_overrides(),
                'endpoints': self._get_endpoints_overrides(),
            }
        }

        # Gate for the chart patch that wires OS_CACERT into the ks-* Job pods.
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
        return {
            'replicas': {
                'central': self._num_provisioned_controllers(),
                'notification': self._num_provisioned_controllers()
            }
        }

    def _get_manifests_overrides(self):
        # IPMI agent is not included in the image; keep its daemonset disabled.
        return {'daemonset_ipmi': False}

    def _get_conf_overrides(self):
        ceilometer_conf = {
            'notification': {
                'messaging_urls': {
                    'values': self._get_notification_messaging_urls()
                }
            },
            'meter': {
                'meter_definitions_dirs': '/etc/ceilometer/meters.d'
            },
        }
        if self._is_openstack_https_ready(self.SERVICE_NAME):
            ceilometer_conf['service_credentials'] = {
                'cafile': self.get_ca_file()
            }
        return {'ceilometer': ceilometer_conf}

    def _get_notification_messaging_urls(self):
        rabbit_user = 'rabbitmq-admin'
        rabbit_pass = self._get_common_password(rabbit_user)
        rabbit_host = self._get_service_default_dns_name(
            app_constants.HELM_CHART_RABBITMQ)
        rabbit_port = 5672
        rabbit_paths = ['/ceilometer', '/cinder', '/glance', '/nova',
                        '/keystone', '/neutron', '/heat']

        LOG.debug("Ceilometer notification messaging host: %s", rabbit_host)

        return [
            'rabbit://%s:%s@%s:%d%s' %
            (rabbit_user, rabbit_pass, rabbit_host, rabbit_port, rabbit_path)
            for rabbit_path in rabbit_paths
        ]

    def _get_endpoints_overrides(self):
        return {
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS),
            },
            'oslo_cache': {
                'auth': {
                    'memcache_secret_key':
                        self._get_common_password('auth_memcache_key')
                }
            },
            'oslo_messaging': {
                'auth': self._get_endpoints_oslo_messaging_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS),
                'statefulset': {
                    'replicas': self._num_provisioned_controllers()
                }
            },
        }

    def get_region_name(self):
        return self._get_service_region_name(self.SERVICE_NAME)
