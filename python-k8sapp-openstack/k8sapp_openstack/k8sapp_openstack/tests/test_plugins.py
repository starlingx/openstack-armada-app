#
# SPDX-License-Identifier: Apache-2.0
#

# fmt:off
import mock

from k8sapp_openstack.armada.manifest_openstack import \
    OpenstackArmadaManifestOperator
from k8sapp_openstack.common import constants as app_constants
from sysinv.common import constants
from sysinv.helm import common
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base
from sysinv.tests.helm.test_helm import HelmOperatorTestSuiteMixin

# fmt:on

KEY_SCHEMA = "schema"
KEY_METADATA = "metadata"
KEY_METADATA_NAME = "name"


class K8SAppOpenstackAppBaseMixin(object):
    app_name = app_constants.HELM_APP_OPENSTACK
    path_name = app_name + ".tgz"

    def setUp(self):
        super(K8SAppOpenstackAppBaseMixin, self).setUp()
        # Label hosts with appropriate labels
        for host in self.hosts:
            if host.personality == constants.CONTROLLER:
                dbutils.create_test_label(
                    host_id=host.id,
                    label_key=common.LABEL_CONTROLLER,
                    label_value=common.LABEL_VALUE_ENABLED,
                )
            elif host.personality == constants.WORKER:
                dbutils.create_test_label(
                    host_id=host.id,
                    label_key=common.LABEL_COMPUTE_LABEL,
                    label_value=common.LABEL_VALUE_ENABLED,
                )


class K8SAppOpenstackAppMixin(K8SAppOpenstackAppBaseMixin):
    def setUp(self):
        super(K8SAppOpenstackAppMixin, self).setUp()

        save_delete_manifest = mock.patch.object(
            OpenstackArmadaManifestOperator, "save_delete_manifest"
        )
        save_delete_manifest.start()
        self.addCleanup(save_delete_manifest.stop)


# Test Configuration:
# - Controller
# - IPv6
# - Ceph Storage
# - stx-openstack app
class K8SAppOpenstackControllerTestCase(
    K8SAppOpenstackAppMixin,
    HelmOperatorTestSuiteMixin,
    dbbase.BaseIPv6Mixin,
    dbbase.BaseCephStorageBackendMixin,
    dbbase.ControllerHostTestCase,
):
    pass


# Test Configuration:
# - AIO
# - IPv4
# - Ceph Storage
# - stx-openstack app
class K8SAppOpenstackAIOTestCase(
    K8SAppOpenstackAppMixin,
    HelmOperatorTestSuiteMixin,
    dbbase.BaseCephStorageBackendMixin,
    dbbase.AIOSimplexHostTestCase,
):
    pass


# Test Configuration:
# - Controller
# - stx-openstack app
class SaveDeleteManifestTestCase(
    K8SAppOpenstackAppBaseMixin,
    base.HelmTestCaseMixin,
    dbbase.ControllerHostTestCase
):
    @mock.patch("os.path.exists", return_value=True)
    @mock.patch(
        "k8sapp_openstack.armada.manifest_openstack.deepcopy",
        return_value=[
            {
                "schema": "armada/ChartGroup/v1",
                "metadata": {
                    "name": "openstack-compute-kit",
                },
                "data": {
                    "sequenced": "false",
                    "chart_group": [
                        "openstack-libvirt",
                        "openstack-placement",
                        "openstack-nova",
                        "openstack-nova-api-proxy",
                        "openstack-pci-irq-affinity-agent",
                        "openstack-neutron",
                    ],
                },
            },
            {
                "schema": "armada/Manifest/v1",
                "metadata": {
                    "name": "openstack-manifest",
                },
                "data": {
                    "release_prefix": "osh",
                    "chart_groups": [
                        "openstack-psp-rolebinding",
                        "openstack-ingress",
                        "openstack-mariadb",
                        "openstack-memcached",
                        "openstack-rabbitmq",
                        "openstack-keystone",
                        "openstack-barbican",
                        "openstack-glance",
                        "openstack-cinder",
                        "openstack-ceph-rgw",
                        "openstack-compute-kit",
                        "openstack-heat",
                        "openstack-fm-rest-api",
                        "openstack-horizon",
                        "openstack-telemetry",
                    ],
                },
            },
        ],
    )
    @mock.patch("six.moves.builtins.open", mock.mock_open(read_data="fake"))
    @mock.patch(
        "k8sapp_openstack.armada.manifest_openstack"
        ".OpenstackArmadaManifestOperator._cleanup_deletion_manifest"
    )
    def test_save_delete_manifest(self, *_):
        def assert_manifest_overrides(manifest, parameters):
            """Validate the manifest contains the supplied parameters"""
            if not isinstance(manifest, list) \
                    or not isinstance(parameters, list):
                self.assertOverridesParameters(manifest, parameters)
            else:
                for i in parameters:
                    for j in manifest:
                        if (
                            i[KEY_SCHEMA] == j[KEY_SCHEMA]
                            and i[KEY_METADATA][KEY_METADATA_NAME]
                            == j[KEY_METADATA][KEY_METADATA_NAME]
                        ):
                            self.assertOverridesParameters(j, i)
                            break

        armada_op = OpenstackArmadaManifestOperator()
        armada_op.save_delete_manifest()

        assert_manifest_overrides(
            armada_op.delete_manifest_contents,
            [
                {
                    "schema": "armada/ChartGroup/v1",
                    "metadata": {
                        "name": "openstack-compute-kit",
                    },
                    "data": {
                        "sequenced": "true",
                        "chart_group": [
                            "openstack-neutron",
                            "openstack-pci-irq-affinity-agent",
                            "openstack-nova-api-proxy",
                            "openstack-nova",
                            "openstack-placement",
                            "openstack-libvirt",
                        ],
                    },
                },
                {
                    "schema": "armada/Manifest/v1",
                    "metadata": {
                        "name": "openstack-manifest",
                    },
                    "data": {
                        "release_prefix": "osh",
                        "chart_groups": [
                            "openstack-telemetry",
                            "openstack-horizon",
                            "openstack-fm-rest-api",
                            "openstack-heat",
                            "openstack-compute-kit",
                            "openstack-ceph-rgw",
                            "openstack-cinder",
                            "openstack-glance",
                            "openstack-barbican",
                            "openstack-keystone",
                            "openstack-rabbitmq",
                            "openstack-memcached",
                            "openstack-mariadb",
                            "openstack-ingress",
                            "openstack-psp-rolebinding",
                        ],
                    },
                },
            ],
        )
