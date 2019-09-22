#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import constants
from sysinv.helm import common
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm.test_helm import HelmOperatorTestSuiteMixin


class K8SAppOpenstackAppMixin(object):
    app_name = constants.HELM_APP_OPENSTACK
    path_name = app_name + '.tgz'

    def setUp(self):
        super(K8SAppOpenstackAppMixin, self).setUp()
        # Label hosts with appropriate labels
        for host in self.hosts:
            if host.personality == constants.CONTROLLER:
                dbutils.create_test_label(
                    host_id=host.id,
                    label_key=common.LABEL_CONTROLLER,
                    label_value=common.LABEL_VALUE_ENABLED)
            elif host.personality == constants.WORKER:
                dbutils.create_test_label(
                    host_id=host.id,
                    label_key=common.LABEL_COMPUTE_LABEL,
                    label_value=common.LABEL_VALUE_ENABLED)


# Test Configuration:
# - Controller
# - IPv6
# - Ceph Storage
# - stx-openstack app
class K8SAppOpenstackControllerTestCase(K8SAppOpenstackAppMixin,
                                        dbbase.BaseIPv6Mixin,
                                        dbbase.BaseCephStorageBackendMixin,
                                        HelmOperatorTestSuiteMixin,
                                        dbbase.ControllerHostTestCase):
    pass


# Test Configuration:
# - AIO
# - IPv4
# - Ceph Storage
# - stx-openstack app
class K8SAppOpenstackAIOTestCase(K8SAppOpenstackAppMixin,
                                 dbbase.BaseCephStorageBackendMixin,
                                 HelmOperatorTestSuiteMixin,
                                 dbbase.AIOSimplexHostTestCase):
    pass
