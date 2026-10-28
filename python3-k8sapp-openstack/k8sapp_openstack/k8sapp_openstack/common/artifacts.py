# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

"""Parse, identify and build delivery structures for storage_conf.artifacts.

One parser shared by the Python and whole-image consumers and by the pre-apply
checks, so a declaration is interpreted the same way when validated and when
manifests are generated.

Pure and stateless: no image inspection, registry access or saved state.
Records are recomputed from the current overrides on each call. This module
builds the per-component pieces; the chart composes generated and manual values
at render time.
"""

import hashlib
import json
import posixpath

from k8sapp_openstack.common import constants as app_constants


class ArtifactError(ValueError):
    """Artifact declaration error with field context.

    config_path points at the bad field, e.g.
    storage_conf.artifacts[1].mounts[0].mountPath. name and artifact_id are
    added when known.
    """

    def __init__(self, config_path, reason, name=None, artifact_id=None):
        self.config_path = config_path
        self.reason = reason
        self.name = name
        self.artifact_id = artifact_id
        label = ""
        if name is not None:
            label = " [%s]" % name
        if artifact_id is not None:
            label += " (id=%s)" % artifact_id
        super().__init__("%s%s: %s" % (config_path, label, reason))


def _artifacts_root():
    """Dotted path of the top-level artifact list, for error messages."""
    return app_constants.OVERRIDE_ARTIFACTS


def _entry_path(index):
    return "%s[%d]" % (_artifacts_root(), index)


def _is_nonempty_str(value):
    return isinstance(value, str) and value != ""


def _reject_traversal(path, config_path, name=None):
    """Reject '..' in a path, before normalization."""
    parts = path.split("/")
    if ".." in parts:
        raise ArtifactError(
            config_path,
            "parent traversal ('..') is not allowed in path %r" % path,
            name=name)


def _validate_source(source, config_path, name=None):
    """Validate the ``source`` mapping and return the image reference."""
    if not isinstance(source, dict):
        raise ArtifactError(
            config_path, "'source' must be a mapping", name=name)

    unknown = set(source) - app_constants.ARTIFACT_SOURCE_ALLOWED_KEYS
    if unknown:
        raise ArtifactError(
            config_path,
            "unknown key(s) in 'source': %s; only 'image' is accepted"
            % ", ".join(sorted(unknown)),
            name=name)

    image = source.get("image")
    if not _is_nonempty_str(image):
        raise ArtifactError(
            config_path + ".source.image",
            "required non-empty string image reference is missing",
            name=name)
    return image


def _validate_targets(targets, config_path, name=None):
    """Validate 'targets' and return it in fixed order.

    Called only when the key is present. Empty, null or unknown values are
    errors; omission (handled by the caller) means both components.
    """
    if targets is None:
        # Explicit null (an absent key is handled by the caller).
        raise ArtifactError(
            config_path + ".targets",
            "targets must be a non-empty list of %s; null is not allowed"
            % list(app_constants.ARTIFACT_COMPONENTS),
            name=name)

    if not isinstance(targets, list) or not targets:
        raise ArtifactError(
            config_path + ".targets",
            "targets must be a non-empty list of %s"
            % list(app_constants.ARTIFACT_COMPONENTS),
            name=name)

    seen = set()
    for value in targets:
        if value not in app_constants.ARTIFACT_COMPONENTS:
            raise ArtifactError(
                config_path + ".targets",
                "invalid target %r; valid values are %s"
                % (value, list(app_constants.ARTIFACT_COMPONENTS)),
                name=name)
        seen.add(value)
    # Normalize to fixed order, independent of declaration order.
    return tuple(c for c in app_constants.ARTIFACT_COMPONENTS if c in seen)


def _validate_python_paths(python_paths, config_path, name=None):
    """Validate an explicit ``pythonPaths`` list, preserving order."""
    if not isinstance(python_paths, list) or not python_paths:
        raise ArtifactError(
            config_path + ".pythonPaths",
            "pythonPaths must be a non-empty list of image-relative "
            "directory paths",
            name=name)

    normalized = []
    for i, path in enumerate(python_paths):
        item_path = "%s.pythonPaths[%d]" % (config_path, i)
        if not _is_nonempty_str(path):
            raise ArtifactError(
                item_path, "must be a non-empty string", name=name)
        if path.startswith("/"):
            raise ArtifactError(
                item_path,
                "absolute paths are not allowed; use image-relative paths",
                name=name)
        if ":" in path:
            raise ArtifactError(
                item_path,
                "':' is not allowed in a Python search path",
                name=name)
        _reject_traversal(path, item_path, name=name)
        # '.' means the image root (resolved to the mount root at render time).
        normalized.append(posixpath.normpath(path))
    return normalized


def _validate_mounts(mounts, config_path, name=None):
    """Validate 'mounts' (whole-image mode). Each item accepts only an absolute
    'mountPath'."""
    if not isinstance(mounts, list) or not mounts:
        raise ArtifactError(
            config_path + ".mounts",
            "mounts must be a non-empty list of mount items",
            name=name)

    normalized = []
    for i, item in enumerate(mounts):
        item_path = "%s.mounts[%d]" % (config_path, i)
        if not isinstance(item, dict):
            raise ArtifactError(
                item_path, "mount item must be a mapping", name=name)

        unknown = set(item) - app_constants.ARTIFACT_MOUNT_ALLOWED_KEYS
        if unknown:
            raise ArtifactError(
                item_path,
                "unknown key(s): %s; only 'mountPath' is accepted"
                % ", ".join(sorted(unknown)),
                name=name)

        mount_path = item.get("mountPath")
        if not _is_nonempty_str(mount_path):
            raise ArtifactError(
                item_path + ".mountPath",
                "required non-empty absolute destination is missing",
                name=name)
        if not mount_path.startswith("/"):
            raise ArtifactError(
                item_path + ".mountPath",
                "mountPath must be an absolute path, got %r" % mount_path,
                name=name)
        _reject_traversal(mount_path, item_path + ".mountPath", name=name)
        normalized.append({"mountPath": posixpath.normpath(mount_path)})
    return normalized


def _default_display_name(image):
    """Fallback display name: the image repository leaf, without digest/tag."""
    repo = image.split("@", 1)[0]
    # Strip a trailing tag only; the leaf has no registry host:port.
    leaf = repo.rsplit("/", 1)[-1]
    if ":" in leaf:
        leaf = leaf.rsplit(":", 1)[0]
    return leaf or image


def _canonical_identity_payload(image, targets, consumption):
    """Canonical structure for the id hash.

    Excludes name and list position. Keeps path/mount order (it is meaningful).
    """
    payload = {
        "image": image,
        "targets": list(targets),
    }
    if consumption["kind"] == app_constants.ARTIFACT_KIND_PYTHON:
        payload["consumption"] = {
            "kind": app_constants.ARTIFACT_KIND_PYTHON,
            "paths": list(consumption["paths"]),
        }
    else:
        payload["consumption"] = {
            "kind": app_constants.ARTIFACT_KIND_MOUNTS,
            "mounts": [m["mountPath"] for m in consumption["mounts"]],
        }
    return payload


def _canonical_json(payload):
    """Deterministic JSON for hashing and collision comparison."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_artifact_id(image, targets, consumption):
    """Return (short_id, canonical_json).

    short_id is the first ARTIFACT_ID_LENGTH hex chars of SHA-256(canonical).
    canonical is returned so callers can tell a real short-id collision from
    two equal entries.
    """
    payload = _canonical_identity_payload(image, targets, consumption)
    canonical = _canonical_json(payload)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:app_constants.ARTIFACT_ID_LENGTH], canonical


def normalize_artifacts(entries):
    """Validate and normalize storage_conf.artifacts into records.

    :param entries: value of storage_conf.artifacts. None or [] means no
        delivery (empty list). Any other type is an error.
    :returns: records in input order. Each is a dict with config_path,
        display_name, id, image, targets (fixed order) and consumption.
        consumption is {"kind": "python", "paths": [...]} or
        {"kind": "mounts", "mounts": [{"mountPath": ...}]}.
    :raises ArtifactError: on the first bad entry, or on an id collision between
        different entries.
    """
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise ArtifactError(
            _artifacts_root(),
            "artifacts must be a list; omit it or use [] for no delivery")

    records = []
    # short id -> canonical json, to tell a real collision from equal entries.
    seen_ids = {}

    for index, entry in enumerate(entries):
        config_path = _entry_path(index)
        if not isinstance(entry, dict):
            raise ArtifactError(config_path, "artifact entry must be a mapping")

        # Read name first so it can label later errors.
        name = entry.get("name")
        if "name" in entry and not _is_nonempty_str(name):
            raise ArtifactError(
                config_path + ".name",
                "name, when present, must be a non-empty string")

        unknown = set(entry) - app_constants.ARTIFACT_ALLOWED_KEYS
        if unknown:
            raise ArtifactError(
                config_path,
                "unknown key(s): %s; allowed keys are %s (obsolete 'module', "
                "artifact-level 'mountPath'/'subPath' and operator 'id' are "
                "rejected)"
                % (", ".join(sorted(unknown)),
                   sorted(app_constants.ARTIFACT_ALLOWED_KEYS)),
                name=name)

        image = _validate_source(entry.get("source"), config_path, name=name)
        display_name = name if _is_nonempty_str(name) \
            else _default_display_name(image)

        # Targets: omitted -> both; explicit null/empty/unknown -> error.
        if "targets" in entry:
            targets = _validate_targets(
                entry["targets"], config_path, name=display_name)
        else:
            targets = tuple(app_constants.ARTIFACT_COMPONENTS)

        has_python = "pythonPaths" in entry
        has_mounts = "mounts" in entry
        if has_python and has_mounts:
            raise ArtifactError(
                config_path,
                "'pythonPaths' and 'mounts' cannot be combined in one entry",
                name=display_name)

        if has_mounts:
            consumption = {
                "kind": app_constants.ARTIFACT_KIND_MOUNTS,
                "mounts": _validate_mounts(
                    entry["mounts"], config_path, name=display_name),
            }
        elif has_python:
            consumption = {
                "kind": app_constants.ARTIFACT_KIND_PYTHON,
                "paths": _validate_python_paths(
                    entry["pythonPaths"], config_path, name=display_name),
            }
        else:
            # Image-only default: Python at the image root.
            consumption = {
                "kind": app_constants.ARTIFACT_KIND_PYTHON,
                "paths": [posixpath.normpath(p)
                          for p in app_constants.ARTIFACT_DEFAULT_PYTHON_PATHS],
            }

        artifact_id, canonical = compute_artifact_id(
            image, targets, consumption)

        prior = seen_ids.get(artifact_id)
        if prior is not None and prior != canonical:
            # Same short id, different entry: do not merge.
            raise ArtifactError(
                config_path,
                "id %r collides with a different artifact declaration"
                % artifact_id,
                name=display_name, artifact_id=artifact_id)
        seen_ids[artifact_id] = canonical

        records.append({
            "config_path": config_path,
            "display_name": display_name,
            "id": artifact_id,
            "image": image,
            "targets": targets,
            "consumption": consumption,
        })

    return records


def artifact_resource_name(artifact_id):
    """Return the generated Kubernetes resource name for an artifact id."""
    return app_constants.ARTIFACT_RESOURCE_NAME_PREFIX + artifact_id


def artifact_mount_root(artifact_id):
    """Generated mount root for a Python artifact (internal path)."""
    return app_constants.ARTIFACT_MOUNT_ROOT_PREFIX + artifact_id


def make_image_volume(record):
    """Build a Kubernetes image volume: image kept verbatim, explicit pull
    policy."""
    return {
        "name": artifact_resource_name(record["id"]),
        "image": {
            "reference": record["image"],
            "pullPolicy": app_constants.ARTIFACT_IMAGE_PULL_POLICY,
        },
    }


def _parent_or_equal(a, b):
    """True if path a equals or is a parent of b, compared by component.

    So /opt/vendor overlaps /opt/vendor/bin but not /opt/vendor2.
    """
    a_parts = [p for p in a.split("/") if p]
    b_parts = [p for p in b.split("/") if p]
    if len(a_parts) > len(b_parts):
        return False
    return b_parts[:len(a_parts)] == a_parts


def _mounts_conflict(existing, candidate):
    """Return a conflict reason for two volumeMounts, or None.

    Same destination with identical mounts is not a conflict (the caller
    deduplicates). Same destination with any difference, or a parent/child
    destination overlap, is a conflict.
    """
    e_path = existing["mountPath"]
    c_path = candidate["mountPath"]

    if e_path == c_path:
        if existing == candidate:
            return None
        return "conflicting mounts at the same destination %r" % c_path

    if _parent_or_equal(e_path, c_path) or _parent_or_equal(c_path, e_path):
        return ("overlapping parent/child mount destinations %r and %r"
                % (e_path, c_path))
    return None


def compose_component_delivery(contributions, existing_mounts=None):
    """Combine delivery contributions for one component.

    :param contributions: ordered per-artifact dicts with optional volumes,
        volumeMounts and python_paths. The caller builds them; this only
        combines.
    :param existing_mounts: volumeMounts already on the container, used to check
        for conflicts. Defaults to none.
    :returns: dict with combined volumes, volumeMounts and python_paths.
        Duplicates are dropped; first-seen python path order is kept.
    :raises ArtifactError: on a mount conflict or a conflicting volume.
    """
    volumes = []
    volumes_by_name = {}
    volume_mounts = []
    python_paths = []
    seen_python = set()

    # Existing mounts only guard artifact mounts; they are not emitted again.
    effective_mounts = list(existing_mounts or [])

    for contribution in contributions:
        for volume in contribution.get("volumes", []):
            name = volume.get("name")
            prior = volumes_by_name.get(name)
            if prior is None:
                volumes_by_name[name] = volume
                volumes.append(volume)
            elif prior != volume:
                raise ArtifactError(
                    _artifacts_root(),
                    "conflicting volume definitions for %r" % name)
            # Same name and definition: dropped.

        for mount in contribution.get("volumeMounts", []):
            # Identical mount already present: skip. Same destination with any
            # difference, or an overlap: raise.
            if mount in effective_mounts:
                continue
            for existing in effective_mounts:
                reason = _mounts_conflict(existing, mount)
                if reason:
                    raise ArtifactError(_artifacts_root(), reason)
            effective_mounts.append(mount)
            volume_mounts.append(mount)

        for path in contribution.get("python_paths", []):
            if path not in seen_python:
                seen_python.add(path)
                python_paths.append(path)

    return {
        "volumes": volumes,
        "volumeMounts": volume_mounts,
        "python_paths": python_paths,
    }
