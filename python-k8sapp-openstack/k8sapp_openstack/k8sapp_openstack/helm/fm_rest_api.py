#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging
from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack

from sysinv.common import exception
from sysinv.helm import common

LOG = logging.getLogger(__name__)


class FmRestApiHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the fm-rest-api chart"""

    CHART = app_constants.HELM_CHART_FM_REST_API

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
            'oslo_db': {
                'auth': self._get_endpoints_oslo_db_overrides(
                    fm_service_name, self.AUTH_USERS)
            },
        }
