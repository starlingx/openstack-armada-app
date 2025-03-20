#
# Copyright (c) 2023-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

""" System inventory App lifecycle operator."""

from pathlib import Path

from oslo_log import log as logging
from sysinv.api.controllers.v1 import utils
from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm import common
from sysinv.helm import lifecycle_base as base
from sysinv.helm import lifecycle_utils as lifecycle_utils
from sysinv.helm import utils as helm_utils
from sysinv.helm.lifecycle_constants import LifecycleConstants

from k8sapp_openstack import utils as app_utils
from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helpers import ldap

LOG = logging.getLogger(__name__)


class OpenstackAppLifecycleOperator(base.AppLifecycleOperator):
    CHARTS_PENDING_INSTALL_ITERATIONS = 60
    APP_KUBESYSTEM_RESOURCE_CONFIG_MAP = 'ceph-etc-pools-audit'
    APP_OPENSTACK_RESOURCE_CONFIG_MAP = 'ceph-etc'
    WAS_APPLIED = 'was_applied'

    def app_lifecycle_actions(self, context, conductor_obj, app_op, app, hook_info):
        """ Perform lifecycle actions for an operation

        :param context: request context
        :param conductor_obj: conductor object
        :param app_op: AppOperator object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """
        # Operation
        if hook_info.lifecycle_type == constants.APP_LIFECYCLE_TYPE_OPERATION:
            if hook_info.operation == constants.APP_APPLY_OP:
                if hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_PRE:
                    return self.pre_apply(context, conductor_obj, app, hook_info)
                elif hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_POST:
                    return self.post_apply(context, conductor_obj, app, hook_info)
            elif hook_info.operation == constants.APP_REMOVE_OP:
                if hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_PRE:
                    return self.pre_remove(context, conductor_obj, hook_info)
                elif hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_POST:
                    return self.post_remove(context, conductor_obj, hook_info)

        # Resource
        elif hook_info.lifecycle_type == constants.APP_LIFECYCLE_TYPE_RESOURCE:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_PRE:
                return self._create_app_specific_resources_pre_apply(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_REMOVE_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_POST:
                return self._delete_app_specific_resources_post_remove(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_RECOVER_OP:
                return self._recover_actions(app)

        # Rbd
        elif hook_info.lifecycle_type == constants.APP_LIFECYCLE_TYPE_RBD:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_PRE:
                return lifecycle_utils.create_rbd_provisioner_secrets(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_REMOVE_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_POST:
                return lifecycle_utils.delete_rbd_provisioner_secrets(app_op, app, hook_info)

        # Semantic checks
        elif hook_info.lifecycle_type == constants.APP_LIFECYCLE_TYPE_SEMANTIC_CHECK:
            if hook_info.mode == constants.APP_LIFECYCLE_MODE_AUTO:
                if hook_info.operation == constants.APP_EVALUATE_REAPPLY_OP:
                    return self._semantic_check_evaluate_app_reapply(app_op, app, hook_info)
                elif hook_info.operation == constants.APP_UPDATE_OP:
                    raise exception.LifecycleSemanticCheckOperationNotSupported(
                        mode=constants.APP_LIFECYCLE_MODE_AUTO, op=constants.APP_UPDATE_OP, name=app.name)
            elif hook_info.mode == constants.APP_LIFECYCLE_MODE_MANUAL and \
                    hook_info.operation == constants.APP_APPLY_OP and \
                        hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_PRE:
                return self._pre_manual_apply_check(conductor_obj, app, hook_info)

        # Manifest
        elif hook_info.lifecycle_type == constants.APP_LIFECYCLE_TYPE_MANIFEST:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_PRE:
                return self._pre_update_actions(app)

        # Default behavior
        super(OpenstackAppLifecycleOperator, self).app_lifecycle_actions(context, conductor_obj, app_op, app,
                                                                         hook_info)

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

        # Delete PVC snapshots if existent
        nc = app_utils.get_number_of_controllers()

        for i in range(0, nc):
            pvc_name = f"mysql-data-mariadb-server-{i}"
            snapshot_name = f"snapshot-of-{pvc_name}"
            LOG.info(f"Trying to delete snapshot '{snapshot_name}'")
            app_utils.delete_snapshot(snapshot_name)

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

    def _delete_app_specific_resources_post_remove(self, app_op, app, hook_info):
        """Delete application specific resources.

        :param app_op: AppOperator object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """
        lifecycle_utils.delete_local_registry_secrets(app_op, app, hook_info)
        lifecycle_utils.delete_persistent_volume_claim(app_op, common.HELM_NS_OPENSTACK)
        lifecycle_utils.delete_configmap(app_op, common.HELM_NS_OPENSTACK, self.APP_OPENSTACK_RESOURCE_CONFIG_MAP)
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
            # Copy the latest configmap with the ceph monitor information
            # required by the application into the application namespace
            if app_op._kube.kube_get_config_map(
                    self.APP_OPENSTACK_RESOURCE_CONFIG_MAP,
                    common.HELM_NS_OPENSTACK):
                # Already have one. Delete it, in case it changed
                app_op._kube.kube_delete_config_map(
                    self.APP_OPENSTACK_RESOURCE_CONFIG_MAP,
                    common.HELM_NS_OPENSTACK)

            # Read ceph-etc-pools-audit config map and rename it to ceph-etc
            config_map_body = app_op._kube.kube_read_config_map(
                self.APP_KUBESYSTEM_RESOURCE_CONFIG_MAP,
                common.HELM_NS_RBD_PROVISIONER)

            config_map_body.metadata.resource_version = None
            config_map_body.metadata.namespace = common.HELM_NS_OPENSTACK
            config_map_body.metadata.name = self.APP_OPENSTACK_RESOURCE_CONFIG_MAP

            # Create configmap with correct name
            app_op._kube.kube_create_config_map(
                common.HELM_NS_OPENSTACK,
                config_map_body)

            # Perform pre apply LDAP-related actions.
            self._pre_apply_ldap_actions(app)
        except Exception as e:
            LOG.error(e)
            raise

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

        # Evaluate https reapply semantic check
        if not self._semantic_check_openstack_https_ready():
            raise exception.LifecycleSemanticCheckException(
                "Https semantic check failed."
            )

    def _pre_manual_apply_check(self, conductor_obj, app, hook_info):
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

    def _semantic_check_openstack_https_ready(self):
        """Return True if OpenStack HTTPS is ready for reapply.

        :return: True certificate file is present. Otherwise, False.
        """
        return app_utils.is_openstack_https_ready()

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
        self._pre_update_backup_actions(app)
        self._pre_update_cleanup_actions()

    def _pre_update_cleanup_actions(self):
        """Perform pre update cleanup actions."""

        # TODO: Remove in the future. This code is only necessary when
        # updating from stx-10 to stx-11 STX-O release.
        release = 'ingress'
        patch = {"spec": {"suspend": True}}

        # Update helmrelease to not reconcile during update
        app_utils.update_helmrelease(release, patch)

        # Uninstall helm release.
        status = helm_utils.delete_helm_release(
            release='osh-openstack-ingress', namespace=app_constants.HELM_NS_OPENSTACK)
        LOG.info(status)

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

    def _recover_actions(self, app):
        """Perform all recover actions.

        :param app: AppOperator.Application object

        """
        self._recover_backup_snapshot(app)
        self._recover_app_resources_failed_update()

    def _recover_app_resources_failed_update(self):
        """ Perform resource recover after failed update"""

        # TODO: Remove in the future. This code is only necessary when
        # updating from stx-10 to stx-11 STX-O release.
        release = 'ingress'
        patch = {"spec": {"suspend": False}}

        # Update helmrelease to revert changes
        app_utils.update_helmrelease(release, patch)

        # The new Ingress must be disabled and deleted before starting recovery
        release_failed = 'ingress-nginx-openstack'
        patch_failed = {"spec": {"suspend": True}}
        app_utils.update_helmrelease(release_failed, patch_failed)

        # Uninstall helm release.
        status = helm_utils.delete_helm_release(
            release=release_failed, namespace=app_constants.HELM_NS_OPENSTACK)
        LOG.info(status)

        # Downgrading is not officially supported for MariaDB:
        # https://mariadb.com/kb/en/downgrading-between-major-versions-of-mariadb/
        # Because of that, we need to delete the Helmrelease for the new MariaDB
        # before deploying the old one.
        app_utils.delete_kubernetes_resource(
            resource_type='helmrelease',
            resource_name='mariadb'
        )

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
