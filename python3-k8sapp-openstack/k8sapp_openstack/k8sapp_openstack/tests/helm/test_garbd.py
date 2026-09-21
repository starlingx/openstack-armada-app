#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import mock
from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm import common
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import garbd
from k8sapp_openstack.tests import test_plugins


class GarbdHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                        base.HelmTestCaseMixin):

    def setUp(self):
        super(GarbdHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)
        # _is_enabled() defers to the application level check first, and
        # that returns False when no system override record exists for
        # the chart. Seed one so the garbd specific topology logic is
        # what the assertions actually exercise.
        dbutils.create_test_helm_overrides(
            app_id=self.app.id,
            name=app_constants.HELM_CHART_GARBD,
            namespace=common.HELM_NS_OPENSTACK,
            system_overrides={common.HELM_CHART_ATTR_ENABLED: True})
        self.garbd = garbd.GarbdHelm(self.operator)

    def _chart_enabled(self):
        return self.garbd._is_enabled(self.app_name,
                                      app_constants.HELM_CHART_GARBD,
                                      common.HELM_NS_OPENSTACK)

    def _label_host(self, host, label_key,
                    label_value=common.LABEL_VALUE_ENABLED):
        dbutils.create_test_label(host_id=host.id,
                                  label_key=label_key,
                                  label_value=label_value)

    def _label_aio_controllers(self):
        """Assigns the compute label to every AIO controller.

        AIO controllers carry openstack-compute-node in addition to
        openstack-control-plane, so they are reported as OpenStack
        enabled compute nodes.
        """
        for host in self.hosts:
            if host.personality == constants.CONTROLLER:
                self._label_host(host, common.LABEL_COMPUTE_LABEL)

    def _add_worker(self, unit=0,
                    administrative=constants.ADMIN_UNLOCKED,
                    invprovision=constants.PROVISIONED,
                    compute_labelled=True):
        """Adds a dedicated worker host to the system.

        :param unit: host unit number, used to build the hostname
        :param administrative: administrative state of the host
        :param invprovision: provisioning state of the host
        :param compute_labelled: whether to assign the
            openstack-compute-node label to the host
        :returns: the created host object
        """
        worker = self._create_test_host(
            constants.WORKER,
            unit=unit,
            administrative=administrative,
            operational=constants.OPERATIONAL_ENABLED,
            availability=constants.AVAILABILITY_AVAILABLE,
            invprovision=invprovision)
        if compute_labelled:
            self._label_host(worker, common.LABEL_COMPUTE_LABEL)
        return worker

    def _mock_manifest_operator(self):
        return mock.Mock(
            APP=self.app_name,
            CHART_GROUPS_LUT={self.garbd.CHART: 'mariadb-chart-group'},
            CHARTS_LUT={self.garbd.CHART: 'garbd-chart'})


class GarbdGetOverrideTest(GarbdHelmTestCase,
                           dbbase.ControllerHostTestCase):
    def test_garbd_overrides(self):
        """
        Tests that no system overrides are generated for the supported
        namespace. The garbd chart is configured entirely through its
        static overrides, so the plugin contributes nothing here.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_GARBD,
            cnamespace=common.HELM_NS_OPENSTACK)
        self.assertEqual({}, overrides)

    def test_garbd_overrides_invalid_namespace(self):
        """
        Asserts that an exception is raised if an invalid namespace
        is given when retrieving Helm override parameters.
        """
        self.assertRaises(exception.InvalidHelmNamespace,
                          self.operator.get_helm_chart_overrides,
                          app_constants.HELM_CHART_GARBD,
                          cnamespace=common.HELM_NS_DEFAULT)

    def test_garbd_overrides_missing_namespace(self):
        """
        Tests that the default Helm override parameters
        are returned when no namespace is passed.
        """
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_GARBD)
        self.assertEqual({common.HELM_NS_OPENSTACK: {}}, overrides)


class GarbdAioSimplexEnablementTest(GarbdHelmTestCase,
                                 dbbase.AIOSimplexHostTestCase):
    def test_garbd_disabled_on_aio_simplex(self):
        """
        Asserts that garbd is disabled when fewer than 2 controllers
        exist. A single mariadb replica is deployed on AIO-SX, so there
        is no quorum to arbitrate.
        """
        self.assertFalse(self._chart_enabled())

    @mock.patch('k8sapp_openstack.utils.is_central_cloud',
                return_value=True)
    def test_garbd_enabled_on_central_cloud(self, *_):
        """
        Asserts that garbd is always enabled on a System Controller,
        regardless of the local topology. The chart must be enabled
        during "application-upload --images" so that all container
        images are downloaded for the subclouds.
        """
        self.assertTrue(self._chart_enabled())

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.'
                '_is_enabled', return_value=False)
    @mock.patch('k8sapp_openstack.utils.is_central_cloud',
                return_value=True)
    def test_garbd_enabled_on_central_cloud_when_user_disabled(self, *_):
        """
        Asserts that the Central Cloud check intentionally overrides the
        user's chart enablement.

        On a System Controller _is_enabled() doubles as "are this chart's
        images required", so it must return True even when the operator
        has disabled the chart, otherwise "application-upload --images"
        leaves the central registry incomplete and subclouds fail to
        apply. Applying the application on the System Controller itself
        is not a supported configuration, which is what makes ignoring
        the user's setting safe here.
        """
        self.assertTrue(self._chart_enabled())


class GarbdAioDuplexEnablementTest(GarbdHelmTestCase,
                                dbbase.ProvisionedAIODuplexSystemTestCase):
    def setUp(self):
        super(GarbdAioDuplexEnablementTest, self).setUp()
        self._label_aio_controllers()

    def test_garbd_disabled_on_pure_aio_duplex(self):
        """
        Asserts that garbd is disabled when no dedicated worker exists.

        Both AIO controllers are returned as OpenStack enabled compute
        nodes, since they report the worker subfunction and carry the
        openstack-compute-node label. They must be excluded by the
        personality check, otherwise garbd would run on a controller
        alongside mariadb and add no quorum benefit on node failure.
        """
        self.assertFalse(self._chart_enabled())

    def test_garbd_enabled_with_unlocked_openstack_worker(self):
        """
        Asserts that garbd is enabled on AIO-DX Plus, where a dedicated
        OpenStack worker is available to run it.
        """
        self._add_worker()
        self.assertTrue(self._chart_enabled())

    def test_garbd_disabled_with_unprovisioned_worker(self):
        """
        Asserts that garbd is disabled while a worker is still
        unprovisioned.

        An UNPROVISIONED host is not reported as an OpenStack enabled
        compute node at all, so it cannot satisfy the worker check even
        though the openstack-compute-node label is present. The host is
        deliberately left unlocked, which is not a state the system
        produces on its own, so that the provisioning filter is the only
        thing that can gate this case. The administrative state check is
        covered by test_garbd_disabled_with_worker_locked_for_maintenance
        below.
        """
        self._add_worker(administrative=constants.ADMIN_UNLOCKED,
                         invprovision=constants.UNPROVISIONED)
        self.assertFalse(self._chart_enabled())

    def test_garbd_disabled_with_worker_locked_for_maintenance(self):
        """
        Asserts that garbd is disabled when the only worker is locked.

        invprovision remains PROVISIONED across a lock, so the host is
        still returned as an OpenStack enabled compute node. Without the
        administrative state check garbd would stay enabled with no
        schedulable node and the application apply would fail.
        """
        self._add_worker(administrative=constants.ADMIN_LOCKED)
        self.assertFalse(self._chart_enabled())

    def test_garbd_disabled_with_worker_missing_compute_label(self):
        """
        Asserts that garbd is disabled for a worker that is not an
        OpenStack compute node. Such a host cannot satisfy the garbd
        nodeSelector, so the chart must not be enabled.
        """
        self._add_worker(compute_labelled=False)
        self.assertFalse(self._chart_enabled())

    def test_garbd_enabled_with_one_of_two_workers_unlocked(self):
        """
        Asserts that a single unlocked worker is sufficient to enable
        garbd when another worker is locked.
        """
        self._add_worker(unit=0, administrative=constants.ADMIN_LOCKED)
        self._add_worker(unit=1)
        self.assertTrue(self._chart_enabled())

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.'
                '_is_enabled', return_value=False)
    def test_garbd_disabled_at_application_level(self, *_):
        """
        Asserts that the topology checks are skipped when the chart has
        been disabled at the application level, on a system that would
        otherwise enable garbd.
        """
        self._add_worker()
        self.assertFalse(self._chart_enabled())


class GarbdChartUpdatesTest(GarbdHelmTestCase,
                            dbbase.ProvisionedAIODuplexSystemTestCase):
    def setUp(self):
        super(GarbdChartUpdatesTest, self).setUp()
        self._label_aio_controllers()
        self._add_worker()

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.'
                '_is_enabled', return_value=False)
    def test_execute_manifest_updates_removes_disabled_chart(self, *_):
        """
        Asserts that a disabled garbd is removed from the mariadb chart
        group on application load.
        """
        operator = self._mock_manifest_operator()
        self.garbd.execute_manifest_updates(operator)
        operator.chart_group_chart_delete.assert_called_once_with(
            'mariadb-chart-group', 'garbd-chart')

    def test_execute_manifest_updates_keeps_enabled_chart(self):
        """
        Asserts that an enabled garbd is left in the mariadb chart group
        on application load.
        """
        operator = self._mock_manifest_operator()
        self.garbd.execute_manifest_updates(operator)
        operator.chart_group_chart_delete.assert_not_called()

    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm.'
                '_is_enabled', return_value=False)
    def test_execute_kustomize_updates_removes_disabled_resource(self, *_):
        """
        Asserts on the deletion of the HelmRelease resource when garbd
        is disabled.
        """
        operator = mock.Mock(APP=self.app_name)
        self.garbd.execute_kustomize_updates(operator)
        operator.helm_release_resource_delete.assert_called_once_with(
            self.garbd.HELM_RELEASE)

    def test_execute_kustomize_updates_keeps_enabled_resource(self):
        """
        Asserts that the HelmRelease resource is retained when garbd is
        enabled.
        """
        operator = mock.Mock(APP=self.app_name)
        self.garbd.execute_kustomize_updates(operator)
        operator.helm_release_resource_delete.assert_not_called()


class GarbdChartUpdatesNoWorkerTest(
        GarbdHelmTestCase,
        dbbase.ProvisionedAIODuplexSystemTestCase):
    """Chart and resource removal driven by the AIO-DX topology check.

    No dedicated worker exists, so _is_enabled() returns False on its own
    and the removal happens without the chart being disabled by the user.
    """

    def setUp(self):
        super(GarbdChartUpdatesNoWorkerTest, self).setUp()
        self._label_aio_controllers()

    def test_execute_manifest_updates_removes_chart_on_pure_aio_duplex(self):
        """
        Asserts that garbd is removed from the mariadb chart group on a
        pure AIO-DX, where no worker is available to run it.
        """
        operator = self._mock_manifest_operator()
        self.garbd.execute_manifest_updates(operator)
        operator.chart_group_chart_delete.assert_called_once_with(
            'mariadb-chart-group', 'garbd-chart')

    def test_execute_kustomize_updates_removes_resource_on_pure_aio_duplex(
            self):
        """
        Asserts that the HelmRelease resource is removed on a pure AIO-DX,
        where no worker is available to run garbd.
        """
        operator = mock.Mock(APP=self.app_name)
        self.garbd.execute_kustomize_updates(operator)
        operator.helm_release_resource_delete.assert_called_once_with(
            self.garbd.HELM_RELEASE)


class GarbdStandardEnablementTest(GarbdHelmTestCase,
                               dbbase.ControllerHostTestCase):
    def setUp(self):
        super(GarbdStandardEnablementTest, self).setUp()
        self.host2 = self._create_test_host(
            constants.CONTROLLER,
            unit=1,
            administrative=constants.ADMIN_UNLOCKED,
            operational=constants.OPERATIONAL_ENABLED,
            availability=constants.AVAILABILITY_AVAILABLE,
            invprovision=constants.PROVISIONED)
        self._label_host(self.host2, common.LABEL_CONTROLLER)

    def test_garbd_enabled_on_standard(self):
        """
        Asserts that garbd remains enabled on Standard, as it was before
        the AIO-DX Plus support was added. Standard controllers are not
        compute labelled, so garbd is kept off the mariadb nodes by its
        nodeSelector alone and the AIO-DX specific worker check does not
        apply.
        """
        self.assertTrue(self._chart_enabled())
