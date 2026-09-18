#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.helm import helm
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

from k8sapp_openstack.helm import libvirt
from k8sapp_openstack.tests import test_plugins


class LibvirtHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                          base.HelmTestCaseMixin):

    def setUp(self):
        super(LibvirtHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class LibvirtGetOverrideTest(LibvirtHelmTestCase,
                             dbbase.ControllerHostTestCase):

    def setUp(self):
        super(LibvirtGetOverrideTest, self).setUp()
        self.operator = helm.HelmOperator(self.dbapi)
        self.libvirt = libvirt.LibvirtHelm(self.operator)
        self.libvirt._ceph_enabled = False

    def test_conf_overrides_include_cluster_host_networks(self):
        primary_subnet = '192.0.2.0/24'
        cluster_host_subnets = [primary_subnet, '2001:db8::/64']

        overrides = self.libvirt._get_conf_overrides(
            primary_subnet, cluster_host_subnets)

        self.assertEqual(
            overrides['dynamic_options']['libvirt']['listen_network_cidr'],
            primary_subnet
        )
        self.assertEqual(
            overrides['address_selection']['node_network_cidrs'],
            cluster_host_subnets
        )
