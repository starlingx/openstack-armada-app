#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for Python artifact consumption in CinderHelm.

Cover CinderHelm._process_artifacts: the empty baseline, image-only root
import to both consumers, nested and multiple ordered paths, target
selection and mount-only entries that add no Python paths.

Only the shared artifacts helpers are real; storage_conf.artifacts is
supplied through _get_value_from_application, so these are plain testtools
unit tests driven by fixtures.
"""

import mock
import testtools

from k8sapp_openstack.common import artifacts
from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helm import cinder

IMG_A = "registry.local:9001/partner/python-a@sha256:aaaa"
IMG_B = "registry.local:9001/partner/python-b@sha256:bbbb"
IMG_HELPER = "registry.local:9001/partner/helpers@sha256:cccc"


def _mount_root(image, targets, paths):
    """Return the generated mount root the plugin resolves paths against."""
    consumption = {"kind": app_constants.ARTIFACT_KIND_PYTHON,
                   "paths": list(paths)}
    artifact_id, _ = artifacts.compute_artifact_id(
        image, tuple(targets), consumption)
    return artifacts.artifact_mount_root(artifact_id)


class ProcessArtifactsBase(testtools.TestCase):
    """Drive CinderHelm._process_artifacts with a given artifacts override."""

    def setUp(self):
        super(ProcessArtifactsBase, self).setUp()
        self.helm = cinder.CinderHelm(None)
        # Empty artifact defaults, as get_overrides builds them.
        self.overrides = {
            "pod": {
                "artifacts": {
                    "cinder_volume": {
                        "volumes": [], "volumeMounts": [], "python_paths": [],
                    },
                    "cinder_backup": {
                        "volumes": [], "volumeMounts": [], "python_paths": [],
                    },
                }
            }
        }

    def _run(self, entries):
        def side_effect(default_value, chart_name, override_name):
            if override_name == app_constants.OVERRIDE_ARTIFACTS:
                return entries
            return default_value
        with mock.patch(
                "k8sapp_openstack.helm.cinder._get_value_from_application",
                side_effect=side_effect):
            return self.helm._process_artifacts(self.overrides)

    def _artifacts(self, result, component):
        return result["pod"]["artifacts"][component]


class DefaultsTestCase(ProcessArtifactsBase):
    """Empty baseline and image-only root import to both consumers."""

    def test_none_leaves_defaults_unchanged(self):
        result = self._run(None)
        for component in ("cinder_volume", "cinder_backup"):
            art = self._artifacts(result, component)
            self.assertEqual([], art["volumes"])
            self.assertEqual([], art["volumeMounts"])
            self.assertEqual([], art["python_paths"])

    def test_empty_list_leaves_defaults_unchanged(self):
        result = self._run([])
        for component in ("cinder_volume", "cinder_backup"):
            art = self._artifacts(result, component)
            self.assertEqual([], art["volumes"])
            self.assertEqual([], art["python_paths"])

    def test_image_only_mounts_root_in_both_consumers(self):
        result = self._run([{"source": {"image": IMG_A}}])
        root = _mount_root(IMG_A, ("volume", "backup"), ["."])
        for component in ("cinder_volume", "cinder_backup"):
            art = self._artifacts(result, component)
            self.assertEqual([root], art["python_paths"])
            self.assertEqual(1, len(art["volumes"]))
            self.assertEqual(IMG_A, art["volumes"][0]["image"]["reference"])
            self.assertEqual(app_constants.ARTIFACT_IMAGE_PULL_POLICY,
                             art["volumes"][0]["image"]["pullPolicy"])
            mount = art["volumeMounts"][0]
            self.assertEqual(root, mount["mountPath"])
            self.assertTrue(mount["readOnly"])
            self.assertEqual(art["volumes"][0]["name"], mount["name"])


class TargetsTestCase(ProcessArtifactsBase):
    """Target selection chooses which consumers receive the artifact."""

    def test_volume_only(self):
        result = self._run([{"source": {"image": IMG_A},
                             "targets": ["volume"]}])
        root = _mount_root(IMG_A, ("volume",), ["."])
        self.assertEqual([root],
                         self._artifacts(result, "cinder_volume")["python_paths"])
        self.assertEqual(
            [], self._artifacts(result, "cinder_backup")["python_paths"])

    def test_backup_only(self):
        result = self._run([{"source": {"image": IMG_A},
                             "targets": ["backup"]}])
        self.assertEqual(
            [], self._artifacts(result, "cinder_volume")["python_paths"])
        self.assertEqual(
            1, len(self._artifacts(result, "cinder_backup")["volumeMounts"]))


class PythonPathsTestCase(ProcessArtifactsBase):
    """Nested search paths resolve beneath the mount root, in order."""

    def test_nested_paths_preserve_order(self):
        result = self._run([{
            "source": {"image": IMG_A},
            "targets": ["volume"],
            "pythonPaths": ["opt/vendor/drivers", "opt/vendor/sdks"],
        }])
        root = _mount_root(
            IMG_A, ("volume",), ["opt/vendor/drivers", "opt/vendor/sdks"])
        self.assertEqual(
            [root + "/opt/vendor/drivers", root + "/opt/vendor/sdks"],
            self._artifacts(result, "cinder_volume")["python_paths"])


class MultipleArtifactsTestCase(ProcessArtifactsBase):
    """Several artifacts compose in declaration order."""

    def test_paths_follow_artifact_order(self):
        result = self._run([
            {"source": {"image": IMG_A}, "targets": ["volume"]},
            {"source": {"image": IMG_B}, "targets": ["volume"]},
        ])
        root_a = _mount_root(IMG_A, ("volume",), ["."])
        root_b = _mount_root(IMG_B, ("volume",), ["."])
        vol = self._artifacts(result, "cinder_volume")
        self.assertEqual([root_a, root_b], vol["python_paths"])
        self.assertEqual(2, len(vol["volumes"]))
        self.assertEqual(2, len(vol["volumeMounts"]))


class MountsKindTestCase(ProcessArtifactsBase):
    """Whole-image mounts entries add no Python delivery here."""

    def test_mounts_only_entry_adds_nothing(self):
        result = self._run([{
            "source": {"image": IMG_HELPER},
            "targets": ["volume"],
            "mounts": [{"mountPath": "/opt/partner/helpers"}],
        }])
        vol = self._artifacts(result, "cinder_volume")
        self.assertEqual([], vol["python_paths"])
        self.assertEqual([], vol["volumes"])
        self.assertEqual([], vol["volumeMounts"])

    def test_mixed_entries_only_python_contributes(self):
        result = self._run([
            {"source": {"image": IMG_A}, "targets": ["volume"]},
            {"source": {"image": IMG_HELPER}, "targets": ["volume"],
             "mounts": [{"mountPath": "/opt/partner/helpers"}]},
        ])
        root_a = _mount_root(IMG_A, ("volume",), ["."])
        vol = self._artifacts(result, "cinder_volume")
        self.assertEqual([root_a], vol["python_paths"])
        self.assertEqual(1, len(vol["volumes"]))
