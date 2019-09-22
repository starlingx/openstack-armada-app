#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.tests import test_plugins

import tsconfig.tsconfig as tsc
from sysinv.helm import common

from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base


class CinderConversionTestCase(test_plugins.K8SAppOpenstackAppMixin,
                               base.HelmTestCaseMixin):
    def setUp(self):
        super(CinderConversionTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class CinderGetOverrideTest(CinderConversionTestCase,
                            dbbase.ControllerHostTestCase):
    def test_cinder_overrides(self):
        dbutils.create_test_host_fs(name='image-conversion',
                                    forihostid=self.host.id)
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_CINDER,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertOverridesParameters(overrides, {
            'conf': {
                'cinder': {
                    'DEFAULT': {
                        'image_conversion_dir': tsc.IMAGE_CONVERSION_PATH}}}
        })
