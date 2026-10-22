#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

"""Render tests for the Cinder chart artifact patch.

The chart is not part of this repository: it is the upstream tarball pinned in
upstream/helm-charts/openstack-helm/debian/<codename>/meta_data.yaml with the quilt
patches of that codename's series applied. These tests build it the same way the
package build does and render it with 'helm template', so they cover the patch that
is actually shipped.

They are skipped unless helm and patch are on PATH and the pinned tarball is
available. Point OPENSTACK_HELM_TARBALL at a copy (for example the build mirror) to
avoid downloading it:

    OPENSTACK_HELM_TARBALL=/path/to/openstack-helm-<sha>.tar.gz \\
        stestr run k8sapp_openstack.tests.helm.test_cinder_artifacts

Tests cover, for both cinder-volume and cinder-backup:
- pod.env.<component> rendered in the matching container only
- a single composed PYTHONPATH, operator literal first and generated paths after
- final override merging: a later value file cannot discard generated values
- pod.mounts combined with pod.artifacts, de-duplication and conflict detection
  against existing, artifact and chart-owned mounts
- legacy-only mount configurations rendering unchanged
- additional rootwrap filter files in cinder-backup
- unchanged rendering when the new inputs are unset
"""

import copy
import hashlib
import os
import shutil
import subprocess  # nosec B404
import tarfile
import tempfile
import urllib.request

import testtools
import yaml

# Repository root, from k8sapp_openstack/tests/helm/ up to openstack-armada-app/.
REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), *([os.pardir] * 5)))
PACKAGE_DIR = os.path.join(
    REPO_ROOT, "upstream", "helm-charts", "openstack-helm")
CODENAME = os.environ.get("OPENSTACK_HELM_CODENAME", "trixie")
# Series entry under test; omitting it yields the pre-change baseline.
PATCH_UNDER_TEST = "Add-artifact-env-mounts-and-backup-rootwrap"

BASE_VALUES = {
    "manifests": {"deployment_volume": True, "deployment_backup": True},
}
RENDERED_TEMPLATES = [
    "templates/deployment-volume.yaml",
    "templates/deployment-backup.yaml",
]

VOLUME = "cinder_volume"
BACKUP = "cinder_backup"
COMPONENTS = [VOLUME, BACKUP]
OTHER_COMPONENT = {VOLUME: BACKUP, BACKUP: VOLUME}
CONTAINER_NAME = {VOLUME: "cinder-volume", BACKUP: "cinder-backup"}

ARTIFACT_VOLUME = {
    "name": "artifact-example",
    "image": {
        "reference": "registry.local:9001/partner/sdk@sha256:0123456789abcdef",
        "pullPolicy": "IfNotPresent",
    },
}
ARTIFACT_MOUNT = {
    "name": "artifact-example",
    "mountPath": "/opt/artifacts/example",
    "readOnly": True,
}
ROOTWRAP_DIR = "/etc/cinder/rootwrap.d/"

# Chart trees are expensive to build, so they are built once per process.
_CHART_CACHE = {}


def _meta_data():
    path = os.path.join(PACKAGE_DIR, "debian", CODENAME, "meta_data.yaml")
    with open(path) as handle:
        return yaml.safe_load(handle)


def _series():
    """The ordered patch file names of the series, comments dropped."""
    path = os.path.join(
        PACKAGE_DIR, "debian", CODENAME, "deb_folder", "patches", "series")
    with open(path) as handle:
        entries = [line.strip() for line in handle]
    return [entry for entry in entries if entry and not entry.startswith("#")]


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _tarball():
    """Return a path to the pinned tarball, or None when it is unavailable."""
    dl_path = _meta_data()["dl_path"]
    candidate = os.environ.get("OPENSTACK_HELM_TARBALL")
    if not candidate:
        cache = os.environ.get(
            "OPENSTACK_HELM_TEST_CACHE",
            os.path.join(tempfile.gettempdir(), "openstack-helm-chart-tests"))
        os.makedirs(cache, exist_ok=True)
        candidate = os.path.join(cache, dl_path["name"])
        if not os.path.isfile(candidate):
            try:
                urllib.request.urlretrieve(dl_path["url"], candidate)  # nosec B310
            except Exception:
                return None
    if not os.path.isfile(candidate):
        return None
    if _sha256(candidate) != dl_path["sha256sum"]:
        raise AssertionError(
            "sha256 of %s does not match %s meta_data.yaml" % (candidate, CODENAME))
    return candidate


def _extract(archive, dest):
    """Extract stripping the leading directory, refusing paths outside dest."""
    with tarfile.open(archive) as tar:
        root = os.path.realpath(dest)
        members = []
        for member in tar.getmembers():
            parts = member.name.split("/", 1)
            if len(parts) < 2 or not parts[1]:
                continue
            member.name = parts[1]
            target = os.path.realpath(os.path.join(dest, member.name))
            if target != root and not target.startswith(root + os.sep):
                raise AssertionError("unsafe path in tarball: %s" % member.name)
            members.append(member)
        extra = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        tar.extractall(dest, members=members, **extra)  # nosec B202


def _build_chart(tarball, exclude=None):
    """Extract the tarball, apply the series and return the cinder chart path.

    exclude is a substring; the series entry containing it is not applied.
    """
    dest = tempfile.mkdtemp(prefix="openstack-helm-%s-" % CODENAME)
    _extract(tarball, dest)
    patches = os.path.join(
        PACKAGE_DIR, "debian", CODENAME, "deb_folder", "patches")
    skipped = 0
    for name in _series():
        if exclude and exclude in name:
            skipped += 1
            continue
        result = subprocess.run(  # nosec B603
            ["patch", "-p1", "--no-backup-if-mismatch", "-s",
             "-i", os.path.join(patches, name)],
            cwd=dest, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise AssertionError(
                "applying %s failed: %s%s" % (name, result.stdout, result.stderr))
    if exclude and skipped != 1:
        raise AssertionError(
            "%r matches %d series entries, expected 1" % (exclude, skipped))
    for root, _, files in os.walk(dest):
        leftovers = [f for f in files if f.endswith((".orig", ".rej"))]
        if leftovers:
            raise AssertionError("patch leftovers in %s: %s" % (root, leftovers))
    result = subprocess.run(  # nosec B603
        ["helm", "dependency", "build", "cinder"],
        cwd=dest, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "helm dependency build failed: %s%s" % (result.stdout, result.stderr))
    return dest, os.path.join(dest, "cinder")


class CinderArtifactRenderTestCase(testtools.TestCase):
    """Base case: builds the patched chart and renders it with helm template."""

    exclude_patch = None

    def setUp(self):
        super(CinderArtifactRenderTestCase, self).setUp()
        for tool in ("helm", "patch"):
            if shutil.which(tool) is None:
                self.skipTest("%s is not available" % tool)
        tarball = _tarball()
        if tarball is None:
            self.skipTest(
                "the openstack-helm tarball pinned in meta_data.yaml is not "
                "available; set OPENSTACK_HELM_TARBALL")
        self.chart = self._chart(tarball, self.exclude_patch)

    @staticmethod
    def _chart(tarball, exclude):
        if exclude not in _CHART_CACHE:
            tree, chart = _build_chart(tarball, exclude)
            _CHART_CACHE[exclude] = chart
            # Trees outlive the test case so they are built once per process.
            CinderArtifactRenderTestCase._trees = getattr(
                CinderArtifactRenderTestCase, "_trees", [])
            CinderArtifactRenderTestCase._trees.append(tree)
        return _CHART_CACHE[exclude]

    # -- rendering ---------------------------------------------------------

    def render(self, *values, **kwargs):
        """Render both Cinder deployments. Returns (ok, documents, stderr)."""
        chart = kwargs.pop("chart", None) or self.chart
        tmp = tempfile.mkdtemp(prefix="cinder-values-")
        try:
            command = ["helm", "template", "c", chart]
            for index, value in enumerate((BASE_VALUES,) + values):
                path = os.path.join(tmp, "values-%d.yaml" % index)
                with open(path, "w") as handle:
                    yaml.safe_dump(value, handle)
                command += ["-f", path]
            for template in RENDERED_TEMPLATES:
                command += ["-s", template]
            result = subprocess.run(  # nosec B603
                command, capture_output=True, text=True, check=False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if result.returncode != 0:
            return False, None, result.stderr
        return True, [d for d in yaml.safe_load_all(result.stdout) if d], ""

    def render_ok(self, *values, **kwargs):
        ok, documents, error = self.render(*values, **kwargs)
        self.assertTrue(ok, "render failed: %s" % error.strip()[-600:])
        return documents

    def assert_render_fails(self, fragment, *values):
        ok, _, error = self.render(*values)
        self.assertFalse(
            ok, "render succeeded but should have failed with %r" % fragment)
        self.assertIn(fragment, error)

    # -- reading the result ------------------------------------------------

    @staticmethod
    def deployments(documents):
        return {d["metadata"]["name"]: d
                for d in documents if d.get("kind") == "Deployment"}

    def pod_spec(self, documents, component):
        name = CONTAINER_NAME[component]
        return self.deployments(documents)[name]["spec"]["template"]["spec"]

    def container(self, documents, component):
        name = CONTAINER_NAME[component]
        for container in self.pod_spec(documents, component)["containers"]:
            if container["name"] == name:
                return container
        self.fail("container %s not found" % name)

    def env(self, documents, component):
        """The container env as a dict; a name rendered twice is a failure."""
        entries = self.container(documents, component).get("env") or []
        names = [entry["name"] for entry in entries]
        self.assertEqual(len(set(names)), len(names),
                         "%s renders an env name twice: %s" % (component, names))
        return {entry["name"]: entry.get("value") for entry in entries}

    def mount_paths(self, documents, component):
        container = self.container(documents, component)
        return [m["mountPath"] for m in container.get("volumeMounts") or []]

    def volume_names(self, documents, component):
        spec = self.pod_spec(documents, component)
        return [volume["name"] for volume in spec.get("volumes") or []]

    def normalized(self, documents):
        """Deployments with the annotation that carries a random value removed."""
        result = []
        for _, deployment in sorted(self.deployments(documents).items()):
            deployment = copy.deepcopy(deployment)
            annotations = deployment["spec"]["template"]["metadata"].get(
                "annotations", {})
            # Hash of a Secret holding a random memcache key: differs per render.
            annotations.pop("configmap-etc-hash", None)
            result.append(deployment)
        return result

    # -- values builders ---------------------------------------------------

    @staticmethod
    def pod_env(component, **variables):
        return {"pod": {"env": {component: variables}}}

    @staticmethod
    def artifacts(component, volumes=None, volume_mounts=None,
                  python_paths=None):
        entry = {}
        if volumes is not None:
            entry["volumes"] = volumes
        if volume_mounts is not None:
            entry["volumeMounts"] = volume_mounts
        if python_paths is not None:
            entry["python_paths"] = python_paths
        return {"pod": {"artifacts": {component: entry}}}

    @staticmethod
    def pod_mounts(component, volumes=None, volume_mounts=None):
        entry = {}
        if volumes is not None:
            entry["volumes"] = volumes
        if volume_mounts is not None:
            entry["volumeMounts"] = volume_mounts
        return {"pod": {"mounts": {component: {component: entry}}}}

    @staticmethod
    def artifact_mount(path, **extra):
        mount = {"name": "artifact-example", "mountPath": path}
        mount.update(extra)
        return mount

    @staticmethod
    def merge(*values):
        """Recursive dict merge, enough for the nested pod.* values above."""
        result = {}
        for value in values:
            for key, item in value.items():
                if isinstance(item, dict) and isinstance(result.get(key), dict):
                    result[key] = CinderArtifactRenderTestCase.merge(
                        result[key], item)
                else:
                    result[key] = item
        return result


class TestEnvironmentVariables(CinderArtifactRenderTestCase):
    """pod.env.<component> rendering and PYTHONPATH composition."""

    def test_ordinary_variables_render_in_their_own_container(self):
        """Declared variables reach the matching container only."""
        for component in COMPONENTS:
            documents = self.render_ok(
                self.pod_env(component, FOO="bar", BAZ="qux"))
            self.assertEqual({"FOO": "bar", "BAZ": "qux"},
                             self.env(documents, component))
            self.assertEqual(
                {}, self.env(documents, OTHER_COMPONENT[component]))

    def test_manual_pythonpath_is_kept_verbatim(self):
        """The operator literal is not normalized or reinterpreted."""
        for component in COMPONENTS:
            documents = self.render_ok(
                self.pod_env(component, PYTHONPATH="/opt/company/python/"))
            self.assertEqual({"PYTHONPATH": "/opt/company/python/"},
                             self.env(documents, component))
            # Once only: the ordinary env helper must not render it as well.
            entries = self.container(documents, component)["env"]
            self.assertEqual(
                1, [e["name"] for e in entries].count("PYTHONPATH"))

    def test_generated_paths_only(self):
        """Generated paths render in their declared order."""
        for component in COMPONENTS:
            documents = self.render_ok(self.artifacts(
                component, python_paths=["/opt/artifacts/a", "/opt/artifacts/b"]))
            self.assertEqual(
                {"PYTHONPATH": "/opt/artifacts/a:/opt/artifacts/b"},
                self.env(documents, component))

    def test_manual_value_precedes_generated_paths_in_one_entry(self):
        """PYTHONPATH is rendered once, manual value first, and only once."""
        for component in COMPONENTS:
            documents = self.render_ok(
                self.pod_env(component, PYTHONPATH="/opt/company/python",
                             FOO="bar"),
                self.artifacts(component, python_paths=["/opt/artifacts/a"]))
            entries = [entry
                       for entry in self.container(documents, component)["env"]
                       if entry["name"] == "PYTHONPATH"]
            self.assertEqual(1, len(entries))
            self.assertEqual("/opt/company/python:/opt/artifacts/a",
                             entries[0]["value"])
            self.assertEqual("bar", self.env(documents, component)["FOO"])

    def test_generated_paths_are_used_as_supplied(self):
        """Generated paths are neither normalized nor de-duplicated."""
        for component in COMPONENTS:
            documents = self.render_ok(self.artifacts(
                component,
                python_paths=["/opt/artifacts/a/", "/opt/artifacts/a",
                              "/opt/artifacts/a"]))
            self.assertEqual(
                {"PYTHONPATH":
                 "/opt/artifacts/a/:/opt/artifacts/a:/opt/artifacts/a"},
                self.env(documents, component))

    def test_a_path_in_both_contributions_is_kept_in_both(self):
        """The manual literal and the generated order are preserved as is."""
        for component in COMPONENTS:
            documents = self.render_ok(
                self.pod_env(component, PYTHONPATH="/opt/artifacts/a"),
                self.artifacts(component,
                               python_paths=["/opt/artifacts/a",
                                             "/opt/artifacts/b"]))
            self.assertEqual(
                {"PYTHONPATH":
                 "/opt/artifacts/a:/opt/artifacts/a:/opt/artifacts/b"},
                self.env(documents, component))

    def test_empty_contributions_add_no_separator(self):
        """An empty manual value or generated entry does not leave a ':'."""
        for component in COMPONENTS:
            documents = self.render_ok(
                self.pod_env(component, PYTHONPATH=""),
                self.artifacts(component,
                               python_paths=["", "/opt/artifacts/a", ""]))
            self.assertEqual({"PYTHONPATH": "/opt/artifacts/a"},
                             self.env(documents, component))
            documents = self.render_ok(
                self.pod_env(component, PYTHONPATH="/opt/company/python"),
                self.artifacts(component, python_paths=[""]))
            self.assertEqual({"PYTHONPATH": "/opt/company/python"},
                             self.env(documents, component))

    def test_both_containers_keep_their_own_values(self):
        """Values configured for both consumers do not mix."""
        documents = self.render_ok({"pod": {"env": {
            VOLUME: {"PYTHONPATH": "/opt/volume", "ONLY_VOLUME": "1"},
            BACKUP: {"PYTHONPATH": "/opt/backup", "ONLY_BACKUP": "1"},
        }}})
        self.assertEqual({"PYTHONPATH": "/opt/volume", "ONLY_VOLUME": "1"},
                         self.env(documents, VOLUME))
        self.assertEqual({"PYTHONPATH": "/opt/backup", "ONLY_BACKUP": "1"},
                         self.env(documents, BACKUP))

    def test_existing_container_environment_is_preserved(self):
        """The conditional REQUESTS_CA_BUNDLE survives the new include."""
        documents = self.render_ok(
            {"manifests": {"certificates": True}},
            self.pod_env(VOLUME, FOO="bar"))
        environment = self.env(documents, VOLUME)
        self.assertEqual("/etc/ssl/certs/openstack-helm.crt",
                         environment["REQUESTS_CA_BUNDLE"])
        self.assertEqual("bar", environment["FOO"])

    def test_non_string_pythonpath_is_rejected(self):
        """An unsupported composition type fails the render."""
        for component in COMPONENTS:
            self.assert_render_fails(
                "PYTHONPATH must be a string",
                self.pod_env(component, PYTHONPATH=["/a", "/b"]))

    def test_non_string_generated_paths_are_rejected(self):
        """A generated entry that is not a string never becomes a path."""
        for component in COMPONENTS:
            for entry in (None, 5, True, ["/a"], {"k": "v"}):
                self.assert_render_fails(
                    "cinder %s: pod.artifacts.%s.python_paths entries must be "
                    "strings" % (component, component),
                    self.artifacts(component,
                                   python_paths=["/opt/artifacts/a", entry]))
            self.assert_render_fails(
                "cinder %s: pod.artifacts.%s.python_paths must be a list"
                % (component, component),
                self.artifacts(component, python_paths="/opt/artifacts/a"))

    def test_null_values_are_treated_as_unset(self):
        """Null values render nothing instead of failing."""
        for component in COMPONENTS:
            documents = self.render_ok(self.pod_env(component, PYTHONPATH=None))
            self.assertNotIn("PYTHONPATH", self.env(documents, component))
            self.render_ok({"pod": {"env": {component: None}}})
            self.render_ok({"pod": {"artifacts": {component: None}}})
        for key in ("env", "artifacts"):
            self.render_ok({"pod": {key: None}})


class TestOverrideMerging(CinderArtifactRenderTestCase):
    """Composition after the platform merges user and system overrides."""

    def test_a_later_override_cannot_discard_generated_values(self):
        """Helm keeps the last scalar and the last list; generated values stay."""
        for component in COMPONENTS:
            generated = self.artifacts(
                component, volumes=[ARTIFACT_VOLUME],
                volume_mounts=[ARTIFACT_MOUNT],
                python_paths=["/opt/artifacts/example"])
            first = self.merge(
                generated,
                self.pod_env(component, PYTHONPATH="/opt/first"),
                self.pod_mounts(
                    component,
                    volumes=[{"name": "first-extra", "emptyDir": {}}],
                    volume_mounts=[{"name": "first-extra",
                                    "mountPath": "/opt/first/extra"}]))
            later = self.merge(
                self.pod_env(component, PYTHONPATH="/opt/later"),
                self.pod_mounts(
                    component,
                    volumes=[{"name": "later-extra", "emptyDir": {}}],
                    volume_mounts=[{"name": "later-extra",
                                    "mountPath": "/opt/later/extra"}]))
            documents = self.render_ok(first, later)

            self.assertEqual(
                {"PYTHONPATH": "/opt/later:/opt/artifacts/example"},
                self.env(documents, component))
            paths = self.mount_paths(documents, component)
            self.assertIn("/opt/later/extra", paths)
            self.assertNotIn("/opt/first/extra", paths)
            self.assertIn("/opt/artifacts/example", paths)
            self.assertIn("artifact-example",
                          self.volume_names(documents, component))

    def test_an_emptied_user_list_keeps_generated_mounts(self):
        """Setting the operator mount list to [] does not remove artifacts."""
        for component in COMPONENTS:
            documents = self.render_ok(
                self.artifacts(component, volumes=[ARTIFACT_VOLUME],
                               volume_mounts=[ARTIFACT_MOUNT]),
                self.pod_mounts(component, volumes=[], volume_mounts=[]))
            self.assertIn("/opt/artifacts/example",
                          self.mount_paths(documents, component))
            self.assertIn("artifact-example",
                          self.volume_names(documents, component))


class TestMountIntegration(CinderArtifactRenderTestCase):
    """pod.mounts combined with pod.artifacts, and conflict detection."""

    def test_artifact_mount_and_volume_reach_only_their_container(self):
        """The generated volume and mount render, and do not cross over."""
        for component in COMPONENTS:
            other = OTHER_COMPONENT[component]
            documents = self.render_ok(self.artifacts(
                component, volumes=[ARTIFACT_VOLUME],
                volume_mounts=[ARTIFACT_MOUNT]))
            self.assertIn("/opt/artifacts/example",
                          self.mount_paths(documents, component))
            self.assertIn(ARTIFACT_VOLUME,
                          self.pod_spec(documents, component)["volumes"])
            self.assertNotIn("/opt/artifacts/example",
                             self.mount_paths(documents, other))
            self.assertNotIn("artifact-example",
                             self.volume_names(documents, other))

    def test_operator_and_artifact_mounts_coexist(self):
        """Both mount lists reach the container."""
        for component in COMPONENTS:
            documents = self.render_ok(
                self.pod_mounts(
                    component,
                    volumes=[{"name": "user-extra", "emptyDir": {}}],
                    volume_mounts=[{"name": "user-extra",
                                    "mountPath": "/opt/user/extra"}]),
                self.artifacts(component, volumes=[ARTIFACT_VOLUME],
                               volume_mounts=[ARTIFACT_MOUNT]))
            paths = self.mount_paths(documents, component)
            self.assertIn("/opt/user/extra", paths)
            self.assertIn("/opt/artifacts/example", paths)

    def test_equivalent_mappings_are_kept_once(self):
        """The same mapping from both inputs renders a single time."""
        for component in COMPONENTS:
            documents = self.render_ok(
                self.pod_mounts(component, volumes=[ARTIFACT_VOLUME],
                                volume_mounts=[ARTIFACT_MOUNT]),
                self.artifacts(component, volumes=[ARTIFACT_VOLUME],
                               volume_mounts=[ARTIFACT_MOUNT]))
            self.assertEqual(1, self.mount_paths(documents, component).count(
                "/opt/artifacts/example"))
            self.assertEqual(1, self.volume_names(documents, component).count(
                "artifact-example"))

    def test_one_volume_can_back_several_destinations(self):
        """Whole-image delivery mounts one image at several paths."""
        for component in COMPONENTS:
            documents = self.render_ok(self.artifacts(
                component, volumes=[ARTIFACT_VOLUME],
                volume_mounts=[self.artifact_mount("/opt/partner/helpers"),
                               self.artifact_mount("/opt/partner/sdk")]))
            paths = self.mount_paths(documents, component)
            self.assertIn("/opt/partner/helpers", paths)
            self.assertIn("/opt/partner/sdk", paths)
            self.assertEqual(1, self.volume_names(documents, component).count(
                "artifact-example"))

    def test_sibling_destinations_are_not_a_conflict(self):
        """/opt/vendor and /opt/vendor2 do not overlap."""
        for component in COMPONENTS:
            documents = self.render_ok(
                self.pod_mounts(
                    component,
                    volumes=[{"name": "user-extra", "emptyDir": {}}],
                    volume_mounts=[{"name": "user-extra",
                                    "mountPath": "/opt/vendor2"}]),
                self.artifacts(component, volumes=[ARTIFACT_VOLUME],
                               volume_mounts=[
                                   self.artifact_mount("/opt/vendor")]))
            paths = self.mount_paths(documents, component)
            self.assertIn("/opt/vendor", paths)
            self.assertIn("/opt/vendor2", paths)

    def test_the_same_destination_in_both_containers_is_allowed(self):
        """Separate Pods may use the same path."""
        documents = self.render_ok(
            self.artifacts(VOLUME, volumes=[ARTIFACT_VOLUME],
                           volume_mounts=[self.artifact_mount("/opt/shared")]),
            self.artifacts(BACKUP, volumes=[ARTIFACT_VOLUME],
                           volume_mounts=[self.artifact_mount("/opt/shared")]))
        self.assertIn("/opt/shared", self.mount_paths(documents, VOLUME))
        self.assertIn("/opt/shared", self.mount_paths(documents, BACKUP))

    def test_an_artifact_above_an_operator_destination_fails(self):
        """A parent destination overlaps and is reported with the path."""
        for component in COMPONENTS:
            self.assert_render_fails(
                "cinder %s: artifact mountPath /opt/vendor overlaps "
                "/opt/vendor/bin" % component,
                self.pod_mounts(
                    component,
                    volumes=[{"name": "user-extra", "emptyDir": {}}],
                    volume_mounts=[{"name": "user-extra",
                                    "mountPath": "/opt/vendor/bin"}]),
                self.artifacts(component, volumes=[ARTIFACT_VOLUME],
                               volume_mounts=[
                                   self.artifact_mount("/opt/vendor")]))

    def test_an_artifact_below_an_operator_destination_fails(self):
        """A child destination overlaps as well."""
        for component in COMPONENTS:
            self.assert_render_fails(
                "cinder %s: artifact mountPath /opt/vendor/bin overlaps "
                "/opt/vendor" % component,
                self.pod_mounts(
                    component,
                    volumes=[{"name": "user-extra", "emptyDir": {}}],
                    volume_mounts=[{"name": "user-extra",
                                    "mountPath": "/opt/vendor"}]),
                self.artifacts(component, volumes=[ARTIFACT_VOLUME],
                               volume_mounts=[
                                   self.artifact_mount("/opt/vendor/bin")]))

    def test_a_non_canonical_operator_destination_is_compared_cleaned(self):
        """An operator mount written as /opt/./vendor still overlaps /opt/vendor."""
        for component in COMPONENTS:
            for spelled in ("/opt/./vendor", "/opt/../opt/vendor",
                            "/opt/vendor/./bin", "/opt/vendor/"):
                self.assert_render_fails(
                    "cinder %s: artifact mountPath /opt/vendor overlaps %s"
                    % (component, spelled),
                    self.pod_mounts(
                        component,
                        volumes=[{"name": "user-extra", "emptyDir": {}}],
                        volume_mounts=[{"name": "user-extra",
                                        "mountPath": spelled}]),
                    self.artifacts(component, volumes=[ARTIFACT_VOLUME],
                                   volume_mounts=[
                                       self.artifact_mount("/opt/vendor")]))

    def test_an_overlap_between_two_artifacts_fails(self):
        """Artifacts are compared against each other, not only against mounts."""
        for component in COMPONENTS:
            self.assert_render_fails(
                "cinder %s: artifact mountPath /opt/b/c overlaps /opt/b"
                % component,
                self.artifacts(
                    component,
                    volumes=[ARTIFACT_VOLUME,
                             dict(ARTIFACT_VOLUME, name="artifact-other")],
                    volume_mounts=[
                        self.artifact_mount("/opt/b"),
                        {"name": "artifact-other", "mountPath": "/opt/b/c"}]))

    def test_different_mappings_at_the_same_destination_fail(self):
        """Two volumes cannot share one destination."""
        for component in COMPONENTS:
            self.assert_render_fails(
                "cinder %s: incompatible mounts at the same destination "
                "/opt/same" % component,
                self.artifacts(
                    component,
                    volumes=[ARTIFACT_VOLUME,
                             dict(ARTIFACT_VOLUME, name="artifact-other")],
                    volume_mounts=[
                        self.artifact_mount("/opt/same"),
                        {"name": "artifact-other", "mountPath": "/opt/same"}]))

    def test_mappings_differing_only_in_an_option_fail(self):
        """Equivalence compares the whole mount, including unknown fields."""
        for component in COMPONENTS:
            self.assert_render_fails(
                "incompatible mounts at the same destination /opt/opts",
                self.pod_mounts(
                    component, volumes=[ARTIFACT_VOLUME],
                    volume_mounts=[self.artifact_mount(
                        "/opt/opts", readOnly=True,
                        recursiveReadOnly="Enabled")]),
                self.artifacts(
                    component, volumes=[ARTIFACT_VOLUME],
                    volume_mounts=[self.artifact_mount(
                        "/opt/opts", readOnly=True,
                        recursiveReadOnly="Disabled")]))

    def test_mappings_differing_only_in_subpath_fail(self):
        """Selected content is part of the comparison."""
        for component in COMPONENTS:
            self.assert_render_fails(
                "incompatible mounts at the same destination /opt/opts",
                self.pod_mounts(
                    component, volumes=[ARTIFACT_VOLUME],
                    volume_mounts=[self.artifact_mount("/opt/opts",
                                                       subPath="a")]),
                self.artifacts(
                    component, volumes=[ARTIFACT_VOLUME],
                    volume_mounts=[self.artifact_mount("/opt/opts",
                                                       subPath="b")]))

    def test_read_only_false_equals_read_only_unset(self):
        """The only normalization applied to the comparison."""
        for component in COMPONENTS:
            documents = self.render_ok(
                self.pod_mounts(
                    component, volumes=[ARTIFACT_VOLUME],
                    volume_mounts=[self.artifact_mount("/opt/ro",
                                                       readOnly=False)]),
                self.artifacts(
                    component, volumes=[ARTIFACT_VOLUME],
                    volume_mounts=[self.artifact_mount("/opt/ro")]))
            self.assertEqual(
                1, self.mount_paths(documents, component).count("/opt/ro"))

    def test_a_volume_name_reused_with_another_definition_fails(self):
        """Incompatible volume definitions sharing a name are rejected."""
        for component in COMPONENTS:
            self.assert_render_fails(
                "cinder %s: volume artifact-example defined twice with "
                "different content" % component,
                self.pod_mounts(
                    component,
                    volumes=[{"name": "artifact-example", "emptyDir": {}}],
                    volume_mounts=[{"name": "artifact-example",
                                    "mountPath": "/opt/user"}]),
                self.artifacts(
                    component, volumes=[ARTIFACT_VOLUME],
                    volume_mounts=[self.artifact_mount(
                        "/opt/artifacts/example")]))

    def test_an_artifact_mount_without_a_destination_fails(self):
        """A generated mount must carry a mountPath."""
        for component in COMPONENTS:
            self.assert_render_fails(
                "cinder %s: artifact volume artifact-example has no mountPath"
                % component,
                self.artifacts(component, volumes=[ARTIFACT_VOLUME],
                               volume_mounts=[{"name": "artifact-example"}]))

    def test_a_non_canonical_artifact_destination_fails(self):
        """A destination the guard cannot compare literally is rejected.

        Kubernetes keeps mountPath as written and the runtime cleans it, so
        '//etc/cinder/x' or '/opt/../etc/x' would land on a chart-owned path
        while comparing unequal to it.
        """
        for component in COMPONENTS:
            for path in ("//etc/cinder/rootwrap.d/partner.filters",
                         "/opt/../etc/sudoers.d/partner",
                         "/etc/./cinder/rootwrap.conf",
                         "/opt/artifacts/example/",
                         "opt/artifacts/example"):
                self.assert_render_fails(
                    "cinder %s: artifact mountPath %s is not a clean absolute "
                    "path" % (component, path),
                    self.artifacts(component, volumes=[ARTIFACT_VOLUME],
                                   volume_mounts=[self.artifact_mount(path)]))

    def test_an_artifact_volume_named_like_a_chart_volume_fails(self):
        """A chart-owned volume name is rejected before the API server would."""
        for component in COMPONENTS:
            for name in ("cinder-etc", "pod-tmp", "cinder-bin"):
                self.assert_render_fails(
                    "cinder %s: artifact volume %s reuses a chart volume name"
                    % (component, name),
                    self.artifacts(
                        component,
                        volumes=[dict(ARTIFACT_VOLUME, name=name)],
                        volume_mounts=[dict(ARTIFACT_MOUNT, name=name)]))

    def test_the_error_names_the_consumer_that_is_wrong(self):
        """A conflict is not attributed to the other consumer."""
        for component in COMPONENTS:
            self.assert_render_fails(
                "cinder %s: artifact mountPath /var/lib/cinder conflicts"
                % component,
                self.artifacts(component, volumes=[ARTIFACT_VOLUME],
                               volume_mounts=[self.artifact_mount(
                                   "/var/lib/cinder")]))


class TestChartOwnedMountConflicts(CinderArtifactRenderTestCase):
    """Conflicts with the chart's own fixed and conditional mounts."""

    _CEPH = {"conf": {
        "cinder": {"DEFAULT": {"enabled_backends": "rbd1"}},
        "backends": {"rbd1": {
            "volume_driver": "cinder.volume.drivers.rbd.RBDDriver",
            "volume_backend_name": "rbd1",
            "rbd_pool": "cinder.volumes"}}}}
    _POSIX = "cinder.backup.drivers.posix.PosixBackupDriver"

    def shapes(self):
        """Value sets that switch on the conditional branches of the mounts."""
        return {
            "defaults": {},
            "tls": {"manifests": {"certificates": True}},
            "iscsi": {"conf": {"enable_iscsi": True}},
            "fcp": {"storage_conf": {"active_protocols": ["fcp"]}},
            "nfs": {"storage_conf": {"active_protocols": ["nfs"]},
                    "conf": {"nfs_shares": "1.2.3.4:/export\n"}},
            "esb-nfs-files": {"conf": {"esb_nfs_shares_files": {
                "partner.shares": "1.2.3.4:/export\n"}}},
            "ceph": self._CEPH,
            "ceph-external": self.merge(self._CEPH, {"ceph_client": {
                "enable_external_ceph_backend": True,
                "external_ceph": {"rbd_user": "ext",
                                  "rbd_user_keyring": "c2VjcmV0"}}}),
            "backup-ceph": {"conf": {"cinder": {"DEFAULT": {
                "backup_driver":
                    "cinder.backup.drivers.ceph.CephBackupDriver"}}}},
            "backup-posix": {"conf": {"cinder": {"DEFAULT": {
                "backup_driver": self._POSIX}}}},
            # Paths taken from values must be guarded wherever they point, not
            # only when they fall under the defaults.
            "custom-state-path": {"conf": {"cinder": {"DEFAULT": {
                "state_path": "/opt/cinder-state"}}}},
            "custom-lock-path": {"conf": {"cinder": {"oslo_concurrency": {
                "lock_path": "/opt/cinder-locks"}}}},
            "custom-log-config": {"conf": {"cinder": {"DEFAULT": {
                "log_config_append": "/opt/logcfg/logging.conf"}}}},
            "custom-coordination": {"conf": {"cinder": {"coordination": {
                "backend_url": "file:///opt/cinder-coordination"}}}},
            "custom-posix-backup": {"conf": {"cinder": {"DEFAULT": {
                "backup_driver": self._POSIX,
                "backup_posix_path": "/mnt/cinder-backups"}}}},
        }

    def test_an_artifact_is_rejected_on_every_destination_the_chart_mounts(self):
        """The expected set is read back from the rendered Deployment.

        A fixed or conditional chart mount that the guard does not cover shows
        up here, so the destination list cannot drift from the templates.
        """
        for label, values in sorted(self.shapes().items()):
            documents = self.render_ok(values)
            for component in COMPONENTS:
                destinations = sorted(set(
                    self.mount_paths(documents, component)))
                self.assertTrue(destinations)
                accepted = []
                for path in destinations:
                    ok, _, _ = self.render(self.merge(values, self.artifacts(
                        component, volumes=[ARTIFACT_VOLUME],
                        volume_mounts=[self.artifact_mount(path)])))
                    if ok:
                        accepted.append(path)
                self.assertEqual(
                    [], accepted,
                    "%s/%s: artifact accepted on chart-owned destinations"
                    % (label, component))

    def test_an_artifact_volume_is_rejected_on_every_name_the_chart_uses(self):
        """The expected set is read back from the rendered Deployments.

        A fixed or conditional chart volume the guard does not cover shows up
        here, so the name list cannot drift from the templates.
        """
        names = {component: set() for component in COMPONENTS}
        for values in self.shapes().values():
            documents = self.render_ok(values)
            for component in COMPONENTS:
                names[component].update(
                    self.volume_names(documents, component))
        for component in COMPONENTS:
            self.assertTrue(names[component])
            accepted = []
            for name in sorted(names[component]):
                ok, _, _ = self.render(self.artifacts(
                    component,
                    volumes=[dict(ARTIFACT_VOLUME, name=name)],
                    volume_mounts=[dict(ARTIFACT_MOUNT, name=name)]))
                if ok:
                    accepted.append(name)
            self.assertEqual(
                [], accepted,
                "%s: artifact volume accepted on chart-owned names" % component)

    def test_an_artifact_beside_the_chart_mounts_renders(self):
        """The guard does not reject destinations the chart does not use."""
        for component in COMPONENTS:
            documents = self.render_ok(self.artifacts(
                component, volumes=[ARTIFACT_VOLUME],
                volume_mounts=[self.artifact_mount("/opt/partner")]))
            paths = self.mount_paths(documents, component)
            self.assertIn("/etc/cinder/cinder.conf", paths)
            self.assertIn("/opt/partner", paths)


class TestLegacyMountBehaviour(CinderArtifactRenderTestCase):
    """Configurations without artifacts must render as they did before."""

    LEGACY_VOLUMES = [{"name": "dupv", "emptyDir": {}},
                      {"name": "dupv", "hostPath": {"path": "/tmp/legacy"}}]

    def test_duplicate_volume_names_still_render(self):
        """The strict volume check does not apply without artifacts."""
        for component in COMPONENTS:
            documents = self.render_ok(self.pod_mounts(
                component, volumes=self.LEGACY_VOLUMES,
                volume_mounts=[{"name": "dupv", "mountPath": "/opt/legacy"}]))
            self.assertEqual(
                2, self.volume_names(documents, component).count("dupv"))

    def test_duplicate_mappings_are_not_deduplicated(self):
        """Legacy lists are passed through unchanged, duplicates included."""
        for component in COMPONENTS:
            documents = self.render_ok(self.pod_mounts(
                component, volumes=[{"name": "legacy", "emptyDir": {}}],
                volume_mounts=[{"name": "legacy",
                                "mountPath": "/opt/legacy"}] * 2))
            self.assertEqual(
                2, self.mount_paths(documents, component).count("/opt/legacy"))

    def test_a_legacy_mount_on_a_chart_destination_still_renders(self):
        """The chart-owned destination check applies to artifacts only."""
        for component in COMPONENTS:
            self.render_ok(self.pod_mounts(
                component, volumes=[{"name": "legacy", "emptyDir": {}}],
                volume_mounts=[{"name": "legacy",
                                "mountPath": "/var/lib/cinder/legacy"}]))

    def test_artifacts_on_one_consumer_do_not_affect_the_other(self):
        """The strict checks stay scoped to the consumer with artifacts."""
        for component in COMPONENTS:
            other = OTHER_COMPONENT[component]
            documents = self.render_ok(
                self.pod_mounts(
                    component, volumes=self.LEGACY_VOLUMES,
                    volume_mounts=[{"name": "dupv",
                                    "mountPath": "/opt/legacy"}] * 2),
                self.artifacts(other, volumes=[ARTIFACT_VOLUME],
                               volume_mounts=[ARTIFACT_MOUNT]))
            self.assertEqual(
                2, self.mount_paths(documents, component).count("/opt/legacy"))
            self.assertEqual(
                2, self.volume_names(documents, component).count("dupv"))


class TestBackupRootwrapFilters(CinderArtifactRenderTestCase):
    """Additional rootwrap filter files projected into cinder-backup."""

    FILTERS = {"conf": {"rootwrap_filters": {
        "partner_copy": {
            "pods": ["backup"],
            "content": "[Filters]\ndellfcopy: CommandFilter, dellfcopy, root\n"},
        "shared_copy": {
            "pods": ["volume", "backup"],
            "content": "[Filters]\nshared: CommandFilter, shared, root\n"},
        "volume_only": {
            "pods": ["volume"],
            "content": "[Filters]\nvonly: CommandFilter, vonly, root\n"},
    }}}

    def test_filters_reach_only_the_selected_consumers(self):
        """pods: [backup], [volume, backup] and [volume] are all honored."""
        documents = self.render_ok(self.FILTERS)
        volume = self.mount_paths(documents, VOLUME)
        backup = self.mount_paths(documents, BACKUP)
        self.assertIn(ROOTWRAP_DIR + "partner-copy.filters", backup)
        self.assertNotIn(ROOTWRAP_DIR + "partner-copy.filters", volume)
        self.assertIn(ROOTWRAP_DIR + "shared-copy.filters", volume)
        self.assertIn(ROOTWRAP_DIR + "shared-copy.filters", backup)
        self.assertIn(ROOTWRAP_DIR + "volume-only.filters", volume)
        self.assertNotIn(ROOTWRAP_DIR + "volume-only.filters", backup)

    def test_volume_filters_are_mounted_exactly_once(self):
        """The standard filter file is preserved and not duplicated."""
        documents = self.render_ok(self.FILTERS)
        for component in COMPONENTS:
            self.assertEqual(1, self.mount_paths(documents, component).count(
                ROOTWRAP_DIR + "volume.filters"))

    def test_selecting_the_standard_filter_for_backup_does_not_duplicate_it(self):
        """A filter keyed 'volume' including backup must not mount twice."""
        documents = self.render_ok({"conf": {"rootwrap_filters": {
            "volume": {"pods": ["volume", "backup"]}}}})
        self.assertEqual(1, self.mount_paths(documents, BACKUP).count(
            ROOTWRAP_DIR + "volume.filters"))

    def test_the_projection_reuses_the_existing_naming_convention(self):
        """The file comes from cinder-etc through its own read-only subPath."""
        documents = self.render_ok(self.FILTERS)
        container = self.container(documents, BACKUP)
        entries = [mount for mount in container["volumeMounts"]
                   if mount["mountPath"]
                   == ROOTWRAP_DIR + "partner-copy.filters"]
        self.assertEqual(1, len(entries))
        self.assertEqual("cinder-etc", entries[0]["name"])
        self.assertEqual("partner-copy.filters", entries[0]["subPath"])
        self.assertTrue(entries[0]["readOnly"])
        self.assertIn("cinder-etc", self.volume_names(documents, BACKUP))

    def test_underscores_become_dashes_in_the_projected_name(self):
        """Keys with several underscores follow the ConfigMap naming."""
        documents = self.render_ok({"conf": {"rootwrap_filters": {
            "my_partner_copy": {"pods": ["backup"],
                                "content": "[Filters]\n"}}}})
        self.assertIn(ROOTWRAP_DIR + "my-partner-copy.filters",
                      self.mount_paths(documents, BACKUP))

    def test_a_filter_without_a_selector_reaches_no_consumer(self):
        """An absent pods list is not an implicit selection."""
        documents = self.render_ok({"conf": {"rootwrap_filters": {
            "no_pods": {"content": "[Filters]\n"}}}})
        for component in COMPONENTS:
            self.assertNotIn(ROOTWRAP_DIR + "no-pods.filters",
                             self.mount_paths(documents, component))


class TestDocumentedSampleValues(CinderArtifactRenderTestCase):
    """The plugin-to-chart handoff documented in cinder/values.yaml."""

    def test_the_documented_example_renders_as_documented(self):
        """The sample values produce the documented Deployment fragment."""
        for component in COMPONENTS:
            documents = self.render_ok({"pod": {
                "env": {component: {"PYTHONPATH": "/opt/company/python"}},
                "artifacts": {component: {
                    "volumes": [ARTIFACT_VOLUME],
                    "volumeMounts": [ARTIFACT_MOUNT],
                    "python_paths": ["/opt/artifacts/example"]}}}})
            self.assertEqual(
                [{"name": "PYTHONPATH",
                  "value": "/opt/company/python:/opt/artifacts/example"}],
                self.container(documents, component)["env"])
            self.assertIn(ARTIFACT_MOUNT,
                          self.container(documents, component)["volumeMounts"])
            self.assertIn(ARTIFACT_VOLUME,
                          self.pod_spec(documents, component)["volumes"])


class TestUnchangedDefaults(CinderArtifactRenderTestCase):
    """With the new inputs unset, the rendered workloads must not change."""

    def baseline(self):
        """The same series built without the patch under test."""
        tarball = _tarball()
        return self._chart(tarball, PATCH_UNDER_TEST)

    def test_defaults_match_the_series_without_the_patch(self):
        """Both Deployments render exactly as they did before the patch."""
        after = self.normalized(self.render_ok())
        before = self.normalized(self.render_ok(chart=self.baseline()))
        self.assertEqual(["cinder-backup", "cinder-volume"],
                         [d["metadata"]["name"] for d in after])
        self.assertEqual(before, after)

    def test_explicit_empty_inputs_change_nothing(self):
        """Declaring the new keys empty is the same as leaving them unset."""
        empty = {"pod": {
            "env": {component: {} for component in COMPONENTS},
            "artifacts": {component: {"volumes": [], "volumeMounts": [],
                                      "python_paths": []}
                          for component in COMPONENTS}}}
        documents = self.render_ok(empty)
        for component in COMPONENTS:
            self.assertEqual({}, self.env(documents, component))
            self.assertFalse(self.container(documents, component).get("env"))
        self.assertEqual(self.normalized(self.render_ok(chart=self.baseline())),
                         self.normalized(documents))


class TestChartLint(CinderArtifactRenderTestCase):
    """helm lint on the patched chart."""

    def test_helm_lint_passes(self):
        """The patched chart passes the chart lint checks."""
        result = subprocess.run(  # nosec B603
            ["helm", "lint", self.chart], capture_output=True, text=True,
            check=False)
        self.assertEqual(0, result.returncode, result.stdout[-600:])
        self.assertIn("0 chart(s) failed", result.stdout)
