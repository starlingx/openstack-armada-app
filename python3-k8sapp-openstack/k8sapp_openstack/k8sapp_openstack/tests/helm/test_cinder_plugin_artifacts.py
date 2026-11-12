#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for Python artifact consumption in CinderHelm.

Cover CinderHelm._process_artifacts: the empty baseline, image-only root
import to both consumers, nested and multiple ordered paths, target
selection, whole-image mounts and their use together with Python entries.

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
        self.overrides = self._empty_overrides()

    @staticmethod
    def _empty_overrides():
        """Empty artifact defaults, as get_overrides builds them."""
        return {
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


def _mounts_id(image, targets, mount_paths):
    """Return the generated artifact id of a whole-image entry."""
    consumption = {"kind": app_constants.ARTIFACT_KIND_MOUNTS,
                   "mounts": [{"mountPath": p} for p in mount_paths]}
    artifact_id, _ = artifacts.compute_artifact_id(
        image, tuple(targets), consumption)
    return artifact_id


class MountsKindTestCase(ProcessArtifactsBase):
    """Whole-image mounts entries mount the complete image read-only."""

    def test_single_destination_in_both_consumers(self):
        result = self._run([{
            "source": {"image": IMG_HELPER},
            "mounts": [{"mountPath": "/opt/partner/helpers"}],
        }])
        name = artifacts.artifact_resource_name(
            _mounts_id(IMG_HELPER, ("volume", "backup"),
                       ["/opt/partner/helpers"]))
        for component in ("cinder_volume", "cinder_backup"):
            art = self._artifacts(result, component)
            self.assertEqual(
                [{"name": name,
                  "image": {"reference": IMG_HELPER,
                            "pullPolicy": "IfNotPresent"}}],
                art["volumes"])
            self.assertEqual(
                [{"name": name, "mountPath": "/opt/partner/helpers",
                  "readOnly": True}],
                art["volumeMounts"])
            self.assertEqual([], art["python_paths"])

    def test_several_destinations_share_one_volume(self):
        result = self._run([{
            "source": {"image": IMG_HELPER},
            "targets": ["volume"],
            "mounts": [{"mountPath": "/opt/partner/helpers"},
                       {"mountPath": "/usr/local/partner"}],
        }])
        vol = self._artifacts(result, "cinder_volume")
        self.assertEqual(1, len(vol["volumes"]))
        self.assertEqual(
            ["/opt/partner/helpers", "/usr/local/partner"],
            [m["mountPath"] for m in vol["volumeMounts"]])
        self.assertEqual(
            {vol["volumes"][0]["name"]},
            {m["name"] for m in vol["volumeMounts"]})
        self.assertTrue(all(m["readOnly"] for m in vol["volumeMounts"]))

    def test_volume_only_target_leaves_backup_empty(self):
        result = self._run([{
            "source": {"image": IMG_HELPER},
            "targets": ["volume"],
            "mounts": [{"mountPath": "/opt/partner/helpers"}],
        }])
        backup = self._artifacts(result, "cinder_backup")
        self.assertEqual([], backup["volumes"])
        self.assertEqual([], backup["volumeMounts"])

    def test_backup_only_target_leaves_volume_empty(self):
        result = self._run([{
            "source": {"image": IMG_HELPER},
            "targets": ["backup"],
            "mounts": [{"mountPath": "/opt/partner/helpers"}],
        }])
        self.assertEqual(
            [], self._artifacts(result, "cinder_volume")["volumeMounts"])
        self.assertEqual(
            1, len(self._artifacts(result, "cinder_backup")["volumeMounts"]))

    def test_consumers_do_not_share_objects(self):
        result = self._run([{
            "source": {"image": IMG_HELPER},
            "mounts": [{"mountPath": "/opt/partner/helpers"}],
        }])
        vol = self._artifacts(result, "cinder_volume")
        backup = self._artifacts(result, "cinder_backup")
        self.assertEqual(vol["volumes"], backup["volumes"])
        self.assertIsNot(vol["volumes"][0], backup["volumes"][0])
        self.assertIsNot(vol["volumeMounts"][0], backup["volumeMounts"][0])

    def test_mounts_do_not_add_python_paths(self):
        result = self._run([{
            "source": {"image": IMG_HELPER},
            "mounts": [{"mountPath": "/opt/partner/helpers"}],
        }])
        for component in ("cinder_volume", "cinder_backup"):
            self.assertEqual(
                [], self._artifacts(result, component)["python_paths"])

    def test_mount_path_is_normalized(self):
        result = self._run([{
            "source": {"image": IMG_HELPER},
            "targets": ["volume"],
            "mounts": [{"mountPath": "//opt/partner/helpers/"}],
        }])
        self.assertEqual(
            "/opt/partner/helpers",
            self._artifacts(result, "cinder_volume")["volumeMounts"][0][
                "mountPath"])

    def test_equivalent_entries_are_deduplicated(self):
        entry = {"source": {"image": IMG_HELPER}, "targets": ["volume"],
                 "mounts": [{"mountPath": "/opt/partner/helpers"}]}
        result = self._run([entry, dict(entry)])
        vol = self._artifacts(result, "cinder_volume")
        self.assertEqual(1, len(vol["volumes"]))
        self.assertEqual(1, len(vol["volumeMounts"]))

    def test_names_do_not_change_the_generated_delivery(self):
        plain = {"source": {"image": IMG_HELPER}, "targets": ["volume"],
                 "mounts": [{"mountPath": "/opt/partner/helpers"}]}
        named = dict(plain, name="helpers")
        self.assertEqual(
            self._artifacts(self._run([plain]), "cinder_volume"),
            self._artifacts(self._run([named]), "cinder_volume"))


class MountsConflictTestCase(ProcessArtifactsBase):
    """Incompatible whole-image destinations fail instead of replacing."""

    def test_same_destination_from_different_images_is_rejected(self):
        self.assertRaises(artifacts.ArtifactError, self._run, [
            {"source": {"image": IMG_HELPER}, "targets": ["volume"],
             "mounts": [{"mountPath": "/opt/partner/helpers"}]},
            {"source": {"image": IMG_B}, "targets": ["volume"],
             "mounts": [{"mountPath": "/opt/partner/helpers"}]},
        ])

    def test_nested_destinations_are_rejected(self):
        self.assertRaises(artifacts.ArtifactError, self._run, [
            {"source": {"image": IMG_HELPER}, "targets": ["volume"],
             "mounts": [{"mountPath": "/opt/partner"}]},
            {"source": {"image": IMG_B}, "targets": ["volume"],
             "mounts": [{"mountPath": "/opt/partner/helpers"}]},
        ])

    def test_sibling_destinations_are_accepted(self):
        result = self._run([
            {"source": {"image": IMG_HELPER}, "targets": ["volume"],
             "mounts": [{"mountPath": "/opt/partner"}]},
            {"source": {"image": IMG_B}, "targets": ["volume"],
             "mounts": [{"mountPath": "/opt/partner2"}]},
        ])
        self.assertEqual(
            2, len(self._artifacts(result, "cinder_volume")["volumeMounts"]))

    def test_same_destination_in_separate_consumers_is_accepted(self):
        result = self._run([
            {"source": {"image": IMG_HELPER}, "targets": ["volume"],
             "mounts": [{"mountPath": "/opt/partner/helpers"}]},
            {"source": {"image": IMG_B}, "targets": ["backup"],
             "mounts": [{"mountPath": "/opt/partner/helpers"}]},
        ])
        self.assertEqual(
            1, len(self._artifacts(result, "cinder_volume")["volumeMounts"]))
        self.assertEqual(
            1, len(self._artifacts(result, "cinder_backup")["volumeMounts"]))

    def test_subpath_is_rejected(self):
        self.assertRaises(artifacts.ArtifactError, self._run, [{
            "source": {"image": IMG_HELPER},
            "mounts": [{"mountPath": "/usr/local/bin/x",
                        "subPath": "bin/x"}],
        }])


class MixedModesTestCase(ProcessArtifactsBase):
    """Python and whole-image entries coexist without overwriting."""

    def test_python_and_mounts_both_reach_the_consumer(self):
        result = self._run([
            {"source": {"image": IMG_A}, "targets": ["volume"]},
            {"source": {"image": IMG_HELPER}, "targets": ["volume"],
             "mounts": [{"mountPath": "/opt/partner/helpers"}]},
        ])
        root_a = _mount_root(IMG_A, ("volume",), ["."])
        vol = self._artifacts(result, "cinder_volume")
        self.assertEqual([root_a], vol["python_paths"])
        self.assertEqual(2, len(vol["volumes"]))
        self.assertEqual(
            [root_a, "/opt/partner/helpers"],
            [m["mountPath"] for m in vol["volumeMounts"]])

    def test_same_image_in_python_and_mounts_entries(self):
        result = self._run([
            {"source": {"image": IMG_A}, "targets": ["volume"]},
            {"source": {"image": IMG_A}, "targets": ["volume"],
             "mounts": [{"mountPath": "/opt/partner/helpers"}]},
        ])
        vol = self._artifacts(result, "cinder_volume")
        self.assertEqual(2, len(vol["volumeMounts"]))
        # Both volumes reference the same image under distinct names.
        self.assertEqual(2, len({v["name"] for v in vol["volumes"]}))
        self.assertEqual({IMG_A},
                         {v["image"]["reference"] for v in vol["volumes"]})
        self.assertEqual(1, len(vol["python_paths"]))

    def test_removing_the_mounts_entry_removes_its_delivery(self):
        both = [
            {"source": {"image": IMG_A}, "targets": ["volume"]},
            {"source": {"image": IMG_HELPER}, "targets": ["volume"],
             "mounts": [{"mountPath": "/opt/partner/helpers"}]},
        ]
        self.assertEqual(
            2, len(self._artifacts(self._run(both), "cinder_volume")[
                "volumeMounts"]))
        # A new apply starts again from the empty defaults.
        self.overrides = self._empty_overrides()
        python_only = self._run(both[:1])
        vol = self._artifacts(python_only, "cinder_volume")
        self.assertEqual(1, len(vol["volumeMounts"]))
        self.assertEqual(1, len(vol["volumes"]))
