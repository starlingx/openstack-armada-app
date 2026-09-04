#
# Copyright (c) 2023-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

""" System inventory App lifecycle operator."""

import os
from pathlib import Path
import shutil
import tempfile

from oslo_log import log as logging
from sysinv.api.controllers.v1 import utils
from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import kubernetes
from sysinv.helm import common
from sysinv.helm import lifecycle_base as base
from sysinv.helm import lifecycle_utils as lifecycle_utils
from sysinv.helm.lifecycle_constants import LifecycleConstants
from tsconfig import tsconfig as tsc

from k8sapp_openstack import utils as app_utils
from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helpers import ldap
from k8sapp_openstack.utils import check_dex_healthy
from k8sapp_openstack.utils import check_if_namespace_exists
from k8sapp_openstack.utils import check_if_pvc_exists_in_a_namespace
from k8sapp_openstack.utils import check_netapp_backends
from k8sapp_openstack.utils import check_storageclass_change
from k8sapp_openstack.utils import get_available_volume_backends
from k8sapp_openstack.utils import get_endpoint_domain
from k8sapp_openstack.utils import get_pvc_storageclass
from k8sapp_openstack.utils import get_pvc_storageclass_requirements
from k8sapp_openstack.utils import get_storage_backends_priority_list
from k8sapp_openstack.utils import is_ceph_backend_available
from k8sapp_openstack.utils import is_dex_enabled
from k8sapp_openstack.utils import oidc_parameters_exist
from k8sapp_openstack.utils import post_apply_update_dex_redirect_uri

LOG = logging.getLogger(__name__)


class OpenstackAppLifecycleOperator(base.AppLifecycleOperator):
    CHARTS_PENDING_INSTALL_ITERATIONS = 60
    APP_KUBESYSTEM_RESOURCE_CONFIG_MAP = 'rbd-storage-init'
    APP_OPENSTACK_RESOURCE_CONFIG_MAP = 'ceph-etc'
    WAS_APPLIED = 'was_applied'
    MAX_HOSTS_FOR_DETAILED_MSG = 5

    def app_lifecycle_actions(self, context, conductor_obj, app_op, app, hook_info):
        """ Perform lifecycle actions for an operation

        :param context: request context
        :param conductor_obj: conductor object
        :param app_op: AppOperator object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """
        # Operation
        # relative_timing is logged because a hook is only reachable when the
        # type, operation and timing all match what sysinv dispatches; without
        # the timing a mis-registered hook looks indistinguishable from one
        # that simply did not run.
        LOG.info("app_lifecycle_actions %s/%s (%s)",
                 hook_info.lifecycle_type, hook_info.relative_timing,
                 hook_info.operation)

        if hook_info.lifecycle_type == LifecycleConstants.APP_LIFECYCLE_TYPE_OPERATION:
            if hook_info.operation == constants.APP_APPLY_OP:
                if hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                    return self.pre_apply(context, conductor_obj, app, hook_info)
                elif hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_POST:
                    return self.post_apply(context, conductor_obj, app, hook_info)
            elif hook_info.operation == constants.APP_REMOVE_OP:
                if hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                    return self.pre_remove(context, conductor_obj, hook_info)
                elif hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_POST:
                    return self.post_remove(context, conductor_obj, hook_info)
            elif hook_info.operation == constants.APP_UPLOAD_OP:
                if hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_POST:
                    return self.post_upload(context, conductor_obj, app, hook_info)
            elif hook_info.operation == constants.APP_DELETE_OP:
                if hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                    return self.pre_delete(app_op, app)

        # Resource
        elif hook_info.lifecycle_type == LifecycleConstants.APP_LIFECYCLE_TYPE_RESOURCE:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                return self._create_app_specific_resources_pre_apply(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_REMOVE_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_POST:
                return self._delete_app_specific_resources_post_remove(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_RECOVER_OP:
                return self._recover_actions(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_UPDATE_OP:
                if hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                    return self.pre_update(app_op, app)
            elif hook_info.operation == constants.APP_DOWNGRADE_OP:
                if hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                    return self.pre_downgrade(app_op, app)

        # Semantic checks
        elif hook_info.lifecycle_type == LifecycleConstants.APP_LIFECYCLE_TYPE_SEMANTIC_CHECK:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                return self._pre_apply_check(conductor_obj, app, hook_info)
            elif hook_info.mode == LifecycleConstants.APP_LIFECYCLE_MODE_AUTO and \
                    hook_info.operation == constants.APP_EVALUATE_REAPPLY_OP:
                return self._semantic_check_evaluate_app_reapply(app_op, app, hook_info)
            elif hook_info.mode == LifecycleConstants.APP_LIFECYCLE_MODE_MANUAL and \
                    hook_info.operation == constants.APP_REMOVE_OP and \
                         hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                return self._pre_remove_check(conductor_obj, app, hook_info)

        # Manifest
        elif hook_info.lifecycle_type == LifecycleConstants.APP_LIFECYCLE_TYPE_MANIFEST:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                return self._pre_update_actions(app)
            elif hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_POST:
                return self.post_apply_manifest(app, hook_info)

        # Default behavior
        super(OpenstackAppLifecycleOperator, self).app_lifecycle_actions(context, conductor_obj, app_op, app,
                                                                         hook_info)

    def post_upload(self, context, conductor_obj, app, hook_info):
        """Post upload actions

        Performs LDAP-related post-upload setup, then deploys the
        application-owned ansible playbooks bundled in the tarball to the
        DRBD-replicated /opt/platform/ansible/ tree.

        :param context: request context
        :param conductor_obj: conductor object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """
        self._post_upload_ldap_actions(app)
        self._deploy_ansible(app)

    def pre_apply(self, context, conductor_obj, app, hook_info):
        """Pre apply actions

        :param context: request context
        :param conductor_obj: conductor object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """
        hook_info[LifecycleConstants.EXTRA][self.WAS_APPLIED] = app.active

    def post_apply(self, context, conductor_obj, app, hook_info):
        """ Post apply actions

        :param context: request context
        :param conductor_obj: conductor object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """
        if LifecycleConstants.EXTRA not in hook_info:
            raise exception.LifecycleMissingInfo("Missing {}".format(LifecycleConstants.EXTRA))
        if LifecycleConstants.APP_APPLIED not in hook_info[LifecycleConstants.EXTRA]:
            raise exception.LifecycleMissingInfo(
                "Missing {} {}".format(LifecycleConstants.EXTRA, LifecycleConstants.APP_APPLIED))
        if self.WAS_APPLIED not in hook_info[LifecycleConstants.EXTRA]:
            raise exception.LifecycleMissingInfo("Missing {} {}".format(LifecycleConstants.EXTRA, self.WAS_APPLIED))

        if hook_info[LifecycleConstants.EXTRA][LifecycleConstants.APP_APPLIED] and \
                not hook_info[LifecycleConstants.EXTRA][self.WAS_APPLIED]:
            # apply any runtime configurations that are needed for
            # stx_openstack application
            conductor_obj._update_config_for_stx_openstack(context)

            # The radosgw chart may have been enabled/disabled. Regardless of
            # the prior apply state, update the ceph config
            conductor_obj._update_radosgw_config(context)

        self._delete_maridb_pvc_snapshots_if_exists()

        # Update DEX redirect URI for Keystone WebSSO integration
        if hook_info[LifecycleConstants.EXTRA][LifecycleConstants.APP_APPLIED]:
            try:
                post_apply_update_dex_redirect_uri(context, conductor_obj)
            except Exception as e:
                # Log error but don't fail the openstack apply
                LOG.error(f"Failed to update DEX redirect URI: {e}")

        # Attempt to recover VMs found in ERROR state (e.g. expired
        # iSCSI/FC sessions after a backup & restore operation).
        if hook_info[LifecycleConstants.EXTRA][LifecycleConstants.APP_APPLIED]:
            try:
                app_utils.recover_error_servers(conductor_obj)
            except Exception as e:
                LOG.error(f"Failed to recover error servers: {e}")

        # The apply succeeded, so the version it replaced is no longer a
        # rollback target and no version other than the running one needs to
        # stay on disk. Also attempted from post_apply_manifest, which is the
        # only one of the two that fires on an application-update; the prune
        # is idempotent so whichever runs first wins and the other no-ops.
        if hook_info[LifecycleConstants.EXTRA][LifecycleConstants.APP_APPLIED]:
            try:
                self._prune_previous_ansible(app)
            except Exception as e:
                # Never fail an otherwise successful apply over cleanup.
                LOG.error("Failed to prune the retained playbook version: %s",
                          e)

    def post_apply_manifest(self, app, hook_info):
        """Post apply manifest actions

        Registered in addition to post_apply because the two hooks do not
        cover the same operations: sysinv raises no operation-timed hook on
        the application-update path, so post_apply never runs for an update,
        while this hook is raised for both a plain apply and an update. The
        retained playbook generation only ever exists during an update, so
        without this registration the prune could never reach a target.

        Registering the same work on both hooks follows the precedent set by
        the OIDC application plugin. On a plain apply both fire, a few
        milliseconds apart; _prune_previous_ansible is idempotent, so the
        second call finds no 'previous' pointer and returns.

        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object
        """
        self._post_update_image_actions(app)

        # Unlike post_apply, this hook is also raised when the manifest
        # failed to apply, so the success flag has to be honoured here -- a
        # failed update must keep its rollback target.
        if hook_info[LifecycleConstants.EXTRA].get(
                LifecycleConstants.MANIFEST_APPLIED):
            try:
                self._prune_previous_ansible(app)
            except Exception as e:
                # Never fail an otherwise successful apply over cleanup.
                LOG.error("Failed to prune the retained playbook version: %s",
                          e)

    def pre_remove(self, context, conductor_obj, hook_info):
        """Pre remove actions

        :param context: request context
        :param conductor_obj: conductor object
        :param hook_info: LifecycleHookInfo object

        """
        # Need to update sm stx_openstack runtime manifest first
        # to deprovision dbmon service prior to removing the
        # stx-openstack application
        conductor_obj._config_sm_stx_openstack(context)

    def post_remove(self, context, conductor_obj, hook_info):
        """Post remove actions

        :param context: request context
        :param conductor_obj: conductor object
        :param hook_info: LifecycleHookInfo object

        """
        if LifecycleConstants.EXTRA not in hook_info:
            raise exception.LifecycleMissingInfo("Missing {}".format(LifecycleConstants.EXTRA))
        if LifecycleConstants.APP_REMOVED not in hook_info[LifecycleConstants.EXTRA]:
            raise exception.LifecycleMissingInfo(
                "Missing {} {}".format(LifecycleConstants.EXTRA, LifecycleConstants.APP_REMOVED))

        if hook_info[LifecycleConstants.EXTRA][LifecycleConstants.APP_REMOVED]:
            # Update the VIM configuration.
            conductor_obj._update_vim_config(context)
            conductor_obj._update_radosgw_config(context)

    def pre_delete(self, app_op, app):
        """Pre delete actions.

        Called only on explicit application-delete (not application-remove).
        Purges the application's whole /opt/platform/ansible/ tree: the
        application is going away, so no version directory or rollback
        pointer needs to outlive it.
        """
        LOG.info("openstack pre_delete: full cleanup starting.")
        # Remove every deployed playbook version and tracking pointer.
        self._purge_ansible(app)

    def pre_update(self, app_op, app):
        """Pre update actions.

        Called only on explicit application-update.
        This deploys /opt/platform/ansible
        """
        LOG.info("openstack pre_update: ansible deploy starting.")
        # Perform pre update playbook deploy.
        self._deploy_ansible(app)

    def pre_downgrade(self, app_op, app):
        """Pre downgrade actions.

        sysinv raises this from perform_app_update when the target version is
        lower than the installed one. It is dispatched as a RESOURCE hook with
        PRE timing (sysinv/conductor/kube_app.py, the APP_DOWNGRADE_OP block),
        and ``app`` is the version being downgraded *from* -- the dispatch
        passes ``from_rpc_app``.

        Retires that version's playbooks and promotes the retained generation,
        so the tree does not keep a directory for a version the system is
        moving away from. It runs before the new (lower) version's tarball is
        uploaded, so the subsequent pre_update deploy re-establishes 'current'.
        """
        LOG.info("openstack pre_downgrade: retiring playbooks for %s.",
                 app.version)
        self._undeploy_ansible(app)

    def _delete_maridb_pvc_snapshots_if_exists(self) -> None:
        """
        Delete PVC snapshots if they exist.
        :return: None
        """
        nc = app_utils.get_number_of_controllers()

        for i in range(0, nc):
            pvc_name = f"mysql-data-mariadb-server-{i}"
            snapshot_name = f"snapshot-of-{pvc_name}"
            LOG.info(f"Trying to delete snapshot (if exists) '{snapshot_name}'")
            # We can ignore not found images. This is to avoid logging an error when the
            # apply hook is executed for the first time (not after an update) and the
            # snapshot doesn't exist yet.
            app_utils.delete_snapshot(snapshot_name, ignore_not_found=True)

    def _delete_app_specific_resources_post_remove(self, app_op, app, hook_info):
        """Delete application specific resources.

        :param app_op: AppOperator object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """
        lifecycle_utils.delete_local_registry_secrets(app_op, app, hook_info)
        lifecycle_utils.delete_persistent_volume_claim(app_op, common.HELM_NS_OPENSTACK)
        lifecycle_utils.delete_configmap(app_op, common.HELM_NS_OPENSTACK, self.APP_OPENSTACK_RESOURCE_CONFIG_MAP)
        app_utils.delete_dex_secret()
        app_utils.delete_storage_ca_cert_secret()
        app_utils.delete_aodh_rest_notifier_ca_cert_secret()
        lifecycle_utils.delete_namespace(app_op, common.HELM_NS_OPENSTACK)

        # Perform post remove LDAP-related actions.
        self._post_remove_ldap_actions()

    def _create_app_specific_resources_pre_apply(self, app_op, app, hook_info):
        """Add application specific resources.

        :param app_op: AppOperator object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """
        lifecycle_utils.create_local_registry_secrets(app_op, app, hook_info)

        try:
            kube = kubernetes.KubeOperator()
            # Create openstack namespace if it doesn't exist
            # Copy the latest configmap with the ceph monitor information
            # required by the application into the application namespace
            if kube.kube_get_config_map(
                    self.APP_OPENSTACK_RESOURCE_CONFIG_MAP,
                    common.HELM_NS_OPENSTACK):
                # Already have one. Delete it, in case it changed
                kube.kube_delete_config_map(
                    self.APP_OPENSTACK_RESOURCE_CONFIG_MAP,
                    common.HELM_NS_OPENSTACK)

            # Create required storage backend configmap
            self._pre_apply_copy_storage_backend_config(kube)

            # Perform pre apply LDAP-related actions.
            self._pre_apply_ldap_actions(app)

            # Create secret containing dex integration credentials
            app_utils.pre_apply_create_dex_resources_secret(kube)

            # Upgrade compatibility: copy legacy netapp-ca-cert before creating storage-ca-cert.
            app_utils.migrate_legacy_netapp_ca_cert_secret(kube)
            app_utils.create_storage_ca_cert_secret(kube)

            # Setup user provided Aodh notifier certificates
            app_utils.create_aodh_rest_notifier_ca_cert_secret(kube)
        except Exception as e:
            LOG.error(e)
            raise

    def _pre_apply_copy_storage_backend_config(self, kube):
        """Creates the respective config map from the selected storage backend.
        Called when creating specific app resources during pre-apply cycle.

        :param kube: AppOperator object

        Raises:
            LifecycleMissingInfo: Reports an issue when reading the source config map.
        """
        rook_ceph_available, _ = is_ceph_backend_available(ceph_type=constants.SB_TYPE_CEPH_ROOK)
        host_ceph_available, _ = is_ceph_backend_available(ceph_type=constants.SB_TYPE_CEPH)
        if rook_ceph_available:
            LOG.info(f"Read {self.APP_OPENSTACK_RESOURCE_CONFIG_MAP} config map"
                     "from rook-ceph namespace "
                     f"({app_constants.HELM_NS_ROOK_CEPH})")
            src_config_map_name = self.APP_OPENSTACK_RESOURCE_CONFIG_MAP
            src_config_map_ns = app_constants.HELM_NS_ROOK_CEPH
        elif host_ceph_available:
            LOG.info(f"Read {self.APP_KUBESYSTEM_RESOURCE_CONFIG_MAP} config map"
                     "from host-ceph namespace "
                     f"({common.HELM_NS_RBD_PROVISIONER})")
            src_config_map_name = self.APP_KUBESYSTEM_RESOURCE_CONFIG_MAP
            src_config_map_ns = common.HELM_NS_RBD_PROVISIONER
        else:
            LOG.warning("Ceph is not available, skipping Ceph ConfigMap copy")
            return

        config_map_body = kube.kube_read_config_map(src_config_map_name, src_config_map_ns)

        if not config_map_body:
            raise exception.LifecycleMissingInfo(
                f"Missing storage backend config map: {src_config_map_ns}/{src_config_map_name}")

        config_map_body.metadata.resource_version = None
        config_map_body.metadata.namespace = common.HELM_NS_OPENSTACK
        config_map_body.metadata.name = self.APP_OPENSTACK_RESOURCE_CONFIG_MAP

        # Create configmap with correct name
        kube.kube_create_config_map(
            common.HELM_NS_OPENSTACK,
            config_map_body)

    def _semantic_check_evaluate_app_reapply(self, app_op, app, hook_info):
        """Semantic check for evaluating app reapply

        This is an example of how to use the evaluate reapply semantic check.
        The same behavior could have been achieved by placing a filter in the metadata
        based on LifecycleConstants.TRIGGER_CONFIGURE_REQUIRED

        Example of equivalent behavior by adding filters to triggers in metadata:
        ---
        behavior:
          evaluate_reapply:
            triggers:
              - type: unlock
                filters:                    # This line was added
                - configure_required: True  # This line was added
              - type: force-unlock
                filters:                    # This line was added
                - configure_required: True  # This line was added

        :param app_op: AppOperator object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """
        if LifecycleConstants.EVALUATE_REAPPLY_TRIGGER not in hook_info[LifecycleConstants.EXTRA]:
            raise exception.LifecycleMissingInfo(
                "Missing {}".format(LifecycleConstants.EVALUATE_REAPPLY_TRIGGER))
        trigger = hook_info[LifecycleConstants.EXTRA][LifecycleConstants.EVALUATE_REAPPLY_TRIGGER]

        if LifecycleConstants.TRIGGER_TYPE not in trigger:
            raise exception.LifecycleMissingInfo(
                "Missing {} {}".format(LifecycleConstants.EVALUATE_REAPPLY_TRIGGER,
                                       LifecycleConstants.TRIGGER_TYPE))

        # At the moment of writing this focus is on keeping backwards compatibility
        # The logic was extracted and kept as it was
        if trigger[LifecycleConstants.TRIGGER_TYPE] in [constants.UNLOCK_ACTION, constants.FORCE_UNLOCK_ACTION]:
            if LifecycleConstants.TRIGGER_CONFIGURE_REQUIRED not in trigger:
                raise exception.LifecycleMissingInfo(
                    "Missing {} {}".format(LifecycleConstants.EVALUATE_REAPPLY_TRIGGER,
                                           LifecycleConstants.TRIGGER_CONFIGURE_REQUIRED))

            # For an unlock, the logic had 'configure_required' set to True
            if not trigger[LifecycleConstants.TRIGGER_CONFIGURE_REQUIRED]:
                raise exception.LifecycleSemanticCheckException(
                    "Trigger type {} expects {} to be true".format(
                        trigger[LifecycleConstants.TRIGGER_TYPE],
                        LifecycleConstants.TRIGGER_CONFIGURE_REQUIRED))
        elif trigger[LifecycleConstants.TRIGGER_TYPE] == constants.APP_EVALUATE_REAPPLY_TYPE_DETECTED_SWACT:
            # On host swacts, we must ensure that all controllers nodes have
            # their clients' working directories with the right permissions.
            working_directory = Path(app_utils.get_clients_working_directory())

            try:
                # If at least one of them has an invalid value, both will be
                # set to `None`. This will cause the clients' working
                # directory to be reconfigured (in terms of permissions).
                working_directory_owner = working_directory.owner()
                working_directory_group = working_directory.group()
            except KeyError:
                working_directory_owner = None
                working_directory_group = None

            if (
                working_directory.exists()
                and (
                    working_directory_owner != app_constants.CLIENTS_WORKING_DIR_USER
                    or working_directory_group != app_constants.CLIENTS_WORKING_DIR_GROUP
                )
            ):
                status = app_utils.reset_clients_working_directory_permissions(
                    path=str(working_directory)
                )
                if not status:
                    raise exception.LifecycleSemanticCheckException(
                        "Unable to reset clients' working directory "
                        f"`{str(working_directory)}` permissions."
                    )

    def _pre_apply_check(self, conductor_obj, app, hook_info):
        """Semantic check for evaluating app manual apply

        :param conductor_obj: conductor object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """
        # Check AIO-SX node stable state
        active_controller = utils.HostHelper.get_active_controller(conductor_obj.dbapi)
        if (utils.is_host_simplex_controller(active_controller) and
                not active_controller.vim_progress_status.startswith(
                constants.VIM_SERVICES_ENABLED)):
            LOG.info("%s requires application-apply, but some VIM services "
                "are not at services-enabled state on node %s. "
                "Application-apply rejected." % (app.name, active_controller.hostname))
            raise exception.LifecycleSemanticCheckException(
                "Application-apply rejected: operation is not allowed "
                "while the node {} not in {} state.".format(
                    active_controller.hostname, constants.VIM_SERVICES_ENABLED))

        # Check system type
        self._semantic_check_dc_system_type(app)

        # Check storage backends: availability, ESB required-field validation,
        # ESB secretRef resolvability, ESB backup StorageClass, and StorageClass
        # resolution/immutability.
        self._semantic_check_storage_backends()

        # Check vswitch configuration
        self._semantic_check_vswitch_config(conductor_obj.dbapi)

        # Check data network configuration
        self._semantic_check_datanetwork_config(conductor_obj.dbapi)

        # Check OIDC configuration when the feature is enabled
        self._semantic_check_oidc_config(conductor_obj.dbapi)

        # Check NetApp dual-SAN StorageClass sanType configuration
        self._semantic_check_netapp_san_storageclasses()

    def _pre_remove_check(self, conductor_obj, app, hook_info):
        """Semantic check for evaluating app manual remove

        :param conductor_obj: conductor object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """

        # Check if all servers were deleted before removing application
        self._semantic_check_openstack_vms_created()

    def _semantic_check_openstack_vms_created(self):
        """Evaluate app remove conditions."""

        # Fail if any servers are loaded.
        if len(app_utils.get_server_list()) == 0:
            LOG.info("Openstack has no server created, proceeding with application remove")
        else:
            raise exception.LifecycleSemanticCheckException(
                "There are OpenStack instances created in the system."
                " Please delete all Openstack instances before removing the application")

    def _semantic_check_storage_backends(self):
        """Pre-apply semantic checks for all storage backends.

        Generic orchestrator for every storage-backend validator (strict and
        ESB). Strict backend availability is probed once via
        ``_is_strict_backend_available()`` and shared with the availability
        sub-check.

        Sub-checks, in order:

        - ``_semantic_check_storage_backend_available()`` verifies that at least
          one storage backend (strict or ESB) is available and ready, and
          validates the required fields (``protocol``) of every enabled
          non-strict ESB backend.
        - ``_semantic_check_secretref()`` verifies that every non-empty
          ``secretRef`` references an existing Kubernetes Secret and that every
          declared Secret key exists.
        - ``_semantic_check_backend_storageclass()`` validates StorageClass
          resolution (fail-fast) and immutability for PVC-backed charts.

        Blocking rules:
        - Availability / required-field failures block only when no strict
          backend independently satisfies availability (a valid strict backend
          downgrades invalid ESB entries to a log).
        - secretRef and ESB backup StorageClass failures always block when they
          occur (i.e. when an ESB backend is in use), regardless of strict
          backend availability.
        - StorageClass resolution/immutability failures always block.

        Raises:
            LifecycleSemanticCheckException: If any sub-check fails per the
                blocking rules above.
        """
        strict_available, status = self._is_strict_backend_available()
        self._semantic_check_storage_backend_available(strict_available, status)
        self._semantic_check_secretref()
        self._semantic_check_backend_storageclass()

    def _is_strict_backend_available(self):
        """Probe strict (native) storage backend availability.

        Centralizes availability detection for the strict backends (Rook Ceph
        with fsid + manager API, and NetApp NFS/iSCSI/FC) so the orchestrator
        can compute it once and share it with every ESB sub-check.

        Returns:
            tuple[bool, str]: ``(available, status)`` where ``available`` is True
            when at least one strict backend is available and ready, and
            ``status`` is a human-readable summary of the probes (reused in the
            "no storage backends available" error message).
        """
        status = ""
        fsid_available = False
        rook_api_available = False
        backend_available = False
        ceph_available, _ = app_utils.is_ceph_backend_available(
            ceph_type=constants.SB_TYPE_CEPH
        )
        rook_ceph_available, _ = app_utils.is_ceph_backend_available(
            ceph_type=constants.SB_TYPE_CEPH_ROOK
        )
        netapp_backends_available = app_utils.check_netapp_backends()
        netapp_nfs_available = netapp_backends_available.get(
            app_constants.NETAPP_NFS_BACKEND_NAME,
            False
        )
        netapp_iscsi_available = netapp_backends_available.get(
            app_constants.NETAPP_ISCSI_BACKEND_NAME,
            False
        )
        netapp_fc_available = netapp_backends_available.get(
            app_constants.NETAPP_FC_BACKEND_NAME,
            False
        )
        status = f"ceph_available={ceph_available}, " \
                 f"rook_ceph_available={rook_ceph_available}, " \
                 f"netapp_nfs_available={netapp_nfs_available}, " \
                 f"netapp_iscsi_available={netapp_iscsi_available}, " \
                 f"netapp_fc_available={netapp_fc_available}"
        if rook_ceph_available:
            rook_api_available = app_utils.is_rook_ceph_api_available()
            fsid_available = app_utils.get_ceph_fsid() is not None
            backend_available = rook_api_available and fsid_available
            status += f", fsid_available={fsid_available}, " \
                      f"rook_api_available={rook_api_available}"

        if netapp_nfs_available:
            backend_available = True
        elif netapp_iscsi_available:
            backend_available = True
        elif netapp_fc_available:
            backend_available = True

        return backend_available, status

    def _semantic_check_storage_backend_available(self, strict_available,
                                                  status):
        """Checks if at least one of the supported storage backends
        is available and ready for openstack deployment.

        Extended for ESB: each enabled non-strict storage_backends entry must
        have a matching backends_conf entry with a valid protocol.
        A valid ESB entry counts as an available backend.
        When no backend is available the apply is blocked and the ESB validation
        errors are appended to the message. When a valid backend is available,
        invalid ESB entries are logged but do not block apply.

        Args:
            strict_available: Whether a strict backend is available (probed once
                by ``_is_strict_backend_available()``).
            status: Human-readable strict backend probe summary.

        Raises:
            LifecycleSemanticCheckException: no storage backend available for
                                             openstack deployment.
        """
        esb_available, esb_errors = self._validate_esb_backend_configs()
        backend_available = strict_available or esb_available

        if not backend_available:
            err_msg = "No storage backends available and ready for openstack " \
                      f"deployment. status: {status}"
            if esb_errors:
                err_msg += " ESB backend validation errors: " + \
                    "; ".join(esb_errors)
            LOG.error(f"{err_msg}")
            raise exception.LifecycleSemanticCheckException(err_msg)

        # A valid backend is available: ESB validation errors (if any) are
        # logged but do not block apply, since strict or other ESB backends
        for esb_error in esb_errors:
            LOG.error(
                "Ignoring invalid ESB backend configuration because a valid "
                f"storage backend is available: {esb_error}")

    def _validate_esb_backend_configs(self):
        """Validate enabled non-strict (ESB) storage_backends entries.

        For each enabled entry in ``storage_conf.storage_backends`` whose name is
        not a strict-backend name, looks up the matching
        ``storage_conf.backends_conf`` entry and validates its required fields.
        The ``volume_backend`` dict is treated as an opaque pass-through and its
        contents are not validated.


        Returns:
            tuple[bool, list[str]]: ``(available, errors)`` where ``available``
            is True when at least one enabled ESB backend passed validation, and
            ``errors`` is the list of human-readable validation errors for the
            enabled ESB backends that failed.
        """
        errors = []
        available = False

        enabled_backends = app_utils.get_enabled_storage_backends_from_override()
        backends_conf = app_utils.get_backends_conf()

        for name in enabled_backends:
            if app_utils.is_strict_backend(name):
                # Strict backends use their own auto-detection logic; any
                # matching backends_conf entry is silently ignored.
                continue

            entry = backends_conf.get(name)
            if not entry:
                errors.append(
                    f"ESB [{name}]: no matching storage_conf.backends_conf "
                    "entry found. Every non-strict backend enabled in "
                    "storage_conf.storage_backends requires a backends_conf "
                    "entry declaring at least a supported 'protocol'")
                continue

            entry_errors = self._validate_esb_entry(name, entry)
            if entry_errors:
                errors.extend(entry_errors)
            else:
                available = True

        return available, errors

    def _validate_esb_entry(self, name, entry):
        """Validate the required fields of a single ESB backends_conf entry.

        Args:
            name: The backend name (matches the storage_backends entry).
            entry: The backends_conf entry dict.

        Returns:
            list[str]: Validation errors for this entry (empty when valid).
        """
        errors = []
        valid_protocols = sorted(app_constants.VALID_ESB_PROTOCOLS)

        protocol = entry.get("protocol")
        if not protocol:
            errors.append(
                f"ESB [{name}]: missing required field 'protocol' "
                f"(one of {valid_protocols}).")
        elif protocol == "rbd":
            # rbd is internal-only: it represents the ceph strict backend's
            # contribution to active_protocols and cannot be declared by
            # operators in backends_conf.
            errors.append(
                f"ESB [{name}]: protocol 'rbd' is internal-only and cannot be "
                f"declared by operators. Valid protocols: {valid_protocols}.")
        elif protocol not in app_constants.VALID_ESB_PROTOCOLS:
            errors.append(
                f"ESB [{name}]: invalid protocol '{protocol}'. "
                f"Valid protocols: {valid_protocols}.")

        # k8s_storage_class is intentionally NOT required here. A missing (or
        # 'none') value simply means the backend does not provision PVCs, which
        # is valid for a pure Cinder volume backend (e.g. iSCSI/FC over the
        # network). When a StorageClass is actually needed, the failure is
        # raised by the context that needs it:
        #   - PVC provisioning (MariaDB/RabbitMQ/Glance-PVC/Nova-PVC) ->
        #     _check_storageclass_resolution()

        return errors

    def _semantic_check_secretref(self):
        """Validate ESB credential injection via secretRef.

        For each enabled non-strict backend whose backends_conf entry declares a
        non-empty ``secretRef``, verifies that:

        - ``secretRef.name`` references an existing Kubernetes Secret in the
          namespace given by ``secretRef.namespace`` (defaulting to the
          openstack namespace when omitted), and
        - every right-hand-side key declared in ``secretRef.keys`` exists in the
          referenced Secret.

        A secretRef is only declared on an ESB backend that is in use, so any
        failure here always blocks apply, regardless of whether a strict backend
        is also available.

        Raises:
            LifecycleSemanticCheckException: If a referenced Secret does not
                exist or a declared key is missing.
        """
        enabled_backends = app_utils.get_enabled_storage_backends_from_override()
        backends_conf = app_utils.get_backends_conf()

        errors = []
        kube = None
        for name in enabled_backends:
            if app_utils.is_strict_backend(name):
                continue

            entry = backends_conf.get(name)
            if not entry:
                # Missing backends_conf entry is reported by the availability
                # check; nothing to validate here.
                continue

            secret_ref = entry.get("secretRef")
            if not secret_ref:
                # secretRef is optional and may be {} / absent.
                continue

            secret_name = secret_ref.get("name")
            keys = secret_ref.get("keys") or {}
            namespace = (secret_ref.get("namespace")
                         or app_constants.HELM_NS_OPENSTACK)

            if not secret_name:
                errors.append(
                    f"ESB [{name}]: secretRef is declared but is missing the "
                    "required 'name' field.")
                continue

            if kube is None:
                kube = kubernetes.KubeOperator()

            try:
                secret = kube.kube_get_secret(secret_name, namespace)
            except Exception as e:
                errors.append(
                    f"ESB [{name}]: unable to read Secret '{secret_name}' in "
                    f"namespace '{namespace}': {e}")
                continue

            if secret is None:
                errors.append(
                    f"ESB [{name}]: Secret '{secret_name}' not found in "
                    f"namespace '{namespace}'. Create the Secret before "
                    "applying the application.")
                continue

            # Report missing keys in a incomplete or empty Secret
            secret_data = getattr(secret, "data", None) or {}

            missing_keys = sorted(
                {secret_key for secret_key in keys.values()
                 if secret_key not in secret_data}
            )
            if missing_keys:
                errors.append(
                    f"ESB [{name}]: Secret '{secret_name}' in namespace "
                    f"'{namespace}' is missing required key(s): "
                    f"{', '.join(missing_keys)}.")

        if errors:
            raise exception.LifecycleSemanticCheckException("; ".join(errors))

    def _semantic_check_oidc_config(self, dbapi):
        """Validate Dex enablement, endpoint domain availability,
        mandatory OIDC parameters and Dex health.

        Args:
            dbapi: Sysinv DB connection used to query service parameters.

        Raises:
            LifecycleSemanticCheckException: Missing the endpoint_domain
              configuration for OpenStack, mandatory for DEX integration.
            LifecycleSemanticCheckException: Missing OIDC parameters on subcloud.
            LifecycleSemanticCheckException: Dex health check failed.
        """
        if is_dex_enabled():
            if not get_endpoint_domain(dbapi):
                raise exception.LifecycleSemanticCheckException(
                    "Missing the endpoint_domain configuration for OpenStack,"
                    " mandatory for DEX integration.")

            if not oidc_parameters_exist(dbapi):
                raise exception.LifecycleSemanticCheckException("Missing OIDC parameters.")

            if not check_dex_healthy(dbapi, True):
                raise exception.LifecycleSemanticCheckException("Dex health check failed.")

    def _get_vswitch_label_combinations(self):
        return app_constants.VSWITCH_ALLOWED_COMBINATIONS

    def _semantic_check_vswitch_config(self, dbapi):

        labels, conflicts = app_utils.get_system_vswitch_labels(
            dbapi, self._get_vswitch_label_combinations())

        if len(conflicts) == 0:
            if len(labels) == 0:
                raise exception.LifecycleSemanticCheckException(
                    "There are no openstack-enabled compute nodes")
        elif app_constants.VSWITCH_LABEL_NONE in conflicts:
            conflicts.remove(app_constants.VSWITCH_LABEL_NONE)
            if len(conflicts) == 0:
                if len(labels) == 0:
                    raise exception.LifecycleSemanticCheckException(
                        "None of the openstack-enabled compute nodes have vswitch configured")
                else:
                    raise exception.LifecycleSemanticCheckException(
                        "There are openstack-enabled compute nodes with no vswitch configuration")
            else:
                raise exception.LifecycleSemanticCheckException(
                    "There are openstack-enabled compute nodes with no vswitch configuration "
                    "and there are conflicting vswitch configurations: "
                    f"{', '.join(sorted(conflicts))}")
        elif len(conflicts) >= 1:
            raise exception.LifecycleSemanticCheckException(
                "There are conflicting vswitch configurations: "
                f"{', '.join(sorted(conflicts))}")

    def _semantic_check_datanetwork_config(self, dbapi):
        hosts = dbapi.ihost_get_list()
        labels = dbapi.label_get_all()

        labels_by_host = app_utils.get_labels_by_host(labels)
        enabled_hosts = app_utils.get_openstack_enabled_compute_nodes(hosts, labels_by_host)

        db_ifdatanets = app_utils.get_interface_datanets(dbapi)

        hosts_without_ifdatanets = set()
        hosts_by_id = dict()
        for host in enabled_hosts:
            hosts_by_id[host.id] = host
            hosts_without_ifdatanets.add(host.id)

        datanets_by_iface = dict()
        conflicted_ifaces = dict()
        conflicted_iface_hosts = set()
        for if_datanet in db_ifdatanets:
            if if_datanet.forihostid not in hosts_by_id:
                continue
            hosts_without_ifdatanets.discard(if_datanet.forihostid)
            ifdn_list = datanets_by_iface.setdefault(if_datanet.interface_id, [])
            ifdn_list.append(if_datanet)
            if len(ifdn_list) == 2:
                # Comparison is made this way because if the interface has more than 1 associated
                # datanet, it has to be placed in conflicted_ifaces just once. Since ifdn_list is
                # incremented 1 by 1, if len(ifdn_list) is any number greater than 2, it means at
                # some point it was 2, so the interface has already been placed in the dict.
                conflicted_ifaces[if_datanet.interface_id] = {"host": if_datanet.forihostid,
                                                              "ifname": if_datanet.ifname}
                conflicted_iface_hosts.add(if_datanet.forihostid)

        if conflicted_ifaces:
            # If there are more than MAX_HOSTS_FOR_DETAILED_MSG hosts with conflicted interfaces,
            # format exception message with host count only, to avoid too long messages.
            if (count := len(conflicted_iface_hosts)) > self.MAX_HOSTS_FOR_DETAILED_MSG:
                raise exception.LifecycleSemanticCheckException(
                    f"There are {count} hosts in which multiple data networks are associated with "
                    "the same interface")
            items = []
            for iface_id, data in conflicted_ifaces.items():
                datanets = [dn.datanetwork_name for dn in datanets_by_iface[iface_id]]
                host = hosts_by_id[data['host']].hostname
                text = f"{data['ifname']} in {host} ({', '.join(datanets)})"
                items.append(text)
            raise exception.LifecycleSemanticCheckException(
                f"Interfaces cannot have multiple associated data networks: {', '.join(items)}")

        if (count := len(hosts_without_ifdatanets)) > 0:
            # If there are more than MAX_HOSTS_FOR_DETAILED_MSG hosts without associated datanets,
            # format exception message with host count only, to avoid too long messages.
            if count > self.MAX_HOSTS_FOR_DETAILED_MSG:
                raise exception.LifecycleSemanticCheckException(
                    f"There are {count} hosts in which no data network is "
                    "associated with an interface")
            sorted_hosts = sorted(hosts_without_ifdatanets)
            raise exception.LifecycleSemanticCheckException(
                "The following hosts have no data networks associated with interfaces: "
                f"{', '.join([hosts_by_id[id].hostname for id in sorted_hosts])}")

    def _post_upload_ldap_actions(self, app):
        """Perform post upload LDAP-related actions.

        On a central cloud (system controller), create the LDAP group
        'openstack' so that it gets synced to subclouds. On non-central
        systems, this is a no-op since the pre-apply flow handles
        LDAP group creation.

        :param app: AppOperator.Application object
        """
        if not app_utils.is_central_cloud():
            return

        group_exists = ldap.check_group(
            app_constants.CLIENTS_WORKING_DIR_GROUP
        )
        if not group_exists:
            status = ldap.add_group(app_constants.CLIENTS_WORKING_DIR_GROUP)
            if not status:
                LOG.error(
                    "Failed to create LDAP group '%s' on central cloud "
                    "during app upload. Subclouds will not be able to "
                    "apply %s until this group is created.",
                    app_constants.CLIENTS_WORKING_DIR_GROUP,
                    app.name
                )

    def _pre_apply_ldap_actions(self, app):
        """Perform pre apply LDAP-related actions.

        :param app: AppOperator.Application object
        :raises KubeAppApplyFailure: If at least one application specific
                                     resource fails to be created.
        """

        # Create group `openstack`. If in a subcloud, just notify the group
        # should be created in the controller.
        group_exists = ldap.check_group(
            app_constants.CLIENTS_WORKING_DIR_GROUP
        )
        if not group_exists:
            if app_utils.is_subcloud():
                raise exception.KubeAppApplyFailure(
                    name=app.name,
                    version=app.version,
                    reason=(
                        "When in a subcloud, a LDAP group named \"openstack\" "
                        "with gid \"1001\" should be added in the controller."
                    )
                )
            else:
                status = ldap.add_group(app_constants.CLIENTS_WORKING_DIR_GROUP)
                if not status:
                    raise exception.KubeAppApplyFailure(
                        name=app.name,
                        version=app.version,
                        reason=(
                            "Unable to create application specific resource: "
                            f"Group `{app_constants.CLIENTS_WORKING_DIR_GROUP}` "
                            "(LDAP)."
                        )
                    )

        # Get clients' working directory path.
        # (It can be either the default or a user-defined one)
        working_directory = app_utils.get_clients_working_directory()

        # If it's a user-defined working directory path,
        # delete the default one to avoid leftovers.
        if (
            Path(app_constants.CLIENTS_WORKING_DIR).exists()
            and working_directory != app_constants.CLIENTS_WORKING_DIR
        ):
            app_utils.delete_clients_working_directory(
                path=app_constants.CLIENTS_WORKING_DIR
            )

        # Finally, create the clients' working directory.
        status = app_utils.create_clients_working_directory(
            path=working_directory
        )
        if not status:
            raise exception.KubeAppApplyFailure(
                name=app.name,
                version=app.version,
                reason=(
                    "Unable to create application specific resource: "
                    "OpenStack clients' working directory "
                    f"`{working_directory}`."
                )
            )

    def _post_remove_ldap_actions(self):
        """Perform post remove LDAP-related actions."""

        # Try to delete the OpenStack clients' working directory.
        # If successful, also delete group `openstack`.
        status = app_utils.delete_clients_working_directory()
        if status:
            group_exists = ldap.check_group(
                app_constants.CLIENTS_WORKING_DIR_GROUP
            )
            if group_exists:
                ldap.delete_group(app_constants.CLIENTS_WORKING_DIR_GROUP)

    def _pre_update_actions(self, app):
        """Perform all pre update actions.

        :param conductor_obj: conductor object
        :param app: AppOperator.Application object

        """
        images_base_dir = app.sync_imgfile.split(app.name)[0]
        app_version_list = sorted(
            app_utils.get_app_version_list(images_base_dir, app.name)
        )
        if len(app_version_list) <= 1:
            # Pre-update actions aren't required for apply operations
            return
        self._pre_update_backup_actions(app)
        self._pre_update_cleanup_actions()

    def _pre_update_cleanup_actions(self):
        """Perform pre update cleanup actions."""
        return

    def _pre_update_backup_actions(self, app):
        """Perform pre update backup actions.

        :param app: AppOperator.Application object

        """
        # Create mariadb's PVC snapshots
        nc = app_utils.get_number_of_controllers()
        SNAPSHOT_CLASS_NAME = "rbd-snapshot"

        for i in range(0, nc):
            pvc_name = f"mysql-data-mariadb-server-{i}"
            snapshot_name = f"snapshot-of-{pvc_name}"
            LOG.info(f"Trying to take a snapshot from PVC {pvc_name}")
            app_utils.create_pvc_snapshot(snapshot_name, pvc_name, SNAPSHOT_CLASS_NAME, path=app.inst_path)

    @staticmethod
    def _is_failed_update_version(app, hook_info):
        """Whether this recover dispatch carries the version that failed.

        The recover hook is raised twice with the same 'extra' payload: once
        with the version the update failed on, and once, after the recovery
        has completed, with the version that was restored.
        ``EXTRA[FROM_APP_VERSION]`` names the failed version in both, so
        comparing it against the dispatched application tells the two apart.

        Falls back to True when the information is unavailable, so a missing
        payload retires the failed version's playbooks rather than silently
        leaving them behind.

        Args:
            app (AppOperator.Application): Application being dispatched
            hook_info (LifecycleHookInfo): Recover hook info

        Returns:
            bool: True if ``app`` is the version the update failed on.
        """
        try:
            failed_version = hook_info[LifecycleConstants.EXTRA][
                LifecycleConstants.FROM_APP_VERSION]
        except (KeyError, TypeError):
            LOG.warning("Recover hook carried no %s; assuming %s is the "
                        "failed version",
                        LifecycleConstants.FROM_APP_VERSION, app.version)
            return True
        return app.version == failed_version

    def _recover_actions(self, app_op, app, hook_info):
        """Perform all recover actions.

        Args:
            app_op (AppOperator): System Inventory AppOperator object
            app (AppOperator.Application): Application we are recovering from
            hook_info (LifecycleHookInfo): Recover hook info. Used to tell the
                two recover dispatches apart; see _is_failed_update_version.
        """
        self._recover_backup_snapshot(app)
        self._recover_app_resources_failed_update(app_op, app)

        # Retire the failed version's playbooks and promote the retained
        # generation into 'current'. This is deliberately driven from here
        # rather than from _recover_app_resources_failed_update: that method
        # returns early when only one application version is present on the
        # system, and playbook retirement must not be conditional on whether
        # the FluxCD resource recovery was able to proceed.
        #
        # Guarded because the hook is dispatched twice. Undeploying on the
        # second dispatch would remove the tree belonging to the version that
        # was just recovered to and unlink 'current' along with it.
        if self._is_failed_update_version(app, hook_info):
            self._undeploy_ansible(app)
        else:
            LOG.info("Skipping playbook undeployment for %s %s: this recover "
                     "dispatch carries the recovered version, not the failed "
                     "one", app.name, app.version)

    def _recover_app_resources_failed_update(self, app_op, app):
        """Perform resource recover after failed update

        Args:
            app_op (AppOperator): System Inventory AppOperator object
            app (AppOperator.Application): Application we are recovering from
        """

        images_base_dir = app.sync_imgfile.split(app.name)[0]
        app_version_list = sorted(
            app_utils.get_app_version_list(images_base_dir, app.name)
        )
        if len(app_version_list) == 1:
            LOG.error(f"Can't recover resources, only version "
                      f"{app_version_list[0]} of {app.name} application is "
                      "available on the system")
            return
        elif len(app_version_list) == 0:
            LOG.error(f"Can't recover resources, no version of {app.name} "
                      "application is available on the system")
            return

        if app_version_list[0] != app.version:
            from_version = app_version_list[0]
        else:  # support for downgrading process
            from_version = app_version_list[1]
        to_version = app.version
        LOG.info(f"Recovering {app.name} resources after the app failed to "
                 f"update from version {from_version} to version {to_version}")

        # The following issue related to app recovery process being sunddenly
        # aborted by the Application Framework (AppFwk) was fixed in
        # starlingx master branch and might be included in stx-11 release:
        # https://launchpad.net/bugs/2111929
        # This ports the fix to the app lifecycle so the issue didn't affect the
        # app update recovery on stx-10 platform. This might be removed for app
        # versions supposed to run only on future versions of stx platform.
        LOG.warn("Deregistering abort to start app recovery operation")
        app_op._deregister_app_abort(app.name)

        # Downgrading is not officially supported for MariaDB:
        # https://mariadb.com/kb/en/downgrading-between-major-versions-of-mariadb/
        # Because of that, we need to delete the Helmrelease for the new MariaDB
        # before deploying the old one.
        # Only do this when the MariaDB chart version actually changed: deleting
        # it when the version is unchanged would leave the cluster without
        # MariaDB, as FluxCD can't reconcile a resource that no longer exists.
        # If the version can't be determined, skip the deletion.
        recovered_mariadb_version = app_utils.get_mariadb_chart_version(
            app.name, from_version)
        failed_mariadb_version = app_utils.get_mariadb_chart_version(
            app.name, to_version)

        mariadb_deleted = False
        if (recovered_mariadb_version is not None and
                failed_mariadb_version is not None and
                recovered_mariadb_version != failed_mariadb_version):
            LOG.info(
                "MariaDB chart version changed (failed update used "
                f"{failed_mariadb_version}, recovering to "
                f"{recovered_mariadb_version}); deleting the MariaDB "
                "HelmRelease so the recovered version can be reinstalled "
                "cleanly from the restored PVC snapshot."
            )
            app_utils.delete_kubernetes_resource(
                resource_type='helmrelease',
                resource_name=app_constants.FLUXCD_HELMRELEASE_MARIADB
            )
            mariadb_deleted = True
        else:
            LOG.info(
                "MariaDB chart version unchanged "
                f"(version: {failed_mariadb_version}); skipping MariaDB "
                "HelmRelease deletion during recovery."
            )

        # Force FLuxCD reconciliation for all the application helmreleases.
        # By default the AppFwk only force reconciliation for app updates,
        # but not for app recovery
        # A deleted MariaDB HelmRelease is excluded to avoid a 'not found'
        # reconciliation error; the AppFwk recreates it later.
        exclude_charts = (
            [app_constants.FLUXCD_HELMRELEASE_MARIADB] if mariadb_deleted
            else None
        )
        app_utils.force_app_reconciliation(
            app_op, app, exclude_charts=exclude_charts)

    def _post_update_image_actions(self, app):
        """Perform post update actions, deleting residual images.

        :param app: AppOperator.Application object
        """
        images_base_dir = app.sync_imgfile.split(app.name)[0]
        app_version_list = app_utils.get_app_version_list(images_base_dir, app.name)
        if len(app_version_list) > 1:
            LOG.info("Deleting unused images for app %s", app.name)
            residual_images = app_utils.get_residual_images(app.sync_imgfile, app.version, app_version_list)

            if len(residual_images) > 0:
                app_utils.delete_residual_images(residual_images)

    def _recover_backup_snapshot(self, app):
        """Perform pre recover backup actions

        :param app: AppOperator.Application object

        """
        # Restore mariadb's PVCs if snapshots were taken
        nc = app_utils.get_number_of_controllers()
        STATEFULSET_NAME = "mariadb-server"

        for i in range(0, nc):
            pvc_name = f"mysql-data-mariadb-server-{i}"
            snapshot_name = f"snapshot-of-{pvc_name}"
            LOG.info(f"Trying to restore a snapshot from PVC {pvc_name}")
            app_utils.restore_pvc_snapshot(snapshot_name, pvc_name, STATEFULSET_NAME, path=app.inst_path)

    def _semantic_check_dc_system_type(self, app):
        """Check what type of DC system is running.

        Raises:
            LifecycleSemanticCheckException: Application cannot be applied
                                            on Central Controller.
        """
        if app_utils.is_central_cloud():
            LOG.info("%s apply rejected: application cannot be applied on "
                     "Central Controller." % app.name)
            raise exception.LifecycleSemanticCheckException(
                "Application cannot be applied on Central Controller."
            )

    def _semantic_check_backend_storageclass(self):
        """Validate StorageClass resolution and immutability for app PVCs.

        Orchestrates two focused sub-checks (Single Responsibility principle):

        - ``_check_storageclass_resolution()`` runs on every application-apply
          (fresh install and re-apply). It fails fast when a PVC-requiring
          chart's priority list resolves to no available backend, replacing the
          previous silent fallback to the hardcoded ``general`` StorageClass.

        - ``_check_storageclass_immutability()`` runs only when PVCs already
          exist in the openstack namespace. It blocks in-place StorageClass
          migration for the MariaDB and RabbitMQ PVCs.

        Raises:
            LifecycleSemanticCheckException:
                - If a chart's priority list resolves to no available backend.
                - If a StorageClass change is detected on an existing PVC.
        """
        self._check_storageclass_resolution()
        self._check_storageclass_immutability()

    def _check_storageclass_resolution(self):
        """Fail fast when a required PVC StorageClass cannot be resolved.

        Runs on every application-apply. For each chart that requires a
        PVC-backed StorageClass in the current configuration (MariaDB, RabbitMQ,
        Glance in PVC mode, Nova ephemeral PVC, and Cinder backup when it uses a
        PVC-backed driver), verifies that its configured priority list resolves
        to at least one available backend with a non-``none`` StorageClass.

        Replaces the previous silent fallback to the hardcoded ``general``
        StorageClass: if a priority list resolves to nothing, apply is blocked
        with a clear error identifying the chart and the configured priority
        list.

        Raises:
            LifecycleSemanticCheckException:
                - If any required chart's priority list resolves to no
                  available backend with a valid StorageClass.
        """
        for requirement in get_pvc_storageclass_requirements():
            if not requirement['storage_class']:
                raise exception.LifecycleSemanticCheckException(
                    f"Unable to resolve a Kubernetes StorageClass for the "
                    f"\"{requirement['chart']}\" chart: none of the backends in "
                    f"the configured priority list {requirement['priority_list']} "
                    f"resolve to an available backend with a valid "
                    f"k8s_storage_class. Update the priority list to reference a "
                    f"backend that maps to an existing StorageClass, or provision "
                    f"the required StorageClass before applying the application."
                )

    def _check_storageclass_immutability(self):
        """Enforce StorageClass immutability for application PVCs.

        This semantic check ensures that app PVC's remain bound to the StorageClass
        they were originally deployed with. Migration between different StorageClass
        is not supported.

        The check validates that the StorageClass currently used by the MariaDB and
        RabbitMQ PVCs didn't had changes.

        If a different StorageClass is detected, the check fails intentionally,
        instructing the user to perform a backup and redeploy instead of attempting
        an in-place StorageClass migration.

        The check is skipped if the OpenStack namespace or required PVCs do not exist.

        Raises: LifecycleSemanticCheckException:
            - If there was a change in the StorageClass
        """
        if not check_if_namespace_exists(app_constants.HELM_NS_OPENSTACK):
            LOG.info(f"{app_constants.HELM_NS_OPENSTACK} namespace doesn't exist, "
                        "skipping StorageClasses semantic check")
            return

        if not check_if_pvc_exists_in_a_namespace(app_constants.HELM_NS_OPENSTACK):
            LOG.info(f"There is no PVCs in the {app_constants.HELM_NS_OPENSTACK} namespace, "
                        "skipping StorageClasses semantic check")
            return

        mariadb_priority_list = get_storage_backends_priority_list(app_constants.HELM_CHART_MARIADB)
        mariadb_available_backends = get_available_volume_backends(
            chart_name=app_constants.HELM_CHART_MARIADB
        )
        mariadb_current_storageclass = get_pvc_storageclass(app_constants.MARIADB_PVC_NAME)
        mariadb_storageclass_change_validation, mariadb_new_storageclass = check_storageclass_change(
            mariadb_priority_list,
            mariadb_available_backends,
            mariadb_current_storageclass
             )
        rabbitmq_priority_list = get_storage_backends_priority_list(app_constants.HELM_CHART_RABBITMQ)
        rabbitmq_available_backends = get_available_volume_backends(
            chart_name=app_constants.HELM_CHART_RABBITMQ
        )
        rabbitmq_current_storageclass = get_pvc_storageclass(app_constants.RABBITMQ_PVC_NAME)
        rabbitmq_storageclass_change_validation, rabbitmq_new_storageclass = check_storageclass_change(
            rabbitmq_priority_list,
            rabbitmq_available_backends,
            rabbitmq_current_storageclass
             )

        if (not mariadb_storageclass_change_validation
              and not rabbitmq_storageclass_change_validation):
            return

        if mariadb_storageclass_change_validation:
            raise exception.LifecycleSemanticCheckException(
                f"{app_constants.HELM_CHART_MARIADB} is currently running using "
                f"StorageClass:\"{mariadb_current_storageclass}\" while is trying to reapply "
                f"with StorageClass:\"{mariadb_new_storageclass}\" and migration is not supported. "
                "Please backup your data and remove/apply the application to modify the current StorageClass."
            )

        if rabbitmq_storageclass_change_validation:
            raise exception.LifecycleSemanticCheckException(
                f"{app_constants.HELM_CHART_RABBITMQ} is currently running using "
                f"StorageClass:\"{rabbitmq_current_storageclass}\" while is trying to reapply "
                f"with StorageClass:\"{rabbitmq_new_storageclass}\" and migration is not supported. "
                "Please backup your data and remove/apply the application to modify the current StorageClass."
            )

    def _semantic_check_netapp_san_storageclasses(self):
        """Check that NetApp SAN StorageClasses define parameters.sanType when
        both iSCSI and FC backends are enabled simultaneously.

        When only one SAN backend is enabled, a single StorageClass with only
        ``parameters.backendType: ontap-san`` is sufficient — the driver picks
        it up unambiguously. When both backends are active, each StorageClass
        must additionally declare ``parameters.sanType`` (``iscsi`` or ``fcp``)
        so that the override generator can correctly associate each StorageClass
        with its backend. Without ``sanType``, both backends resolve to the same
        StorageClass (whichever kubectl returns first), which causes incorrect
        volume provisioning at runtime.

        The check is skipped when fewer than two SAN backends are enabled or
        when no StorageClasses with ``backendType: ontap-san`` exist.

        Raises:
            LifecycleSemanticCheckException: if both iSCSI and FC are enabled
                and none of the matching StorageClasses define ``sanType``.
        """
        backends = check_netapp_backends()
        iscsi_enabled = backends.get(app_constants.NETAPP_ISCSI_BACKEND_NAME, False)
        fc_enabled = backends.get(app_constants.NETAPP_FC_BACKEND_NAME, False)

        if not (iscsi_enabled and fc_enabled):
            # Single-SAN or no SAN — sanType is not required
            return

        # Query all StorageClasses for the ontap-san backendType, emitting
        # name and sanType per line (empty string when sanType is absent).
        driver = app_constants.BACKEND_TYPE_NETAPP_ISCSI  # "ontap-san" — same for FC
        jsonpath = (
            f"{{range .items[?(@.parameters.backendType==\"{driver}\")]}}"
            r"{.metadata.name}"
            "{\"\t\"}"
            r"{.parameters.sanType}"
            "{\"\\n\"}"
            r"{end}"
        )
        cmd = [
            "kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
            "get", "storageclass",
            "-o", f"jsonpath={jsonpath}",
        ]
        try:
            output = app_utils.send_cmd_read_response(cmd, log=False)
        except Exception as e:
            LOG.warning(
                f"Unable to query StorageClasses for sanType check: {e}. "
                "Skipping check."
            )
            return

        if not output:
            # No ontap-san StorageClasses present — nothing to validate
            return

        san_types_found = {
            line.partition("\t")[2].strip()
            for line in output.splitlines()
            if line.strip()
        }
        required_san_types = {
            app_constants.NETAPP_ISCSI_SAN_TYPE,  # "iscsi"
            app_constants.NETAPP_FC_SAN_TYPE,      # "fcp"
        }
        missing = required_san_types - san_types_found

        if missing:
            raise exception.LifecycleSemanticCheckException(
                "Both NetApp iSCSI and FC backends are enabled but the following "
                f"sanType values are not declared on any StorageClass with "
                f"backendType '{driver}': {sorted(missing)}. "
                "When both SAN backends are active, each StorageClass must "
                "declare parameters.sanType ('iscsi' or 'fcp') so that each "
                "backend resolves to the correct StorageClass. "
                "Please update your StorageClass definitions before applying."
            )

    def _deploy_ansible(self, app):
        """Deploy application-owned ansible playbooks to /opt/platform/ansible.

        Source:  <app.inst_path>/ansible/
        Target:  /opt/platform/ansible/<release>/<app-name>/<version>/
        Symlink: /opt/platform/ansible/<release>/<app-name>/current -> <version>/

        On each deploy the tracking pointer rotates current -> previous, so
        the version being replaced becomes the rollback target for the
        update now starting. 'previous' exists solely for that purpose --
        see _undeploy_ansible, which promotes it back to 'current' when an
        update fails, and _prune_previous_ansible, which drops it once the
        apply has succeeded. At rest only 'current' remains.

        Anything the pointer still names from an earlier cycle is two
        generations back and is pruned here, which covers an update that
        was interrupted before its own post-apply cleanup ran. A dangling
        pointer (its target directory already removed) is handled rather
        than silently skipped.

        /opt/platform/ is DRBD-replicated to the standby controller, so a
        single write on the active controller is automatically mirrored.
        Graceful skip when the tarball does not contain an ansible/
        directory.
        """
        source_dir = os.path.join(
            app.inst_path, app_constants.ANSIBLE_TARBALL_SUBDIR)
        if not os.path.isdir(source_dir):
            LOG.info(
                "No ansible directory in tarball at %s; "
                "skipping playbook deployment", source_dir)
            return

        release = tsc.SW_VERSION
        app_name = app.name
        version = app.version

        app_base = os.path.join(
            app_constants.ANSIBLE_DEPLOY_BASE, release, app_name)
        target_dir = os.path.join(app_base, version)
        current_link = os.path.join(
            app_base, app_constants.ANSIBLE_CURRENT_LINK)
        previous_link = os.path.join(
            app_base, app_constants.ANSIBLE_PREVIOUS_LINK)

        os.makedirs(app_base, exist_ok=True)

        # Stage to a temp dir within app_base so rename is on the same
        # filesystem (atomic).
        tmp_dir = tempfile.mkdtemp(
            prefix=".{}-".format(version), dir=app_base)
        tmp_link = current_link + ".new"
        try:
            staged_dir = os.path.join(tmp_dir, version)
            shutil.copytree(source_dir, staged_dir)

            # Atomic replacement of the version directory.
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            os.rename(staged_dir, target_dir)

            # The version 'current' names right now becomes the single
            # retained rollback generation.
            current_version = None
            if os.path.islink(current_link):
                current_version = os.path.basename(
                    os.readlink(current_link).rstrip("/"))

            # Enforce the one-prior-generation cap: whatever 'previous' still
            # names is two generations back and is dropped from disk before
            # 'current' rotates into its place.
            self._prune_link(previous_link, app_base,
                             protected={version, current_version})
            self._rotate_link(current_link, previous_link)

            # Atomically publish 'current' -> <version>. Write a new symlink
            # under a temp name, then os.rename over 'current'. os.rename
            # atomically replaces an existing symlink, so 'current' is never
            # observed missing by a concurrent reader.
            if os.path.lexists(tmp_link):
                os.unlink(tmp_link)
            os.symlink(version, tmp_link)
            os.rename(tmp_link, current_link)

            LOG.info(
                "Deployed application playbooks: %s (current -> %s)",
                target_dir, version)
        except Exception:
            LOG.exception("Failed to deploy application playbooks")
            raise
        finally:
            if os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
            # A failed link swap must not leave the staging pointer behind.
            if os.path.lexists(tmp_link):
                try:
                    os.unlink(tmp_link)
                except OSError:
                    LOG.exception("Failed to remove staging pointer %s",
                                  tmp_link)

    def _undeploy_ansible(self, app):
        """Undeploy application-owned ansible playbooks from /opt/platform/ansible.

        Removes the version-specific playbook directory, and if 'current'
        points at the version being removed, unlinks it and promotes
        'previous' into 'current'. A pointer whose target directory no longer
        exists (dangling) is dropped rather than promoted, so 'current' is
        never left pointing at a missing tree. When 'current' points at a
        different version it is left intact (this version was not the active
        one).

        This is the rollback path for a failed application-update: sysinv's
        recover flow applies the old version through FluxCD directly and does
        not re-run the upload hook, so promoting 'previous' here is what
        leaves the recovered version with playbooks on disk.

        Note this is a single-version undeploy. Removing the application
        entirely is _purge_ansible, wired to pre_delete.
        """
        release = tsc.SW_VERSION
        app_name = app.name
        version = app.version

        app_base = os.path.join(
            app_constants.ANSIBLE_DEPLOY_BASE, release, app_name)
        target_dir = os.path.join(app_base, version)
        current_link = os.path.join(
            app_base, app_constants.ANSIBLE_CURRENT_LINK)
        previous_link = os.path.join(
            app_base, app_constants.ANSIBLE_PREVIOUS_LINK)

        LOG.info("Starting playbook undeployment for %s %s", app_name, version)

        # 1. Remove the version-specific playbook directory.
        if os.path.islink(target_dir):
            # Defensive: target_dir should be a real directory, never a link.
            os.unlink(target_dir)
        elif os.path.isdir(target_dir):
            try:
                shutil.rmtree(target_dir)
                LOG.info("Purged playbook directory: %s", target_dir)
            except Exception:
                LOG.exception("Failed to remove playbook tree at %s", target_dir)
        else:
            LOG.info("Playbook path %s does not exist; skipping deletion",
                     target_dir)

        # 2. Only touch 'current' if it actively points at the version we
        #    just removed. Otherwise this version was not the active one and
        #    the pointer chain must be left alone.
        if not os.path.islink(current_link):
            return

        current_target = os.readlink(current_link)
        if os.path.basename(current_target.rstrip("/")) != version:
            LOG.info("'current' points at a different version (%s); "
                     "leaving tracking pointers intact", current_target)
            return

        # 'current' pointed at the removed version. Unlink it and promote
        # 'previous' into its place, but only if that pointer's target
        # directory still exists so 'current' is never left dangling.
        try:
            os.unlink(current_link)
            self._promote_link(previous_link, current_link, app_base)
            LOG.info("Unlinked 'current' and promoted 'previous' for %s",
                     app_name)
        except Exception:
            LOG.exception("Failed to unlink/promote tracking pointer %s",
                          current_link)

    def _prune_previous_ansible(self, app):
        """Drop the retained playbook generation once an apply has succeeded.

        The rollback generation only has to exist *during* an update: the
        deploy hook rotates 'current' into 'previous' at pre_update, and a
        failed update is recovered from that pointer. Once the apply has
        succeeded there is nothing left to roll back to, so the retained
        version is removed and only the running one stays on disk.

        Safe against destroying a rollback target mid-recovery: sysinv's
        recover flow re-applies the old version through FluxCD directly
        (_make_app_request), bypassing perform_app_apply. That path does
        raise fluxcd-request hooks, but neither of the hooks this runs from
        -- operation/post and manifest/post -- so it never runs as part of a
        recovery. Do not move this call onto a fluxcd-request hook.

        The running version is passed as protected so an unexpected pointer
        state can never delete the tree that 'current' resolves to.
        """
        release = tsc.SW_VERSION
        app_base = os.path.join(
            app_constants.ANSIBLE_DEPLOY_BASE, release, app.name)
        current_link = os.path.join(
            app_base, app_constants.ANSIBLE_CURRENT_LINK)
        previous_link = os.path.join(
            app_base, app_constants.ANSIBLE_PREVIOUS_LINK)

        if not os.path.lexists(previous_link):
            return

        current_version = None
        if os.path.islink(current_link):
            current_version = os.path.basename(
                os.readlink(current_link).rstrip("/"))

        self._prune_link(previous_link, app_base,
                         protected={current_version, app.version})
        LOG.info("Dropped the retained playbook generation for %s; only the "
                 "running version remains", app.name)

    def _purge_ansible(self, app):
        """Remove the whole application playbook tree on application-delete.

        Unlike _undeploy_ansible, which removes one version and preserves the
        rollback pointer, this drops /opt/platform/ansible/<release>/<app-name>/
        entirely: every version directory and every tracking pointer. Once the
        application is deleted there is nothing left to back up or restore for
        it, and the platform delegation check degrades to its inline fallback
        when it finds no playbook at the expected path.

        A re-upload redeploys the tree from the tarball via post_upload, so
        the restore procedure (remove, delete, upload, restore) is unaffected.
        """
        release = tsc.SW_VERSION
        app_base = os.path.join(
            app_constants.ANSIBLE_DEPLOY_BASE, release, app.name)

        if os.path.islink(app_base):
            # Defensive: app_base should be a real directory, never a link.
            os.unlink(app_base)
            return
        if not os.path.isdir(app_base):
            LOG.info("No playbook tree at %s; nothing to purge", app_base)
            return

        try:
            # rmtree does not follow the symlinks it removes, so the version
            # directories are deleted exactly once via their real paths.
            shutil.rmtree(app_base)
            LOG.info("Purged application playbook tree: %s", app_base)
        except Exception:
            LOG.exception("Failed to purge playbook tree at %s", app_base)

    @staticmethod
    def _prune_link(link, app_base, protected=frozenset()):
        """Drop a tracking symlink and the version directory it names.

        Enforces the one-prior-generation retention cap during deploy: the
        pointer is removed along with the version tree it resolves to. A
        version named in 'protected' is never deleted -- defensive cover for
        an unexpected pointer state where 'previous' names the version being
        deployed or the one about to become the rollback target. A dangling
        pointer is dropped without error. No-op if link is absent.
        """
        if not os.path.islink(link):
            return
        target = os.readlink(link)
        target_version = os.path.basename(target.rstrip("/"))
        resolved = target if os.path.isabs(target) \
            else os.path.join(app_base, target)

        if target_version in protected:
            LOG.info("Retaining protected version %s; dropping pointer %s",
                     target_version, link)
        elif os.path.isdir(resolved) and not os.path.islink(resolved):
            try:
                shutil.rmtree(resolved)
                LOG.info("Pruned playbook directory past retention: %s",
                         resolved)
            except Exception:
                LOG.exception("Failed to prune playbook tree at %s", resolved)
        os.unlink(link)

    @staticmethod
    def _rotate_link(src_link, dst_link):
        """Move a tracking symlink src_link -> dst_link during deploy.

        Rotates real symlinks (valid or dangling). Removes a stray non-link
        occupying dst_link first so os.rename cannot fail on a real directory.
        No-op if src_link is absent.
        """
        if not os.path.islink(src_link):
            return
        if os.path.lexists(dst_link):
            if os.path.islink(dst_link):
                os.unlink(dst_link)
            elif os.path.isdir(dst_link):
                shutil.rmtree(dst_link)
            else:
                os.unlink(dst_link)
        os.rename(src_link, dst_link)

    @staticmethod
    def _promote_link(src_link, dst_link, app_base):
        """Promote src_link into dst_link during undeploy, dangling-safe.

        If src_link resolves to an existing directory, move it to dst_link.
        If src_link is dangling (target dir gone), drop it instead of
        promoting a broken pointer. No-op if src_link is absent.
        """
        if not os.path.islink(src_link):
            return
        target = os.readlink(src_link)
        resolved = target if os.path.isabs(target) \
            else os.path.join(app_base, target)
        if os.path.isdir(resolved):
            os.rename(src_link, dst_link)
        else:
            os.unlink(src_link)
            LOG.info("Dropped dangling tracking pointer %s (-> %s)",
                     src_link, target)
