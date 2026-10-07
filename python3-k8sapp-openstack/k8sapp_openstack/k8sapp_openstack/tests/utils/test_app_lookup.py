#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import constants
from sysinv.common import exception
from sysinv.tests.db import base
from sysinv.tests.db import utils as dbutils

from k8sapp_openstack import utils as app_utils
from k8sapp_openstack.common import constants as app_constants


class TestFindOpenstackApp(base.DbTestCase):

    def test_reads_current_overrides_after_upgrade(self):
        old_app = dbutils.create_test_app(
            name='wr-openstack', app_version='26.03-0',
            status=constants.APP_INACTIVE_STATE, active=True)
        current_app = dbutils.create_test_app(
            name='wr-openstack', app_version='26.10-0',
            status=constants.APP_APPLY_SUCCESS, active=True)
        dbutils.create_test_helm_overrides(
            app_id=old_app.id, name=app_constants.HELM_CHART_CINDER,
            namespace=app_constants.HELM_NS_OPENSTACK,
            user_overrides='feature:\n  value: old')
        dbutils.create_test_helm_overrides(
            app_id=current_app.id, name=app_constants.HELM_CHART_CINDER,
            namespace=app_constants.HELM_NS_OPENSTACK,
            user_overrides='feature:\n  value: current')

        self.assertEqual(current_app.id,
                         app_utils.find_openstack_app(self.dbapi).id)
        self.assertEqual(
            'current', app_utils._get_value_from_application(
                'default', app_constants.HELM_CHART_CINDER,
                'feature.value'))
        self.assertEqual(
            old_app.id,
            self.dbapi.kube_app_get_inactive('wr-openstack')[0].id)

    def test_finds_downstream_app_during_upgrade(self):
        dbutils.create_test_app(
            name='wr-openstack', app_version='26.03-0',
            status=constants.APP_INACTIVE_STATE)
        current_app = dbutils.create_test_app(
            name='wr-openstack', app_version='26.10-0',
            status=constants.APP_UPDATE_IN_PROGRESS)

        self.assertEqual(current_app.id,
                         app_utils.find_openstack_app(self.dbapi).id)

    def test_accepts_stx_openstack_name(self):
        app = dbutils.create_test_app(
            name='stx-openstack', app_version='26.10-0',
            status=constants.APP_APPLY_SUCCESS)

        self.assertEqual(app.id, app_utils.find_openstack_app(self.dbapi).id)

    def test_only_inactive_app_is_not_found(self):
        dbutils.create_test_app(
            name='wr-openstack', app_version='26.03-0',
            status=constants.APP_INACTIVE_STATE)

        self.assertRaises(exception.KubeAppNotFound,
                          app_utils.find_openstack_app, self.dbapi)
