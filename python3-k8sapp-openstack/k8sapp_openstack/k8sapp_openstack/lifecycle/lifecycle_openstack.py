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
from sysinv.common import kubernetes
from sysinv.helm import common
from sysinv.helm import lifecycle_base as base
from sysinv.helm import lifecycle_utils as lifecycle_utils
from sysinv.helm.lifecycle_constants import LifecycleConstants

from k8sapp_openstack import utils as app_utils
from k8sapp_openstack.common import constants as app_constants
from k8sapp_openstack.helpers import ldap
from k8sapp_openstack.utils import is_ceph_backend_available

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

        # Resource
        elif hook_info.lifecycle_type == LifecycleConstants.APP_LIFECYCLE_TYPE_RESOURCE:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                return self._create_app_specific_resources_pre_apply(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_REMOVE_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_POST:
                return self._delete_app_specific_resources_post_remove(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_RECOVER_OP:
                return self._recover_actions(app_op, app)

        # Rbd
        elif hook_info.lifecycle_type == LifecycleConstants.APP_LIFECYCLE_TYPE_RBD:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                return lifecycle_utils.create_rbd_provisioner_secrets(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_REMOVE_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_POST:
                return lifecycle_utils.delete_rbd_provisioner_secrets(app_op, app, hook_info)

        # Semantic checks
        elif hook_info.lifecycle_type == LifecycleConstants.APP_LIFECYCLE_TYPE_SEMANTIC_CHECK:
            if hook_info.mode == LifecycleConstants.APP_LIFECYCLE_MODE_AUTO:
                if hook_info.operation == constants.APP_EVALUATE_REAPPLY_OP:
                    return self._semantic_check_evaluate_app_reapply(app_op, app, hook_info)
            elif hook_info.mode in [LifecycleConstants.APP_LIFECYCLE_MODE_MANUAL,
                                    LifecycleConstants.APP_LIFECYCLE_MODE_AUTO] and \
                    hook_info.operation == constants.APP_APPLY_OP and \
                        hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                return self._pre_apply_check(conductor_obj, app, hook_info)
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
                return self._post_update_image_actions(app)

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
        available, message = is_ceph_backend_available(ceph_type=constants.SB_TYPE_CEPH_ROOK)

        if available:
            LOG.info("Read ceph-etc config map from rook-ceph namespace")
            src_config_map_name = self.APP_OPENSTACK_RESOURCE_CONFIG_MAP
            src_config_map_ns = app_constants.HELM_NS_ROOK_CEPH
        elif not available and message == app_constants.CEPH_BACKEND_NOT_CONFIGURED:
            raise exception.InvalidStorageBackend(backend=constants.SB_TYPE_CEPH_ROOK)
        elif not available and message == app_constants.DB_API_NOT_AVAILABLE:
            raise ConnectionError("Database API is not available")
        else:
            LOG.info("Read rbd-storage-init config map from kube-system namespace")
            src_config_map_name = self.APP_KUBESYSTEM_RESOURCE_CONFIG_MAP
            src_config_map_ns = common.HELM_NS_RBD_PROVISIONER

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

        # Check storage backends
        self._semantic_check_storage_backend_available()

        # Check vswitch configuration
        self._semantic_check_vswitch_config(conductor_obj.dbapi)

        # Check data network configuration
        self._semantic_check_datanetwork_config(conductor_obj.dbapi)

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

    def _semantic_check_storage_backend_available(self):
        """Checks if at least one of the supported storage backends
        is available and ready for openstack deployment

        Raises:
            LifecycleSemanticCheckException: no storage backend available for
                                             openstack deployment.
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
        status = f"ceph_available={ceph_available}, " \
                 f"rook_ceph_available={rook_ceph_available}"
        if rook_ceph_available:
            rook_api_available = app_utils.is_rook_ceph_api_available()
            fsid_available = app_utils.get_ceph_fsid() is not None
            backend_available = rook_api_available and fsid_available
            status += f", fsid_available={fsid_available}, " \
                      f"rook_api_available={rook_api_available}"
        elif ceph_available:
            fsid_available = app_utils.get_ceph_fsid() is not None
            backend_available = fsid_available
            status += f", fsid_available={fsid_available}"

        if not backend_available:
            err_msg = "No storage backends available and ready for openstack " \
                      f"deployment. status: {status}"
            LOG.error(f"{err_msg}")
            raise exception.LifecycleSemanticCheckException(err_msg)

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

    def _recover_actions(self, app_op, app):
        """Perform all recover actions.

        Args:
            app_op (AppOperator): System Inventory AppOperator object
            app (AppOperator.Application): Application we are recovering from
        """
        self._recover_backup_snapshot(app)
        self._recover_app_resources_failed_update(app_op, app)

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
        app_utils.delete_kubernetes_resource(
            resource_type='helmrelease',
            resource_name='mariadb'
        )

        # Force FLuxCD reconciliation for all the application helmreleases.
        # By default the AppFwk only force reconciliation for app updates,
        # but not for app recovery
        app_utils.force_app_reconciliation(app_op, app)

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
