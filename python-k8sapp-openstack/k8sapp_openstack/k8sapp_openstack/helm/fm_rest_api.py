#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging
from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack


LOG = logging.getLogger(__name__)


class FmRestApiHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the fm-rest-api chart"""

    CHART = app_constants.HELM_CHART_FM_REST_API
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_FM_REST_API

    SERVICE_NAME = app_constants.HELM_CHART_FM_REST_API
    AUTH_USERS = ['fm']

    def get_overrides(self, namespace=None):

        overrides = {
            common.HELM_NS_OPENSTACK: {
                'endpoints': self._get_endpoints_overrides(),
                'pod': {
                    'replicas': {
                        'api': self._num_provisioned_controllers()
                    },
                },
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
        fm_service_name = self._operator.chart_operators[
            app_constants.HELM_CHART_FM_REST_API].SERVICE_NAME

        return {
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    fm_service_name, self.AUTH_USERS),
            },
            'faultmanagement': {
                'host_fqdn_override':
                    self._get_endpoints_host_fqdn_overrides(
                        self.SERVICE_NAME),
                'port': self._get_endpoints_port_api_public_overrides(),
                'scheme': self._get_endpoints_scheme_public_overrides(),
            },
            'oslo_db': {
                'auth': self._get_endpoints_oslo_db_overrides(
                    fm_service_name, self.AUTH_USERS)
            },
        }

    def _get_conf_overrides(self):
        return {
            'fm': {
                'keystone_authtoken': {
                    'cafile': self.get_ca_file(),
                },
            }
        }

    def _get_secrets_overrides(self):
        return {
            'tls': {
                'faultmanagement': {
                    'faultmanagement': {
                        'public': 'keystone-tls-public',
                    },
                    'fm_api': {
                        'internal': 'keystone-tls-public',
                        'public': 'keystone-tls-public'
                    },
                }
            }
        }
