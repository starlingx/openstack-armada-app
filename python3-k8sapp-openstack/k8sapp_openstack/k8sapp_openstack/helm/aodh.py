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
from k8sapp_openstack.utils import is_aodh_rest_notifier_tls_enabled

LOG = logging.getLogger(__name__)


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
        overrides = {
            'replicas': {
                'api': self._num_provisioned_controllers(),
                'evaluator': self._num_provisioned_controllers(),
                'listener': self._num_provisioned_controllers(),
                'notifier': self._num_provisioned_controllers()
            },
            'mounts': self._get_mount_overrides()
        }
        return overrides

    def _get_mount_overrides(self):
        mount_overrides = {
            'aodh_notifier': {
                'aodh_notifier': {
                    'volumes': [],
                    'volumeMounts': []
                }
            }
        }

        if is_aodh_rest_notifier_tls_enabled():
            # Mount Aodh REST Notifier CA certificate from Kubernetes secret.
            # The secret is created or migrated during the pre-apply lifecycle hook
            # (which runs after overrides but before helm install). These mounts are
            # added to the notifier pods when the cert secret is present in namespace
            # even if cert files cannot be found in the host since the files might be
            # temporarily missing during a controller migration.
            mount_overrides['aodh_notifier']['aodh_notifier']['volumes'].append({
                'name': app_constants.AODH_REST_NOTIFIER_CA_CERT_SECRET_NAME,
                'secret': {
                    'secretName': app_constants.AODH_REST_NOTIFIER_CA_CERT_SECRET_NAME,
                    'items': [{
                        'key': app_constants.AODH_REST_NOTIFIER_CA_CERT_SECRET_KEY,
                        'path': app_constants.AODH_REST_NOTIFIER_CA_CERT_SECRET_KEY
                    }]
                }
            })
            mount_overrides['aodh_notifier']['aodh_notifier']['volumeMounts'].append({
                'name': app_constants.AODH_REST_NOTIFIER_CA_CERT_SECRET_NAME,
                'mountPath': app_constants.AODH_REST_NOTIFIER_CA_CERT_MOUNT_PATH,
                'subPath': app_constants.AODH_REST_NOTIFIER_CA_CERT_SECRET_KEY,
                'readOnly': True
            })

        return mount_overrides

    def _get_conf_overrides(self):
        conf_overrides = {
            'aodh': {
                'DEFAULT': {},
                'service_credentials': {
                    'region_name': self.get_region_name()
                },
                'oslo_messaging_notifications': {
                    'transport_url': self._get_notification_transport_url()
                }
            }
        }
        if self._is_openstack_https_ready(self.SERVICE_NAME):
            conf_overrides = self._update_overrides(conf_overrides, {
                'aodh': {
                    'keystone_authtoken': {
                        'cafile': self.get_ca_file()
                    }
                }
            })

        if is_aodh_rest_notifier_tls_enabled():
            # we need to inject the certificate mounted path into aodh.conf
            # enabling the use of the provided cert file mounted in the pod
            conf_overrides['aodh']['DEFAULT']['rest_notifier_ca_bundle_certificate_path'] = \
                app_constants.AODH_REST_NOTIFIER_CA_CERT_MOUNT_PATH

        return conf_overrides

    def _get_notification_transport_url(self):
        return self._get_rabbit_notification_url('/ceilometer')

    def _get_endpoints_overrides(self):
        alarming_endpoints = {
            'host_fqdn_override':
                self._get_endpoints_host_fqdn_overrides(
                    self.SERVICE_NAME),
            'port': self._get_endpoints_port_api_public_overrides(),
            'scheme': self._get_endpoints_scheme_public_overrides(),
        }

        LOG.debug("Aodh alarming endpoints: %s", alarming_endpoints)

        return {
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS),
            },
            'alarming': alarming_endpoints,
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

    def get_region_name(self):
        return self._get_service_region_name(self.SERVICE_NAME)
