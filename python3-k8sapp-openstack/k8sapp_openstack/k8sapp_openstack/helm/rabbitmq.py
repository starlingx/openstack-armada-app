#
# Copyright (c) 2019-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging
from sysinv.common import exception
from sysinv.helm import common

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import openstack
from k8sapp_openstack.utils import get_available_volume_backends
from k8sapp_openstack.utils import get_storage_backends_priority_list
from k8sapp_openstack.utils import resolve_backend_storage_class


LOG = logging.getLogger(__name__)


class RabbitmqHelm(openstack.OpenstackBaseHelm):
    """Class to encapsulate helm operations for the rabbitmq chart"""

    CHART = app_constants.HELM_CHART_RABBITMQ
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_RABBITMQ

    def get_overrides(self, namespace=None):
        limit_enabled, limit_cpus, limit_mem_mib = self._get_platform_res_limit()

        # Refer to: https://github.com/rabbitmq/rabbitmq-common/commit/4f9ef33cf9ba52197ff210ffcdf6629c1b7a6e9e
        io_thread_pool_size = limit_cpus * 16
        if io_thread_pool_size < 64:
            io_thread_pool_size = 64
        elif io_thread_pool_size > 1024:
            io_thread_pool_size = 1024

        available_backend = get_available_volume_backends(app_constants.HELM_CHART_RABBITMQ)
        default_priority_list = get_storage_backends_priority_list(app_constants.HELM_CHART_RABBITMQ)
        priority_storage_class = resolve_backend_storage_class(
            default_priority_list, available_backend)
        if not priority_storage_class:
            LOG.error(
                f"Unable to resolve a StorageClass for the "
                f"{app_constants.HELM_CHART_RABBITMQ} chart: none of the backends "
                f"in the configured priority list {default_priority_list} "
                f"resolve to an available StorageClass. Update "
                f"storage_conf.volume_storage_class_priority to reference a "
                f"backend with a valid k8s_storage_class."
            )

        overrides = {
            common.HELM_NS_OPENSTACK: {
                'pod': {
                    'replicas': {
                        'server': self._num_provisioned_controllers()
                    },
                    'resources': {
                        'enabled': limit_enabled,
                        'prometheus_rabbitmq_exporter': {
                            'limits': {
                                'cpu': "%d000m" % (limit_cpus),
                                'memory': "%dMi" % (limit_mem_mib)
                            }
                        },
                        'server': {
                            'limits': {
                                'cpu': "%d000m" % (limit_cpus),
                                'memory': "%dMi" % (limit_mem_mib)
                            }
                        }
                    }
                },
                'io_thread_pool': {
                    'enabled': limit_enabled,
                    'size': "%d" % (io_thread_pool_size)
                },
                'endpoints': self._get_endpoints_overrides(),
                'manifests': {
                    'config_ipv6': self._is_ipv6_cluster_service()
                },
                'volume': {
                    'class_name': priority_storage_class,
                }
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
        credentials = self._get_endpoints_oslo_messaging_overrides(
            self.CHART, [])
        overrides = {
            'oslo_messaging': {
                'auth': {
                    'user': credentials['admin']
                }
            },
        }
        return overrides
