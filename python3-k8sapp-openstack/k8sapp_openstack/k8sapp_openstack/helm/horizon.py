#
# Copyright (c) 2019-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging
from sysinv.common import constants
from sysinv.common import exception
from sysinv.db import api as dbapi
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack
from k8sapp_openstack.utils import _get_value_from_application
from k8sapp_openstack.utils import get_external_service_url
from k8sapp_openstack.utils import get_services_fqdn_pattern
from k8sapp_openstack.utils import is_dex_enabled

LOG = logging.getLogger(__name__)


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

        # WebSSO configuration when DEX federation is enabled
        if is_dex_enabled():
            websso_config = self._get_websso_auth_config_overrides()
            local_settings_config.update(websso_config)

        return local_settings_config

    def _get_websso_auth_config_overrides(self) -> dict:
        """
        Generate WebSSO authentication configuration for Horizon.

        When DEX federation is enabled in Keystone, this method generates
        the auth.sso and auth.idp_mapping configuration required for
        Horizon's local_settings.py to enable WebSSO functionality.

        The configuration includes:
        - auth.sso.enabled: True to enable WEBSSO_ENABLED
        - auth.sso.initial_choice: Default login method (credentials)
        - auth.idp_mapping: List of IdP configurations for WEBSSO_CHOICES
          and WEBSSO_IDP_MAPPING
        - openstack_keystone_url: External Keystone URL for federation

        Returns:
            dict: WebSSO configuration for Horizon local_settings with:
                - 'auth': SSO and IdP mapping configuration
                - 'openstack_keystone_url': External Keystone API URL
        """
        db = dbapi.get_instance()
        if db is None:
            LOG.warning("Database API instance not available for WebSSO configuration.")
            return {}

        # Get DEX IdP configuration from Keystone overrides
        provider_name = _get_value_from_application(
            default_value="dex",
            chart_name=app_constants.HELM_CHART_KEYSTONE,
            override_name="conf.federation.dex_idp.provider_name")

        protocol_name = _get_value_from_application(
            default_value="openid",
            chart_name=app_constants.HELM_CHART_KEYSTONE,
            override_name="conf.federation.dex_idp.protocol_name")

        # Allow users to customize the WebSSO label shown in Horizon
        websso_label = _get_value_from_application(
            default_value="Login with DEX SSO",
            chart_name=app_constants.HELM_CHART_KEYSTONE,
            override_name="conf.federation.dex_idp.websso_label")

        # Allow users to customize the initial choice (default: credentials)
        websso_initial_choice = _get_value_from_application(
            default_value="credentials",
            chart_name=app_constants.HELM_CHART_KEYSTONE,
            override_name="conf.federation.dex_idp.websso_initial_choice")

        websso_config = {
            'auth': {
                'sso': {
                    'enabled': True,
                    'initial_choice': websso_initial_choice,
                },
                'idp_mapping': [
                    {
                        'name': 'dex_oidc',
                        'label': websso_label,
                        'idp': provider_name,
                        'protocol': protocol_name,
                    }
                ]
            }
        }

        # Get external Keystone URL for WebSSO redirect
        # This is required because WebSSO authentication flow happens
        # through the browser which needs to access Keystone externally
        https_ready = self._is_openstack_https_ready()
        external_keystone_url = get_external_service_url(db, 'keystone', https_ready)

        if external_keystone_url:
            # Use 'raw' config to set OPENSTACK_KEYSTONE_URL
            keystone_url_with_version = f"{external_keystone_url}/v3"
            websso_config['raw'] = {
                'OPENSTACK_KEYSTONE_URL': keystone_url_with_version
            }
            LOG.info(f"Horizon WebSSO configured with external Keystone URL: "
                     f"{keystone_url_with_version}")
        else:
            LOG.warning("External Keystone URL not available for Horizon WebSSO.")

        return websso_config

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
