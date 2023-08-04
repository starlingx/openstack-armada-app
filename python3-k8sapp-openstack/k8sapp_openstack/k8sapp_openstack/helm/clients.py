#
# Copyright (c) 2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging
from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import utils
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack

LOG = logging.getLogger(__name__)


class ClientsHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the Clients chart."""

    CHART = app_constants.HELM_CHART_CLIENTS
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_CLIENTS

    SERVICE_NAME = app_constants.HELM_CHART_CLIENTS

    def __init__(self, operator):
        super(ClientsHelm, self).__init__(operator)

    def get_overrides(self, namespace=None):
        host_overrides = self._get_per_host_overrides()

        overrides = {
            common.HELM_NS_OPENSTACK: {
                "endpoints": self._get_endpoints_overrides(),
                "conf": {
                    "overrides": {
                        "clients_clients": {
                            "hosts": host_overrides,
                        }
                    }
                }
            }
        }

        if self._is_openstack_https_ready():
            overrides[common.HELM_NS_OPENSTACK] = \
                self._enable_certificates(overrides[common.HELM_NS_OPENSTACK])

            # The job-boostrap is disabled by default in this Helm chart since
            # it is only responsible for creating the TLS secret
            overrides[common.HELM_NS_OPENSTACK]["manifests"].update({
                "job_bootstrap": True,
            })

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides

    def _get_endpoints_overrides(self):
        overrides = self._get_common_users_overrides(
                    common.SERVICE_ADMIN)

        overrides['admin'].update({
            'project_name': self._get_admin_project_name(),
            'project_domain_name': self._get_admin_project_domain(),
            'user_domain_name': self._get_admin_user_domain(),
        })

        return {
            'identity': {
                'auth': overrides
            },
            'clients': {
                'host_fqdn_override': self._get_endpoints_host_fqdn_overrides(
                    self.SERVICE_NAME
                )
            },
        }

    def _get_per_host_overrides(self):
        host_list = []
        hosts = self.dbapi.ihost_get_list()

        for host in hosts:
            if (host.invprovision in [constants.PROVISIONED,
                                      constants.PROVISIONING]):
                if constants.WORKER in utils.get_personalities(host):

                    hostname = str(host.hostname)

                    host_clients = {
                        'name': hostname,
                        'conf': {}
                    }
                    host_list.append(host_clients)
        return host_list
