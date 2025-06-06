#
# Copyright (c) 2019-2024 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack
from k8sapp_openstack.utils import get_services_fqdn_pattern


class HorizonHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the horizon chart"""

    CHART = app_constants.HELM_CHART_HORIZON

    SERVICE_NAME = app_constants.HELM_CHART_HORIZON
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_HORIZON

    AUTH_USERS = ["admin"]

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
                'conf': {
                    'horizon': {
                        'local_settings': {
                            'config': self._get_local_settings_config_overrides(),
                        }
                    }
                },
                'endpoints': self._get_endpoints_overrides(),
                'network': {
                    'node_port': {
                        'enabled': self._get_network_node_port_overrides()
                    },
                    'dashboard': {
                        'ingress': {
                            'annotations': {
                                'nginx.ingress.kubernetes.io/proxy-body-size': "2500m"
                            }
                        }
                    }
                }
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

    def _get_endpoints_overrides(self):
        horizon_service_name = self._operator.chart_operators[
            app_constants.HELM_CHART_HORIZON].SERVICE_NAME
        return {
            'dashboard': {
                'host_fqdn_override':
                    self._get_endpoints_host_fqdn_overrides(
                        app_constants.HELM_CHART_HORIZON),
                'port': self._get_endpoints_port_api_public_overrides(),
                'scheme': self._get_endpoints_scheme_public_overrides(),
            },
            'oslo_db': {
                'auth': self._get_endpoints_oslo_db_overrides(
                    self.SERVICE_NAME, [self.SERVICE_NAME])
            },
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    horizon_service_name, self.AUTH_USERS),
            }
        }

    def _get_local_settings_config_overrides(self):
        local_settings_config = {
            'horizon_secret_key': self._get_or_generate_password(
                self.SERVICE_NAME, common.HELM_NS_OPENSTACK,
                'horizon_secret_key'),

            'system_region_name': self._region_name()
        }

        # Basic region config additions
        if self._region_config():
            openstack_host = 'controller'  # TODO(tsmith) must evaluate region functionality
            region_name = self._region_name()

            local_settings_config.update({
                'openstack_keystone_url': "http://%s:5000/v3" % openstack_host,
                'region_name': region_name,
                'available_regions': [("http://%s:5000/v3" % openstack_host, region_name), ],
                'ss_enabled': 'True',
            })

        # Distributed cloud additions
        if self._distributed_cloud_role() in [
                constants.DISTRIBUTED_CLOUD_ROLE_SYSTEMCONTROLLER]:

            local_settings_config.update({
                'dc_mode': 'True',
            })

        # Https & security settings
        if self._is_openstack_https_ready(self.SERVICE_NAME):
            local_settings_config.update({
                'https_enabled': 'True',
            })

        # After version 4.0, CSFR protection implemented by Django consults
        # the Origin header and requires the CSRF_TRUSTED_ORIGINS config to be
        # defined.
        # Ref.: https://docs.djangoproject.com/en/4.2/releases/4.0/#csrf
        csrf_trusted_origins = []
        # Get the openstack endpoint public domain name
        endpoint_domain = self._get_service_parameter(
            constants.SERVICE_TYPE_OPENSTACK,
            constants.SERVICE_PARAM_SECTION_OPENSTACK_HELM,
            constants.SERVICE_PARAM_NAME_ENDPOINT_DOMAIN)
        if endpoint_domain is not None:
            # Define endpoint domain based on pattern
            fqdn_pattern = get_services_fqdn_pattern()
            service_endpoint = fqdn_pattern.format(
                    service_name=self.SERVICE_NAME,
                    endpoint_domain=str(endpoint_domain.value),
            ).lower()
            csrf_trusted_origins.append("%s://%s" %
                                        (self._get_public_protocol(),
                                         service_endpoint))
        local_settings_config.update({
            'csrf_trusted_origins': csrf_trusted_origins,
        })

        lockout_retries = self._get_service_parameter('horizon', 'auth', 'lockout_retries')
        lockout_seconds = self._get_service_parameter('horizon', 'auth', 'lockout_seconds')
        if lockout_retries is not None and lockout_seconds is not None:
            local_settings_config.update({
                'lockout_retries_num': str(lockout_retries.value),
                'lockout_period_sec': str(lockout_seconds.value),
            })

        return local_settings_config

    def _region_config(self):
        # A wrapper over the Base region_config check.
        if (self._distributed_cloud_role() ==
                constants.DISTRIBUTED_CLOUD_ROLE_SUBCLOUD):
            return False
        else:
            return super(HorizonHelm, self)._region_config()

    def _get_network_node_port_overrides(self):
        # If openstack endpoint FQDN is configured, disable node_port 31000
        # which will enable the Ingress for the horizon service
        endpoint_fqdn = self._get_service_parameter(
            constants.SERVICE_TYPE_OPENSTACK,
            constants.SERVICE_PARAM_SECTION_OPENSTACK_HELM,
            constants.SERVICE_PARAM_NAME_ENDPOINT_DOMAIN)
        if endpoint_fqdn:
            return False
        else:
            return True
