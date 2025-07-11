#
# Copyright (c) 2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import unittest
from unittest import mock

from sysinv.common import constants

from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.kustomize.kustomize_openstack import OpenstackFluxCDKustomizeOperator


class TestOpenstackFluxCDKustomizeOperator(unittest.TestCase):

    def setUp(self):
        super(TestOpenstackFluxCDKustomizeOperator, self).setUp()
        self.fluxCDKustomizeOperator = OpenstackFluxCDKustomizeOperator()

    def test_manifest_chart_groups_disable(self, *_):
        """ Tests the manifest_chart_groups_disable method
        Guarantees that it changes "enabled" to False on system overrides and
        that updates the helm overrides with the new value
        """
        app_id = 'app_id'
        kube_app_get_endswith_return_value = mock.Mock()
        kube_app_get_endswith_return_value.id = app_id
        kube_app_get_endswith = mock.Mock()
        kube_app_get_endswith.return_value = kube_app_get_endswith_return_value

        db_helm_override = mock.Mock(
            system_overrides={'enabled': True}
        )
        helm_override_get = mock.Mock()
        helm_override_get.return_value = db_helm_override

        chart = {}
        dbapi = mock.Mock(
            kube_app_get_endswith=kube_app_get_endswith,
            helm_override_get=helm_override_get,
            helm_override_update=mock.Mock(),
        )
        namespace = 'namespace'
        self.fluxCDKustomizeOperator.manifest_chart_groups_disable(dbapi, namespace, chart)

        dbapi.kube_app_get_endswith.assert_called_once_with(self.fluxCDKustomizeOperator.APP)
        dbapi.helm_override_get.assert_called_once_with(app_id, chart, namespace)
        self.assertEqual(db_helm_override.system_overrides['enabled'], False)
        dbapi.helm_override_update.assert_called_once_with(
            app_id, chart, namespace,
            {app_constants.HELM_OVERRIDE_GROUP_SYSTEM: db_helm_override.system_overrides}
        )

    def test_chart_remove(self, *_):
        """ Tests chart_remove method, just checks if the expected
        calls are present
        """
        self.fluxCDKustomizeOperator.helm_release_resource_delete = mock.Mock()
        self.fluxCDKustomizeOperator.manifest_chart_groups_disable = mock.Mock()

        chart = {}
        dbapi = mock.Mock()
        namespace = 'namespace'

        self.fluxCDKustomizeOperator.chart_remove(dbapi, namespace, chart)

        self.fluxCDKustomizeOperator.helm_release_resource_delete.assert_called_once_with(chart)
        self.fluxCDKustomizeOperator.manifest_chart_groups_disable.assert_called_once_with(dbapi, namespace, chart)

    def test_enable_helmrelease_resource(self, *_):
        """ Tests the enable_helmrelease_resource method
        It guarantees that the resources are added to the maps and then removed
        from the cleanup list
        """
        resource_name = 'test_resource'
        secondary_resource = {
            'name': 'test_resource_2',
            'namespace': app_constants.HELM_NS_OPENSTACK,
        }
        self.fluxCDKustomizeOperator.kustomization_resources = []
        self.fluxCDKustomizeOperator.helmrelease_cleanup = [
            {
                'name': resource_name,
                'namespace': app_constants.HELM_NS_OPENSTACK,
            },
            secondary_resource,
        ]
        self.fluxCDKustomizeOperator.enable_helmrelease_resource(resource_name)

        expected_resources = [resource_name]

        self.assertEqual(self.fluxCDKustomizeOperator.kustomization_resources, expected_resources)
        self.assertEqual(self.fluxCDKustomizeOperator.helmrelease_cleanup, [secondary_resource])

    def test_set_helm_releases(self, *_):
        """ Tests the set_helm_releases method
        It guarantees that if the resource is an active resource and
        not in the helm_charts_list param, it is removed.
        Also checks that the resource is enabled if it is in the helm_charts_list
        param and also in cleaned resources but not on the list of active resources
        """
        dbapi = mock.Mock()
        namespace = None
        helm_charts_list = ['test_resource', 'test_resource_3']

        resources = [
            {
                'name': 'test_resource',
                'namespace': app_constants.HELM_NS_OPENSTACK,
            },
            {
                'name': 'test_resource_2',
                'namespace': app_constants.HELM_NS_OPENSTACK,
            },
            {
                'name': 'test_resource_3',
                'namespace': app_constants.HELM_NS_OPENSTACK,
            },
        ]

        self.fluxCDKustomizeOperator.helmrelease_cleanup = [
            resources[0],
            resources[1],
            resources[2],
        ]

        self.fluxCDKustomizeOperator.helmrelease_resource_map = {
            'test_resource': 'r1',
            'test_resource_2': 'r2',
        }

        self.fluxCDKustomizeOperator.chart_remove = mock.Mock()
        self.fluxCDKustomizeOperator.enable_helmrelease_resource = mock.Mock()

        self.fluxCDKustomizeOperator.set_helm_releases(dbapi, namespace, helm_charts_list)

        self.fluxCDKustomizeOperator.chart_remove.assert_called_once_with(
            dbapi, app_constants.HELM_NS_OPENSTACK, resources[1]['name'])

        self.fluxCDKustomizeOperator.enable_helmrelease_resource.assert_called_once_with(resources[2]['name'])

    def test_platform_mode_kustomize_updates__mode_none(self, *_):
        """ Tests the platform_mode_kustomize_updates with mode being None
        Also considers the resources_before_restore being empty and not empty.
        If it is not empty, it should call set_helm_releases passing it as param, and if
        empty, it should not have called set_helm_releases.
        Aside from that, if system.distributed_cloud_role is "DISTRIBUTED_CLOUD_ROLE_SYSTEMCONTROLLER
        it should call chart_remove for all apps listed in the class app groups.
        """
        mode = None
        dbapi = mock.Mock()

        system = mock.Mock(
            distributed_cloud_role=None,
        )
        dbapi.isystem_get_one = mock.Mock(return_value=system)

        self.fluxCDKustomizeOperator.set_helm_releases = mock.Mock()
        self.fluxCDKustomizeOperator.chart_remove = mock.Mock()

        self.fluxCDKustomizeOperator.platform_mode_kustomize_updates(dbapi, mode)
        self.fluxCDKustomizeOperator.set_helm_releases.assert_not_called()

        resources_before_restore = ['test']
        self.fluxCDKustomizeOperator.resources_before_restore = resources_before_restore
        self.fluxCDKustomizeOperator.platform_mode_kustomize_updates(dbapi, mode)
        self.fluxCDKustomizeOperator.set_helm_releases.assert_called_once_with(
            dbapi, app_constants.HELM_NS_OPENSTACK, resources_before_restore)

        self.fluxCDKustomizeOperator.chart_remove.assert_not_called()

        system = mock.Mock(
            distributed_cloud_role=constants.DISTRIBUTED_CLOUD_ROLE_SYSTEMCONTROLLER,
        )
        dbapi.isystem_get_one = mock.Mock(return_value=system)
        self.fluxCDKustomizeOperator.platform_mode_kustomize_updates(dbapi, mode)

        releases = (
            self.fluxCDKustomizeOperator.APP_GROUP_SWIFT +
            self.fluxCDKustomizeOperator.APP_GROUP_COMPUTE_KIT +
            self.fluxCDKustomizeOperator.APP_GROUP_HEAT +
            self.fluxCDKustomizeOperator.APP_GROUP_TELEMETRY
        )

        calls = []
        for release in releases:
            calls.append(mock.call(dbapi, app_constants.HELM_NS_OPENSTACK, release))

        self.fluxCDKustomizeOperator.chart_remove.assert_has_calls(calls)

    def test_platform_mode_kustomize_updates(self, *_):
        """ Tests the other cenarios of platform_mode_kustomize_updates method
        mode could be OPENSTACK_RESTORE_DB or OPENSTACK_RESTORE_STORAGE.
        It guarantess that the expected release list is passed as param of
        set_helm_releases for each case. It also consider the conditionals where
        resources_before_restore is filled with specific values.
        """
        test_cases = [
            {
                'mode': constants.OPENSTACK_RESTORE_DB,
                'resources_before_restore': [],
                'release_list': [
                    app_constants.FLUXCD_HELMRELEASE_INGRESS,
                    app_constants.FLUXCD_HELMRELEASE_NGINX_PORTS_CONTROL,
                    app_constants.FLUXCD_HELMRELEASE_MARIADB,
                ],
            },
            {
                'mode': constants.OPENSTACK_RESTORE_DB,
                'resources_before_restore': [
                    app_constants.FLUXCD_HELMRELEASE_GARBD
                ],
                'release_list': [
                    app_constants.FLUXCD_HELMRELEASE_INGRESS,
                    app_constants.FLUXCD_HELMRELEASE_NGINX_PORTS_CONTROL,
                    app_constants.FLUXCD_HELMRELEASE_MARIADB,
                    app_constants.FLUXCD_HELMRELEASE_GARBD,
                ],
            },
            {
                'mode': constants.OPENSTACK_RESTORE_STORAGE,
                'resources_before_restore': [],
                'release_list': [
                    app_constants.FLUXCD_HELMRELEASE_INGRESS,
                    app_constants.FLUXCD_HELMRELEASE_NGINX_PORTS_CONTROL,
                    app_constants.FLUXCD_HELMRELEASE_MARIADB,
                    app_constants.FLUXCD_HELMRELEASE_MEMCACHED,
                    app_constants.FLUXCD_HELMRELEASE_RABBITMQ,
                    app_constants.FLUXCD_HELMRELEASE_KEYSTONE,
                    app_constants.FLUXCD_HELMRELEASE_GLANCE,
                    app_constants.FLUXCD_HELMRELEASE_CINDER,
                ],
            },
            {
                'mode': constants.OPENSTACK_RESTORE_STORAGE,
                'resources_before_restore': [
                    app_constants.FLUXCD_HELMRELEASE_GARBD,
                    app_constants.FLUXCD_HELMRELEASE_KEYSTONE_API_PROXY,
                ],
                'release_list': [
                    app_constants.FLUXCD_HELMRELEASE_INGRESS,
                    app_constants.FLUXCD_HELMRELEASE_NGINX_PORTS_CONTROL,
                    app_constants.FLUXCD_HELMRELEASE_MARIADB,
                    app_constants.FLUXCD_HELMRELEASE_MEMCACHED,
                    app_constants.FLUXCD_HELMRELEASE_RABBITMQ,
                    app_constants.FLUXCD_HELMRELEASE_KEYSTONE,
                    app_constants.FLUXCD_HELMRELEASE_GLANCE,
                    app_constants.FLUXCD_HELMRELEASE_CINDER,
                    app_constants.FLUXCD_HELMRELEASE_GARBD,
                    app_constants.FLUXCD_HELMRELEASE_KEYSTONE_API_PROXY,
                ],
            },
        ]

        dbapi = mock.Mock()

        self.fluxCDKustomizeOperator.set_helm_releases = mock.Mock()

        for test_data in test_cases:
            mode = test_data['mode']
            release_list = test_data['release_list']
            resources_before_restore = test_data['resources_before_restore']

            self.fluxCDKustomizeOperator.resources_before_restore = resources_before_restore

            self.fluxCDKustomizeOperator.platform_mode_kustomize_updates(dbapi, mode)

            self.fluxCDKustomizeOperator.set_helm_releases.assert_called_once_with(
                dbapi, app_constants.HELM_NS_OPENSTACK, release_list)

            self.fluxCDKustomizeOperator.set_helm_releases.reset_mock()
