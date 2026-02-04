
import mock
from sysinv.common import exception
from sysinv.helm import common
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import rabbitmq
from k8sapp_openstack.tests import test_plugins


class RabbitmqHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                           base.HelmTestCaseMixin):
    def setUp(self):
        super(RabbitmqHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class RabbitmqGetOverridesTest(RabbitmqHelmTestCase,
                               dbbase.ControllerHostTestCase):
    class Dummy(object):

        """
        This is a class to gather the responsibilities of formatting mocks for these test cases,
        and avoid changing the get_overrides function or its return, and even methods called inside
        its context, to demand refactoring on every test function.
        """

        # 1st, 2nd, 3rd TEST - mocking arbitrary variables
    # Values:
        LIMIT_ENABLED, LIMIT_CPUS, LIMIT_MEM_MIB = [True, 20, 30]
        IO_THERAD_POOL_SIZE = LIMIT_CPUS * 16
        VALID_NAMESPACE = common.HELM_NS_OPENSTACK
        INVALID_NAMESPACE = 'INVALID_NAMESPACE'
        PRIORITY_STORAGE_CLASS = "ceph-rbd"

    # Functions:
        GET_PLATFORM_RES_LIMIT_RETURN = {
            LIMIT_ENABLED, LIMIT_CPUS, LIMIT_MEM_MIB}
        GET_AVAILABLE_VOLUME_BACKENDS_RETURN = {
            "ceph": PRIORITY_STORAGE_CLASS,
            "netapp-nfs": "netapp-nas-backend",
            # string value empty if backend for given key not available
            "netapp-iscsi": "netapp-nas-backend",
            "netapp-fc": "netapp-fc-backend"
        }
        GET_STORAGE_BACKENDS_PRIORITY_LIST_RETURN = [
            "ceph", "netapp-nfs", "netapp-iscsi", "nestapp-fc"]
        NUM_PROVISIONED_CONTOLLERS_RETURN = 2
        GET_ENDPOINTS_OSLO_MESSAGING_OVERRIDES = {
            'admin': {
                'username': 'rabbitmq-admin',
                'password': 'COMMON_PASSWORD_test'
            }
        }
        ENDPOINTS_OVERRIDES_RETURN = {
            'oslo_messaging': {
                'auth': {
                    'user': GET_ENDPOINTS_OSLO_MESSAGING_OVERRIDES['admin']
                }
            },
        }
        IS_IPV6_RETURN = True

    # Override for given values and returns:
        EXPECTED_OVERRIDE_VALID_NAMESPACE = {
            'pod': {
                'replicas': {
                    'server': NUM_PROVISIONED_CONTOLLERS_RETURN
                },
                'resources': {
                    'enabled': LIMIT_ENABLED,
                    'prometheus_rabbitmq_exporter': {
                        'limits': {
                            'cpu': "%d000m" % (LIMIT_CPUS),
                            'memory': "%dMi" % (LIMIT_MEM_MIB)
                        }
                    },
                    'server': {
                        'limits': {
                            'cpu': "%d000m" % (LIMIT_CPUS),
                            'memory': "%dMi" % (LIMIT_MEM_MIB)
                        }
                    }
                }
            },
            'io_thread_pool': {
                'enabled': LIMIT_ENABLED,
                'size': "%d" % (IO_THERAD_POOL_SIZE)
            },
            'endpoints': ENDPOINTS_OVERRIDES_RETURN,
            'manifests': {
                'config_ipv6': IS_IPV6_RETURN
            },
            'volume': {
                'class_name': PRIORITY_STORAGE_CLASS,
            }
        }
        EXPECTED_OVERRIDE_MISSING_NAMESPACE = {
            VALID_NAMESPACE: EXPECTED_OVERRIDE_VALID_NAMESPACE}

    """
     1°, 2° and 3° Test for get_overrides function,
     They cover the following cases:

        - called with a valid namespace (namespace='openstack')
        - called with missing namespace
        - called with an invalid namespace.

        Mocks:
            - '_get_platform_res_limit', return_value = [True, 20, 30]
            - 'get_available_volume_backends', return_value = {
                    "ceph": "ceph-rbd",  # string empty if backend for given key is not available
                    "netapp-nfs": "netapp-nas-backend",
                    "netapp-iscsi": "netapp-nas-backend",
                    "netapp-fc": "netapp-fc-backend"
                    }
            - 'get_storage_backends_priority_list', return_value = [
                    "ceph",
                    "netapp-nfs",
                    "netapp-iscsi",
                    "nestapp-fc"
                    ]
            - '_num_provisioned_controllers', return_value = 2
            - '_get_endpoints_overrides', return_value = {
                    'oslo_messaging': {
                        'auth': {
                            'user': {
                                'admin': {
                                    'username': 'rabbitmq-admin',
                                    'password': 'COMMON_PASSWORD_test'
                                }
                            }
                        }
                    },
                }
            - '_is_ipv6_cluster_service', return_value = True
    """

    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm._get_platform_res_limit',
                return_value=Dummy.GET_PLATFORM_RES_LIMIT_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.get_available_volume_backends',
                return_value=Dummy.GET_AVAILABLE_VOLUME_BACKENDS_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.get_storage_backends_priority_list',
                return_value=Dummy.GET_STORAGE_BACKENDS_PRIORITY_LIST_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm._num_provisioned_controllers',
                return_value=Dummy.NUM_PROVISIONED_CONTOLLERS_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm.'
                '_get_endpoints_oslo_messaging_overrides',
                return_value=Dummy.GET_ENDPOINTS_OSLO_MESSAGING_OVERRIDES)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm._is_ipv6_cluster_service',
                return_value=Dummy.IS_IPV6_RETURN)
    def test_rabbitmq_get_overrides_valid_namespace(self, *_):
        """
        Asserts that the given valid namespace passed as a parameter,
        returns only the values of the namespace element.
        """

        # ACT
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_RABBITMQ,
            self.Dummy.VALID_NAMESPACE
        )

        # ASSERTS
        assert common.HELM_NS_OPENSTACK not in overrides
        self.assertOverridesParameters(
            overrides,
            self.Dummy.EXPECTED_OVERRIDE_VALID_NAMESPACE
        )

    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm._get_platform_res_limit',
                return_value=Dummy.GET_PLATFORM_RES_LIMIT_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.get_available_volume_backends',
                return_value=Dummy.GET_AVAILABLE_VOLUME_BACKENDS_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.get_storage_backends_priority_list',
                return_value=Dummy.GET_STORAGE_BACKENDS_PRIORITY_LIST_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm._num_provisioned_controllers',
                return_value=Dummy.NUM_PROVISIONED_CONTOLLERS_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm.'
                '_get_endpoints_oslo_messaging_overrides',
                return_value=Dummy.GET_ENDPOINTS_OSLO_MESSAGING_OVERRIDES)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm._is_ipv6_cluster_service',
                return_value=Dummy.IS_IPV6_RETURN)
    def test_rabbitmq_get_overrides_missing_namespace(self, *_):
        """
        Asserts that the default Helm override parameters
        are returned when no namespace is gives as parameters for get_overrides function.
        """

        # ACT
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_RABBITMQ
        )

        # ASSERTS
        assert common.HELM_NS_OPENSTACK in overrides
        self.assertOverridesParameters(
            overrides,
            self.Dummy.EXPECTED_OVERRIDE_MISSING_NAMESPACE
        )

    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm._get_platform_res_limit',
                return_value=Dummy.GET_PLATFORM_RES_LIMIT_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.get_available_volume_backends',
                return_value=Dummy.GET_AVAILABLE_VOLUME_BACKENDS_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.get_storage_backends_priority_list',
                return_value=Dummy.GET_STORAGE_BACKENDS_PRIORITY_LIST_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm._num_provisioned_controllers',
                return_value=Dummy.NUM_PROVISIONED_CONTOLLERS_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm.'
                '_get_endpoints_oslo_messaging_overrides',
                return_value=Dummy.GET_ENDPOINTS_OSLO_MESSAGING_OVERRIDES)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm._is_ipv6_cluster_service',
                return_value=Dummy.IS_IPV6_RETURN)
    def test_rabbitmq_get_overrides_invalid_namespace(self, *_):
        """
        Asserts that an exception is raised if an invalid namespace
        is given when retrieving Helm override parameters.
        """
        self.assertRaises(exception.InvalidHelmNamespace,
                          self.operator.get_helm_chart_overrides,
                          app_constants.HELM_CHART_RABBITMQ,
                          cnamespace=self.Dummy.INVALID_NAMESPACE
                          )

    """
    4, 5 and 6th Test for get_overrides function, called with '_get_platform_res_limit.return_value'
    ranging different values to cover all execution flows and conditions based of the return of this
    method.
        Mocks:
            - 'get_available_volume_backends', return_value = {
                    "ceph": "ceph-rbd",   # string empty if backend for given key is not available
                    "netapp-nfs": "netapp-nas-backend",
                    "netapp-iscsi": "netapp-nas-backend",
                    "netapp-fc": "netapp-fc-backend"
                    }
            - 'get_storage_backends_priority_list', return_value = [
                    "ceph",
                    "netapp-nfs",
                    "netapp-iscsi",
                    "nestapp-fc"
                    ]
            - '_num_provisioned_controllers', return_value = 2
            - '_get_endpoints_overrides', return_value = {
                    'oslo_messaging': {
                        'auth': {
                            'user': {
                                'admin': {
                                    'username': 'rabbitmq-admin',
                                    'password': 'COMMON_PASSWORD_test'
                                }
                            }
                        }
                    },
                }
            - '_is_ipv6_cluster_service', return_value = True
    """

    @mock.patch('k8sapp_openstack.helm.rabbitmq.get_available_volume_backends',
                return_value=Dummy.GET_AVAILABLE_VOLUME_BACKENDS_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.get_storage_backends_priority_list',
                return_value=Dummy.GET_STORAGE_BACKENDS_PRIORITY_LIST_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm._num_provisioned_controllers',
                return_value=Dummy.NUM_PROVISIONED_CONTOLLERS_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm.'
                '_get_endpoints_oslo_messaging_overrides',
                return_value=Dummy.GET_ENDPOINTS_OSLO_MESSAGING_OVERRIDES)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm._is_ipv6_cluster_service',
                return_value=Dummy.IS_IPV6_RETURN)
    def test_rabbitmq_get_overrides_for_different_get_platform_res_limit_return_values(self, *_):
        # Cases for 4,5,6th test:
        # each case object is composed by:
        # - list with mock values for _get_platform_res_limit.return_value
        # - expected value for io_thread_pool_size
        """
        Asserts if rabbitmq overrides for io_thread_pool_size are loaded correctly when:
            - (limit_cpus < 64)
            - (64 < limit_cpus < 1024)
            - (1024 < limit_cpus)
        """

        cases = [
            {
                "returned_values": [True, 3, 3],
                "expected_override": 64
            },
            {
                "returned_values": [False, 50, 60],
                "expected_override": 800
            },
            {
                "returned_values": [True, 100, 100],
                "expected_override": 1024
            }
        ]

        for index, case in enumerate(cases, start=1):

            # ARRANGE
            limit_enabled, limit_cpus, limit_mem_mib = case["returned_values"]
            expected_value_for_io_thread_pool_size = case["expected_override"]

            with mock.patch.object(
                rabbitmq.RabbitmqHelm,
                '_get_platform_res_limit',
                    return_value=(limit_enabled, limit_cpus, limit_mem_mib)):

                # ACT
                overrides = self.operator.get_helm_chart_overrides(
                    app_constants.HELM_CHART_RABBITMQ
                )

                try:
                    # ASSERTS
                    self.assertOverridesParameters(overrides, {
                        common.HELM_NS_OPENSTACK: {
                            'pod': {
                                'replicas': {
                                    'server': self.Dummy.NUM_PROVISIONED_CONTOLLERS_RETURN
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
                                'size': "%d" % (expected_value_for_io_thread_pool_size)
                            },
                            'endpoints': self.Dummy.ENDPOINTS_OVERRIDES_RETURN,
                            'manifests': {
                                'config_ipv6': self.Dummy.IS_IPV6_RETURN
                            },
                            'volume': {
                                'class_name': self.Dummy.PRIORITY_STORAGE_CLASS,
                            }
                        }
                    })
                except AssertionError as e:   # pragma: no cover
                    self.fail(
                        f"Failed in {index}th case(values = {case['returned_values']}): {e}"
                    )  # pragma: no cover

    """
    7th,8th and 9th Test for get_overrides function, called with 3 different
    cases and values for 'get_available_volume_backends.return_value' and
    'get_storage_backends_priority_list.return_value', in order to cover all
    execution flows and conditions based of the return of this method.
        Mocks:
            - '_get_platform_res_limit', return_value = [True, 20, 30]
            - '_num_provisioned_controllers', return_value = 2
            - '_get_endpoints_overrides', return_value = {
                    'oslo_messaging': {
                        'auth': {
                            'user': {
                                'admin': {
                                    'username': 'rabbitmq-admin',
                                    'password': 'COMMON_PASSWORD_test'
                                }
                            }
                        }
                    },
                }
            - '_is_ipv6_cluster_service', return_value = True
    """

    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm._get_platform_res_limit',
                return_value=Dummy.GET_PLATFORM_RES_LIMIT_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm._num_provisioned_controllers',
                return_value=Dummy.NUM_PROVISIONED_CONTOLLERS_RETURN)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm.'
                '_get_endpoints_oslo_messaging_overrides',
                return_value=Dummy.GET_ENDPOINTS_OSLO_MESSAGING_OVERRIDES)
    @mock.patch('k8sapp_openstack.helm.rabbitmq.RabbitmqHelm._is_ipv6_cluster_service',
                return_value=Dummy.IS_IPV6_RETURN)
    def test_rabbitmq_get_overrides_for_different_available_volume_backends(self, *_):
        # Cases for 7,8 and 9th test:
        # each case object is composed by:
        # - dictionary with mock values for get_available_volume_backends.return_value
        # - list with mock values for get_storage_backends_priority_list.return_value
        # - expected value for priority_storage_class
        """
        Asserts if rabbitmq overrides for priority_storage_class are loaded correctly when:
            - all volume backends are available and matches a storage class in the prioritylist
            - not all volume backends are available, but still matches a storage class from the
            priority list
            - even with available backends, can't match a storage classe in the list, returns
            'general" as it is the default storage class value
        """

        cases = [
            {
                "available_backends": {
                    "ceph": "ceph-rbd",
                    "netapp-nfs": "netapp-nas-backend",
                    "netapp-iscsi": "netapp-nas-backend",
                    "netapp-fc": "netapp-fc-backend"
                },
                "backends_priority_list": ["ceph", "netapp-nfs", "netapp-iscsi", "nestapp-fc"],
                "expected_override": "ceph-rbd"
            },
            {
                "available_backends": {
                    "ceph": "",
                    "netapp-nfs": "netapp-nas-backend",
                    "netapp-iscsi": "netapp-nas-backend",
                    "netapp-fc": "netapp-fc-backend"
                },
                "backends_priority_list": ["ceph", "netapp-nfs", "netapp-iscsi", "nestapp-fc"],
                "expected_override": "netapp-nas-backend"
            },
            {
                "available_backends": {
                    "ceph": "ceph-rbd",
                    "netapp-nfs": "netapp-nas-backend",
                    "netapp-iscsi": "netapp-nas-backend",
                    "netapp-fc": "netapp-fc-backend"
                },
                "backends_priority_list": ["ramdom-backend-1", "ramdom-backend-2"],
                "expected_override": "general"
            },
        ]

        for index, case in enumerate(cases, start=1):

            # ARRANGE
            mocked_availabe_backends = case["available_backends"]
            mocked_backends_priority_list = case["backends_priority_list"]
            expected_storage_class = case["expected_override"]

            with mock.patch.object(
                rabbitmq,
                'get_available_volume_backends',
                return_value=(mocked_availabe_backends)), \
                mock.patch.object(
                    rabbitmq,
                    'get_storage_backends_priority_list',
                    return_value=(mocked_backends_priority_list)):

                # ACT
                overrides = self.operator.get_helm_chart_overrides(
                    app_constants.HELM_CHART_RABBITMQ
                )

                try:
                    # ASSERTS
                    self.assertOverridesParameters(
                        overrides['openstack']['volume'],
                        {'class_name': expected_storage_class, }
                    )
                except AssertionError as e:  # pragma: no cover
                    self.fail(
                        f"Failed in {index}th case(values = {case}): {e}")  # pragma: no cover
