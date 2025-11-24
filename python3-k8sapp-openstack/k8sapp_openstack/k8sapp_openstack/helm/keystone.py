#
# Copyright (c) 2019-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import os

from oslo_log import log as logging
from six.moves import configparser
from sysinv.common import exception
from sysinv.db import api as dbapi
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack
from k8sapp_openstack.utils import get_dex_issuer_url
from k8sapp_openstack.utils import get_external_service_url
from k8sapp_openstack.utils import is_dex_enabled

LOG = logging.getLogger(__name__)

OPENSTACK_PASSWORD_RULES_FILE = '/etc/keystone/password-rules.conf'


class KeystoneHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the keystone chart"""

    CHART = app_constants.HELM_CHART_KEYSTONE
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_KEYSTONE

    SERVICE_NAME = app_constants.HELM_CHART_KEYSTONE
    SERVICE_PATH = '/v3'

    DEFAULT_DOMAIN_NAME = 'default'

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': self._get_pod_overrides(),
                'conf': self._get_conf_overrides(),
                'endpoints': self._get_endpoints_overrides(),
                'network': self._get_network_overrides(),
            }
        }

        if self._is_openstack_https_ready(self.SERVICE_NAME):
            overrides[common.HELM_NS_OPENSTACK] = self._update_overrides(
                overrides[common.HELM_NS_OPENSTACK],
                {'secrets': self._get_secrets_overrides()}
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
        overrides = {
            'replicas': {
                'api': self._num_provisioned_controllers()
            },
            'lifecycle': {
                'termination_grace_period': {
                    'api': {
                        'timeout': 60
                    }
                }
            }
        }
        return overrides

    def _get_conf_keystone_default_overrides(self):
        return {
            'max_token_size': 255,  # static controller.yaml => chart default
            'debug': False,  # static controller.yaml => chart default
            'use_syslog': True,  # static controller.yaml
            'syslog_log_facility': 'local2',  # static controller.yaml
            'log_file': '/dev/null',  # static controller.yaml
            # 'admin_token': self._generate_random_password(length=32)
        }

    def _get_conf_keystone_database_overrides(self):
        return {
            'idle_timeout': 60,  # static controller.yaml
            'max_pool_size': 1,  # static controller.yaml
            'max_overflow': 50,  # static controller.yaml
        }

    def _get_conf_keystone_oslo_middleware_overrides(self):
        return {
            'enable_proxy_headers_parsing': True  # static controller.yaml
        }

    def _get_conf_keystone_token_overrides(self):
        return {
            'provider': 'fernet'  # static controller.yaml => chart default
        }

    def _get_conf_keystone_identity_overrides(self):
        return {
            'driver': 'sql'  # static controller.yaml
        }

    def _get_conf_keystone_assignment_overrides(self):
        return {
            'driver': 'sql'  # static controller.yaml
        }

    @staticmethod
    def _extract_openstack_password_rules_from_file(
            rules_file, section="security_compliance"):
        try:
            config = configparser.RawConfigParser()
            parsed_config = config.read(rules_file)
            if not parsed_config:
                msg = ("Cannot parse rules file: %s" % rules_file)
                raise Exception(msg)
            if not config.has_section(section):
                msg = ("Required section '%s' not found in rules file" % section)
                raise Exception(msg)

            rules = config.items(section)
            if not rules:
                msg = ("section '%s' contains no configuration options" % section)
                raise Exception(msg)
            return dict(rules)
        except Exception:
            raise Exception("Failed to extract password rules from file")

    def _get_password_rule(self):
        password_rule = {}
        if os.path.isfile(OPENSTACK_PASSWORD_RULES_FILE):
            try:
                passwd_rules = \
                    KeystoneHelm._extract_openstack_password_rules_from_file(
                        OPENSTACK_PASSWORD_RULES_FILE)
                password_rule.update({
                    'unique_last_password_count':
                        int(passwd_rules['unique_last_password_count']),
                    'password_regex':
                        self.quoted_str(passwd_rules['password_regex']),
                    'password_regex_description':
                        self.quoted_str(
                            passwd_rules['password_regex_description'])
                })
            except Exception:
                pass
        return password_rule

    def _get_conf_keystone_security_compliance_overrides(self):
        rgx = '^(?=.*\d)(?=.*[a-z])(?=.*[A-Z])(?=.*[!@#$%^&*()<>{}+=_\\\[\]\-?|~`,.;:]).{7,}$'
        overrides = {
            'unique_last_password_count': 2,  # static controller.yaml
            'password_regex': self.quoted_str(rgx),
            'password_regex_description':
                self.quoted_str('Password must have a minimum length of 7'
                                ' characters, and must contain at least 1'
                                ' upper case, 1 lower case, 1 digit, and 1'
                                ' special character'),
        }
        overrides.update(self._get_password_rule())
        return overrides

    def _get_conf_keystone_overrides(self):
        overrides = {
            'DEFAULT': self._get_conf_keystone_default_overrides(),
            'database': self._get_conf_keystone_database_overrides(),
            'oslo_middleware': self._get_conf_keystone_oslo_middleware_overrides(),
            'token': self._get_conf_keystone_token_overrides(),
            'identity': self._get_conf_keystone_identity_overrides(),
            'assignment': self._get_conf_keystone_assignment_overrides(),
            'security_compliance': self._get_conf_keystone_security_compliance_overrides(),
        }

        # Only include these sections if DEX integration is enabled
        if is_dex_enabled():
            overrides['auth'] = self._get_keystone_auth_methods()
            overrides['federation'] = self._get_keystone_trusted_dashboard()

        return overrides

    def _get_conf_policy_overrides(self):
        return {
            "admin_required": "role:admin or is_admin:1",
            "service_role": "role:service",
            "service_or_admin": "rule:admin_required or rule:service_role",
            "owner": "user_id:%(user_id)s",
            "admin_or_owner": "rule:admin_required or rule:owner",
            "token_subject": "user_id:%(target.token.user_id)s",
            "admin_or_token_subject": "rule:admin_required or rule:token_subject",
            "service_admin_or_token_subject":
                "rule:service_or_admin or rule:token_subject",
            "protected_domains":
                "'heat':%(target.domain.name)s or 'magnum':%(target.domain.name)s",
            "protected_projects":
                "'admin':%(target.project.name)s or 'services':%(target.project.name)s",
            "protected_admins":
                "'admin':%(target.user.name)s or 'heat_admin':%(target.user.name)s"
                " or 'dcmanager':%(target.user.name)s",
            "protected_roles":
                "'admin':%(target.role.name)s or 'heat_admin':%(target.user.name)s",
            "protected_services": [
                ["'aodh':%(target.user.name)s"],
                ["'barbican':%(target.user.name)s"],
                ["'ceilometer':%(target.user.name)s"],
                ["'cinder':%(target.user.name)s"],
                ["'glance':%(target.user.name)s"],
                ["'heat':%(target.user.name)s"],
                ["'neutron':%(target.user.name)s"],
                ["'nova':%(target.user.name)s"],
                ["'patching':%(target.user.name)s"],
                ["'sysinv':%(target.user.name)s"],
                ["'mtce':%(target.user.name)s"],
                ["'magnum':%(target.user.name)s"],
                ["'gnocchi':%(target.user.name)s"]
            ],
            "identity:delete_service": "rule:admin_required and not rule:protected_services",
            "identity:delete_domain": "rule:admin_required and not rule:protected_domains",
            "identity:delete_project": "rule:admin_required and not rule:protected_projects",
            "identity:delete_user":
                "rule:admin_required and not (rule:protected_admins or rule:protected_services)",
            "identity:change_password": "rule:admin_or_owner and not rule:protected_services",
            "identity:delete_role": "rule:admin_required and not rule:protected_roles",
        }

    def _get_conf_overrides(self):
        return {
            'keystone': self._get_conf_keystone_overrides(),
            'policy': self._get_conf_policy_overrides(),
            'federation': {
                **self._get_oidc_overrides(),
                **self._get_external_federation_urls()
            }
        }

    def _region_config(self):
        # A wrapper over the Base region_config check.
        return super(KeystoneHelm, self)._region_config()

    def _get_endpoints_overrides(self):
        overrides = {
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, []),
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

        admin_endpoint_override = \
            self._get_endpoints_hosts_admin_overrides(self.SERVICE_NAME)
        if admin_endpoint_override:
            overrides['identity']['hosts'] = admin_endpoint_override

        return overrides

    def _get_network_overrides(self):
        overrides = {
            'api': {
                'ingress': self._get_network_api_ingress_overrides(),
            }
        }
        return overrides

    def get_admin_user_name(self):
        if self._region_config():
            service_config = self._get_service_config(self.SERVICE_NAME)
            if service_config is not None:
                return service_config.capabilities.get('admin_user_name')
        return common.USER_ADMIN

    def get_admin_user_domain(self):
        if self._region_config():
            service_config = self._get_service_config(self.SERVICE_NAME)
            if service_config is not None:
                return service_config.capabilities.get('admin_user_domain')
        return self.DEFAULT_DOMAIN_NAME

    def get_admin_project_name(self):
        if self._region_config():
            service_config = self._get_service_config(self.SERVICE_NAME)
            if service_config is not None:
                return service_config.capabilities.get('admin_project_name')
        return common.USER_ADMIN

    def get_admin_project_domain(self):
        if self._region_config():
            service_config = self._get_service_config(self.SERVICE_NAME)
            if service_config is not None:
                return service_config.capabilities.get('admin_project_domain')
        return self.DEFAULT_DOMAIN_NAME

    def get_admin_password(self):
        o_user = self.get_admin_user_name()
        o_service = common.SERVICE_ADMIN

        return self._get_identity_password(o_service, o_user)

    def get_stx_admin_password(self):
        o_user = common.USER_STX_ADMIN
        o_service = common.SERVICE_ADMIN

        return self._get_identity_password(o_service, o_user)

    def get_region_name(self):
        return self._get_service_region_name(self.SERVICE_NAME)

    def _get_secrets_overrides(self):
        return {
            'tls': {
                'identity': {
                    'api': {
                        'internal': 'keystone-tls-public',
                    }
                }
            }
        }

    def _get_oidc_overrides(self):
        """
        Generate OIDC override values for Dex integration.

        This function builds the OIDC override dictionary containing the
        `provider_remote_id`, which is derived from the system's Dex issuer URL.
        The value is added even if the OIDC application itself is not applied,
        since it is only used when `dex_idp.enabled` is set to True.

        Returns:
            dict: A dictionary with the Dex OIDC override in the format:
                {
                    'dex_idp': {
                        'provider_remote_id': <issuer_url or empty string>
                    }
                }
        """
        db = dbapi.get_instance()
        dex_enabled = is_dex_enabled()
        # Because this will only be used if dex_idp.enabled is true, it can be ammended to the
        # overrides even if oidc is not applied
        return {
            'dex_idp': {
                'provider_remote_id': get_dex_issuer_url(db, dex_enabled)
            }
        }

    def _get_keystone_auth_methods(self):
        """
        Return Keystone authentication methods based on DEX configuration.

        If DEX integration is enabled, include `mapped` and `openid` in the list
        of supported authentication methods. Otherwise, return the standard
        Keystone methods.

        Returns:
            dict: A dictionary containing a single key `'methods'`, whose value
                is a comma-separated string of enabled authentication methods.
                Example: `{'methods': 'external,password,token,mapped,openid'}`
        """
        methods = ['external', 'password', 'token', 'mapped', 'openid']

        return {'methods': ','.join(methods)}

    def _get_keystone_trusted_dashboard(self):
        """
        Generate the Keystone federation configuration section containing
        the `trusted_dashboard` parameter.

        This value points to the Horizon dashboard endpoint used for WebSSO
        authentication when DEX integration is enabled.

        Returns:
            dict: A multistring type formatted dictionary override containing
            Horizon WebSSO URL.
        """
        urls = self._get_external_federation_urls()
        horizon_url = urls['external']['horizon']

        # Extract the base URL without the protocol
        if horizon_url.startswith('https://'):
            base_url = horizon_url.replace('https://', '', 1)
        elif horizon_url.startswith('http://'):
            base_url = horizon_url.replace('http://', '', 1)
        else:
            base_url = horizon_url

        http_url = f"http://{base_url}/auth/websso/"
        https_url = f"https://{base_url}/auth/websso/"

        return self._oslo_multistring_override(
            name='trusted_dashboard',
            values=[https_url, http_url]
        )

    def _get_external_federation_urls(self):
        """
        Discover and return external URLs for federation/WebSSO configuration.

        This function retrieves the external URLs needed for Keystone federation
        with DEX IdP. The URLs are discovered based on:
        - FQDN configuration (endpoint_domain must be configured)
        - OpenStack HTTPS/TLS readiness

        Returns:
            dict: A dictionary with external URLs in the format:
                {
                    'external': {
                        'keystone': <external_keystone_url>,
                        'horizon': <external_horizon_url>,
                        'dex': <dex_issuer_url>
                    }
                }
        """
        db = dbapi.get_instance()
        dex_enabled = is_dex_enabled()
        https_ready = self._is_openstack_https_ready()

        # Discover external URLs
        external_keystone_url = get_external_service_url(db, 'keystone', https_ready)
        external_horizon_url = get_external_service_url(db, 'horizon', https_ready)
        external_dex_url = get_dex_issuer_url(db, dex_enabled)

        result = {
            'external': {
                'keystone': external_keystone_url,
                'horizon': external_horizon_url,
                'dex': external_dex_url
            }
        }

        return result
