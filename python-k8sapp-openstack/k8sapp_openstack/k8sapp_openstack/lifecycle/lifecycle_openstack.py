#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

""" System inventory App lifecycle operator."""

from eventlet import greenthread
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

        # Manifest
        elif hook_info.lifecycle_type == constants.APP_LIFECYCLE_TYPE_MANIFEST and \
                hook_info.operation == constants.APP_APPLY_OP and \
                hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_PRE:
            return self.pre_manifest_apply(app, app_op, hook_info)

        # Resource
        elif hook_info.lifecycle_type == constants.APP_LIFECYCLE_TYPE_RESOURCE:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_PRE:
                return self._create_app_specific_resources_pre_apply(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_REMOVE_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_POST:
                return self._delete_app_specific_resources_post_remove(app_op, app, hook_info)

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

    def pre_manifest_apply(self, app, app_op, hook_info):
        """Pre manifest apply actions

        :param app_op: AppOperator object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """
        # For stx-openstack app, if the apply operation was terminated
        # (e.g. user aborted, controller swacted, sysinv conductor
        # restarted) while compute-kit charts group was being deployed,
        # Tiller may still be processing these charts. Issuing another
        # manifest apply request while there are pending install of libvirt,
        # neutron and/or nova charts will result in reapply failure.
        #
        # Wait up to 10 minutes for Tiller to finish its transaction
        # from previous apply before making a new manifest apply request.
        LOG.info("Wait if there are openstack charts in pending install...")
        for i in range(self.CHARTS_PENDING_INSTALL_ITERATIONS):
            result = helm_utils.get_openstack_pending_install_charts()
            if not result:
                break

            if app_op.is_app_aborted(app.name):
                raise exception.KubeAppAbort()
            greenthread.sleep(10)
        if result:
            app_op._abort_operation(app, constants.APP_APPLY_OP)
            raise exception.KubeAppApplyFailure(
                name=app.name, version=app.version,
                reason="Timed out while waiting for some charts that "
                       "are still in pending install in previous application "
                       "apply to clear. Please try again later.")

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

        # Evaluate https reapply semantic check
        if self._semantic_check_openstack_https_not_ready():
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

    def _semantic_check_openstack_https_not_ready(self):
        """Return True if OpenStack HTTPS is not ready for reapply.

        :return: True when https flag is True and certificates are
        not installed. Otherwise, False.
        """
        return app_utils.https_enabled() and not app_utils.is_openstack_https_certificates_ready()
