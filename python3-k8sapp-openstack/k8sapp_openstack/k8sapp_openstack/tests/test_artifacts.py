# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for k8sapp_openstack.common.artifacts.

Cover both consumption modes, defaults, malformed inputs, whole-image path
rules, unknown keys, targets, identity stability/change/collision, duplicate
labels and mappings, ordering and the empty baseline.

The module is pure (no DB or Helm access), so these are plain testtools unit
tests driven by fixtures.
"""

import testtools

from k8sapp_openstack.common import artifacts
from k8sapp_openstack.common import constants as app_constants

IMG_A = "registry.local:9001/partner/python-bundle@sha256:aaaa"
IMG_B = "registry.local:9001/partner/helpers@sha256:bbbb"


class NormalizeDefaultsTestCase(testtools.TestCase):
    """Empty baseline, image-only Python default and target default."""

    def test_none_is_empty(self):
        self.assertEqual([], artifacts.normalize_artifacts(None))

    def test_empty_list_is_empty(self):
        self.assertEqual([], artifacts.normalize_artifacts([]))

    def test_non_list_top_level_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError,
            artifacts.normalize_artifacts, {"source": {"image": IMG_A}})

    def test_image_only_defaults_to_python_root_and_both_targets(self):
        records = artifacts.normalize_artifacts(
            [{"source": {"image": IMG_A}}])
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual(IMG_A, record["image"])
        self.assertEqual(
            (app_constants.ARTIFACT_COMPONENT_VOLUME,
             app_constants.ARTIFACT_COMPONENT_BACKUP),
            record["targets"])
        self.assertEqual(app_constants.ARTIFACT_KIND_PYTHON,
                         record["consumption"]["kind"])
        self.assertEqual(["."], record["consumption"]["paths"])

    def test_explicit_root_python_equivalent_to_image_only(self):
        image_only = artifacts.normalize_artifacts(
            [{"source": {"image": IMG_A}}])
        explicit = artifacts.normalize_artifacts(
            [{"source": {"image": IMG_A}, "pythonPaths": ["."]}])
        self.assertEqual(image_only[0]["id"], explicit[0]["id"])
        self.assertEqual(image_only[0]["consumption"],
                         explicit[0]["consumption"])

    def test_display_name_defaults_to_repo_leaf(self):
        records = artifacts.normalize_artifacts(
            [{"source": {"image": IMG_A}}])
        self.assertEqual("python-bundle", records[0]["display_name"])


class TargetsTestCase(testtools.TestCase):
    """targets selector rules."""

    def test_single_target(self):
        records = artifacts.normalize_artifacts(
            [{"source": {"image": IMG_A}, "targets": ["volume"]}])
        self.assertEqual(("volume",), records[0]["targets"])

    def test_both_targets_normalized_to_fixed_order(self):
        records = artifacts.normalize_artifacts(
            [{"source": {"image": IMG_A}, "targets": ["backup", "volume"]}])
        self.assertEqual(("volume", "backup"), records[0]["targets"])

    def test_empty_targets_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_A}, "targets": []}])

    def test_null_targets_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_A}, "targets": None}])

    def test_unknown_target_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_A}, "targets": ["api"]}])


class PythonPathsTestCase(testtools.TestCase):
    """pythonPaths validation and ordering."""

    def test_nested_paths_preserve_order(self):
        records = artifacts.normalize_artifacts([{
            "source": {"image": IMG_A},
            "pythonPaths": ["opt/vendor/drivers", "opt/vendor/sdks"],
        }])
        self.assertEqual(["opt/vendor/drivers", "opt/vendor/sdks"],
                         records[0]["consumption"]["paths"])

    def test_empty_python_paths_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_A}, "pythonPaths": []}])

    def test_absolute_python_path_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_A}, "pythonPaths": ["/opt/x"]}])

    def test_colon_python_path_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_A}, "pythonPaths": ["a:b"]}])

    def test_parent_traversal_python_path_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_A}, "pythonPaths": ["a/../b"]}])


class MountsTestCase(testtools.TestCase):
    """Explicit whole-image mounts."""

    def test_whole_image_mount(self):
        records = artifacts.normalize_artifacts([{
            "source": {"image": IMG_B},
            "targets": ["volume"],
            "mounts": [{"mountPath": "/opt/partner/helpers"}],
        }])
        consumption = records[0]["consumption"]
        self.assertEqual(app_constants.ARTIFACT_KIND_MOUNTS,
                         consumption["kind"])
        self.assertEqual([{"mountPath": "/opt/partner/helpers"}],
                         consumption["mounts"])

    def test_mount_subpath_rejected_as_unknown_key(self):
        err = self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_B},
              "mounts": [{"subPath": "bin/x", "mountPath": "/usr/local/bin/x"}]}])
        self.assertIn("subPath", str(err))

    def test_relative_mount_path_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_B}, "mounts": [{"mountPath": "rel/x"}]}])

    def test_empty_mounts_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_B}, "mounts": []}])

    def test_mount_missing_path_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_B}, "mounts": [{}]}])

    def test_python_and_mounts_mutually_exclusive(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_B},
              "pythonPaths": ["."],
              "mounts": [{"mountPath": "/opt/x"}]}])


class StrictSchemaTestCase(testtools.TestCase):
    """Strict key/type validation."""

    def test_unknown_top_level_key_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_A}, "bogus": 1}])

    def test_obsolete_module_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_A}, "module": "foo"}])

    def test_artifact_level_mountpath_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_A}, "mountPath": "/opt/x"}])

    def test_operator_id_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_A}, "id": "abc"}])

    def test_source_unknown_key_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {"image": IMG_A, "tag": "x"}}])

    def test_missing_source_image_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"source": {}}])

    def test_entry_not_mapping_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts, ["x"])

    def test_empty_name_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError, artifacts.normalize_artifacts,
            [{"name": "", "source": {"image": IMG_A}}])


class IdentityTestCase(testtools.TestCase):
    """Internal identity: stability, functional change, collisions, labels."""

    def test_rename_does_not_change_id(self):
        a = artifacts.normalize_artifacts(
            [{"name": "one", "source": {"image": IMG_A}}])
        b = artifacts.normalize_artifacts(
            [{"name": "two", "source": {"image": IMG_A}}])
        self.assertEqual(a[0]["id"], b[0]["id"])

    def test_reorder_does_not_change_id(self):
        records = artifacts.normalize_artifacts([
            {"source": {"image": IMG_A}},
            {"source": {"image": IMG_B}, "mounts": [{"mountPath": "/opt/h"}]},
        ])
        reordered = artifacts.normalize_artifacts([
            {"source": {"image": IMG_B}, "mounts": [{"mountPath": "/opt/h"}]},
            {"source": {"image": IMG_A}},
        ])
        self.assertEqual(records[0]["id"], reordered[1]["id"])
        self.assertEqual(records[1]["id"], reordered[0]["id"])

    def test_image_change_changes_id(self):
        a = artifacts.normalize_artifacts([{"source": {"image": IMG_A}}])
        b = artifacts.normalize_artifacts([{"source": {"image": IMG_B}}])
        self.assertNotEqual(a[0]["id"], b[0]["id"])

    def test_target_change_changes_id(self):
        a = artifacts.normalize_artifacts(
            [{"source": {"image": IMG_A}, "targets": ["volume"]}])
        b = artifacts.normalize_artifacts(
            [{"source": {"image": IMG_A}, "targets": ["backup"]}])
        self.assertNotEqual(a[0]["id"], b[0]["id"])

    def test_python_path_order_changes_id(self):
        a = artifacts.normalize_artifacts(
            [{"source": {"image": IMG_A}, "pythonPaths": ["a", "b"]}])
        b = artifacts.normalize_artifacts(
            [{"source": {"image": IMG_A}, "pythonPaths": ["b", "a"]}])
        self.assertNotEqual(a[0]["id"], b[0]["id"])

    def test_equivalent_declarations_share_id(self):
        records = artifacts.normalize_artifacts([
            {"name": "x", "source": {"image": IMG_A}},
            {"name": "y", "source": {"image": IMG_A}},
        ])
        self.assertEqual(records[0]["id"], records[1]["id"])

    def test_duplicate_labels_allowed(self):
        records = artifacts.normalize_artifacts([
            {"name": "same", "source": {"image": IMG_A}},
            {"name": "same", "source": {"image": IMG_B}},
        ])
        self.assertEqual("same", records[0]["display_name"])
        self.assertEqual("same", records[1]["display_name"])

    def test_id_length_and_hex(self):
        records = artifacts.normalize_artifacts([{"source": {"image": IMG_A}}])
        artifact_id = records[0]["id"]
        self.assertEqual(app_constants.ARTIFACT_ID_LENGTH, len(artifact_id))
        int(artifact_id, 16)  # raises ValueError if not hex

    def test_collision_detection_rejects_distinct_merge(self):
        # Force two functionally different declarations to share a short id by
        # stubbing compute_artifact_id to a constant short id with distinct
        # canonical payloads.
        original = artifacts.compute_artifact_id
        canon = {"n": 0}

        def _fake(image, targets, consumption):
            canon["n"] += 1
            return "deadbeefdeadbeef", "canonical-%d" % canon["n"]

        artifacts.compute_artifact_id = _fake
        try:
            self.assertRaises(
                artifacts.ArtifactError, artifacts.normalize_artifacts,
                [{"source": {"image": IMG_A}},
                 {"source": {"image": IMG_B}}])
        finally:
            artifacts.compute_artifact_id = original


class VolumeHelperTestCase(testtools.TestCase):
    """make_image_volume / naming helpers."""

    def test_make_image_volume_preserves_reference_and_policy(self):
        record = artifacts.normalize_artifacts(
            [{"source": {"image": IMG_A}}])[0]
        volume = artifacts.make_image_volume(record)
        self.assertEqual(IMG_A, volume["image"]["reference"])
        self.assertEqual(app_constants.ARTIFACT_IMAGE_PULL_POLICY,
                         volume["image"]["pullPolicy"])
        self.assertTrue(volume["name"].startswith(
            app_constants.ARTIFACT_RESOURCE_NAME_PREFIX))

    def test_mount_root_prefix(self):
        root = artifacts.artifact_mount_root("abc123")
        self.assertTrue(root.startswith(app_constants.ARTIFACT_MOUNT_ROOT_PREFIX))


class ComposeTestCase(testtools.TestCase):
    """compose_component_delivery combination, dedup and conflict rules."""

    def _contribution(self, name, mount_path, python_path=None):
        contribution = {
            "volumes": [{
                "name": name,
                "image": {"reference": IMG_A, "pullPolicy": "IfNotPresent"},
            }],
            "volumeMounts": [{
                "name": name, "mountPath": mount_path, "readOnly": True,
            }],
            "python_paths": [python_path] if python_path else [],
        }
        return contribution

    def test_empty_contributions(self):
        result = artifacts.compose_component_delivery([])
        self.assertEqual(
            {"volumes": [], "volumeMounts": [], "python_paths": []}, result)

    def test_combine_distinct(self):
        result = artifacts.compose_component_delivery([
            self._contribution("a", "/opt/a", "/opt/a"),
            self._contribution("b", "/opt/b", "/opt/b"),
        ])
        self.assertEqual(2, len(result["volumes"]))
        self.assertEqual(2, len(result["volumeMounts"]))
        self.assertEqual(["/opt/a", "/opt/b"], result["python_paths"])

    def test_python_path_first_occurrence_order(self):
        result = artifacts.compose_component_delivery([
            {"python_paths": ["/x", "/y"]},
            {"python_paths": ["/y", "/z"]},
        ])
        self.assertEqual(["/x", "/y", "/z"], result["python_paths"])

    def test_equivalent_mount_deduplicated(self):
        contribution = self._contribution("a", "/opt/a", "/opt/a")
        result = artifacts.compose_component_delivery([
            contribution, dict(contribution)])
        self.assertEqual(1, len(result["volumeMounts"]))

    def test_conflicting_same_destination_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError,
            artifacts.compose_component_delivery,
            [self._contribution("a", "/opt/same"),
             self._contribution("b", "/opt/same")])

    def test_parent_child_destination_rejected(self):
        self.assertRaises(
            artifacts.ArtifactError,
            artifacts.compose_component_delivery,
            [self._contribution("a", "/opt/vendor"),
             self._contribution("b", "/opt/vendor/bin")])

    def test_sibling_destinations_allowed(self):
        result = artifacts.compose_component_delivery([
            self._contribution("a", "/opt/vendor"),
            self._contribution("b", "/opt/vendor2"),
        ])
        self.assertEqual(2, len(result["volumeMounts"]))

    def test_conflict_against_existing_mount(self):
        existing = [{"name": "chart", "mountPath": "/opt/same",
                     "readOnly": True}]
        self.assertRaises(
            artifacts.ArtifactError,
            artifacts.compose_component_delivery,
            [self._contribution("a", "/opt/same")], existing)

    def test_conflicting_volume_definition_rejected(self):
        c1 = {"volumes": [{"name": "dup", "image": {"reference": IMG_A}}]}
        c2 = {"volumes": [{"name": "dup", "image": {"reference": IMG_B}}]}
        self.assertRaises(
            artifacts.ArtifactError,
            artifacts.compose_component_delivery, [c1, c2])
