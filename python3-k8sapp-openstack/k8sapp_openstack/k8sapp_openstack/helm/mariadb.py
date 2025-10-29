#
# Copyright (c) 2019-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import exception
from sysinv.common import utils as cutils
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack
from k8sapp_openstack.utils import get_available_volume_backends
from k8sapp_openstack.utils import get_storage_backends_priority_list
from k8sapp_openstack.utils import is_ipv4


class MariadbHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the mariadb chart"""

    CHART = app_constants.HELM_CHART_MARIADB
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_MARIADB
    SERVICE_NAME = app_constants.HELM_CHART_MARIADB
    AUTH_USERS = ['mariadb']

    def _num_server_replicas(self):
        return self._num_provisioned_controllers()

    def get_overrides(self, namespace=None):

        available_backend = get_available_volume_backends()
        default_priority_list = get_storage_backends_priority_list(app_constants.HELM_CHART_MARIADB)
        priority_storage_class = app_constants.BACKEND_DEFAULT_STORAGE_CLASS

        for priority in default_priority_list:
            if available_backend.get(priority, ""):
                priority_storage_class = available_backend.get(priority)
                break

        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': {
                    'replicas': {
                        'server': self._num_server_replicas(),
                        'controller': self._num_server_replicas()
                    }
                },
                'endpoints': self._get_endpoints_overrides(),
                'manifests': {
                    'config_ipv6': not is_ipv4()
                },
                'volume': {
                    'class_name': priority_storage_class,
                    'backup': {
                        'class_name': priority_storage_class,
                    }

                }
            }
        }

        if not cutils.is_std_system(self.dbapi):
            config_override = {
                'conf': {
                    'database': {
                        'config_override': ''
                    }
                }
            }
            overrides[common.HELM_NS_OPENSTACK] = self._update_overrides(
                overrides[common.HELM_NS_OPENSTACK],
                config_override
            )

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides

    def _get_endpoints_overrides(self):
        return {
            'oslo_db': {
                'auth': self._get_endpoints_oslo_db_overrides(
                    self.CHART, [])
            },
            'identity': {
                'auth': self._get_endpoints_identity_overrides(
                    self.SERVICE_NAME, self.AUTH_USERS),
            }
        }
