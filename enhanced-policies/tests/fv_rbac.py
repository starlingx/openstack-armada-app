#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

import os

from cinderclient import client as CinderClient
from glanceclient import Client as GlanceClient
from keystoneauth1 import loading
from keystoneauth1 import session
from novaclient import client as NovaClient
import openstack
import os_client_config
import pytest

TEST_CLOUD = os.getenv("OS_CLOUD")

debug = False  # For general issues
debug1 = True  # For teardown issues
debug2 = False  # For temporary issues


class OpenStackTestingSetup:

    def __init__(self):
        self.os_sdk_admin_conn = openstack.connect(cloud=TEST_CLOUD)

        self.user11 = {
            "name": "user11",
            "password": "User11@Project1",
            "project": "project1"
        }
        self.user12 = {
            "name": "user12",
            "password": "User12@Project1",
            "project": "project1"
        }
        self.user13 = {
            "name": "user13",
            "password": "User13@Project1",
            "project": "project1"
        }
        self.user02 = {
            "name": "user02",
            "password": "user02@Project2",
            "project": "project2"
        }
        self.user21 = {
            "name": "user21",
            "password": "User21@Project2",
            "project": "project2"
        }
        self.user22 = {
            "name": "user22",
            "password": "User22@Project2",
            "project": "project2"
        }
        self.user23 = {
            "name": "user23",
            "password": "User23@Project2",
            "project": "project2"
        }

        self.users = (
            self.user11,
            self.user12,
            self.user13,
            self.user02,
            self.user21,
            self.user22,
            self.user23
        )

    def _get_project(self, name):
        return self.os_sdk_admin_conn.get_project(name)

    def _create_project(self, name, description):
        project = self._get_project(name)
        if project is None:
            return self.os_sdk_admin_conn.create_project(
                name,
                domain_id="default",
                description=description
            )
        return project

    def _delete_project(self, name):
        self.os_sdk_admin_conn.delete_project(name)

    def _create_role(self, name):
        role = self.os_sdk_admin_conn.get_role(name)
        if role is None:
            return self.os_sdk_admin_conn.create_role(name)
        return role

    def _delete_role(self, name):
        self.os_sdk_admin_conn.delete_role(name)

    def _grant_role(self, name, user_name, project_name):
        self.os_sdk_admin_conn.grant_role(
            name,
            user=user_name,
            project=project_name
        )

    def _revoke_role(self, name, user_name, project_name):
        self.os_sdk_admin_conn.revoke_role(
            name,
            user=user_name,
            project=project_name
        )

    def _create_user(self, user):
        user_obj = self.os_sdk_admin_conn.identity.find_user(user.get("name"))
        if user_obj is None:
            return self.os_sdk_admin_conn.identity.create_user(
                name=user.get("name"),
                password=user.get("password"),
                default_project=user.get("project"))
        return user_obj

    def _delete_user(self, user):
        self.os_sdk_admin_conn.delete_user(user.get("name"))

    def _create_admin_image(self):
        # wget http://download.cirros-cloud.net/0.3.4/cirros-0.3.4-x86_64-disk.img
        image = self.os_sdk_admin_conn.image.find_image("cirros")
        if not image:
            return self.os_sdk_admin_conn.create_image(
                "cirros",
                filename="cirros-0.3.4-x86_64-disk.img",
                disk_format="qcow2",
                container_format="bare",
                wait=True,
                visibility="public"
            )
        return image

    def _delete_admin_image(self, image):
        if image:
            self.os_sdk_admin_conn.delete_image(image.id)


class OpenStackNetworkingSetup(OpenStackTestingSetup):

  def __init__(self):
        super(OpenStackNetworkingSetup, self).__init__()

    def _create_network_segment_range(self, name, project_name=None, **kwargs):
        sr = self.os_sdk_admin_conn.network.find_network_segment_range(name)
        if sr is None:
            project_id = None
            if project_name:
                project_id = self.os_sdk_admin_conn.get_project(
                    project_name).id
            if project_id is None:
                return self.os_sdk_admin_conn.network. \
                    create_network_segment_range(name=name, **kwargs)
            else:
                return self.os_sdk_admin_conn.network. \
                    create_network_segment_range(
                        name=name,
                        project_id=project_id,
                        **kwargs
                    )
        return sr

    def _delete_network_segment_range(self, name_or_id):
        return self.os_sdk_admin_conn.network.delete_network(name_or_id)


class OpenStackRouterInterface:
    def __init__(self, router_name_or_id, subnet_name_or_id):
        self.router_name_or_id = router_name_or_id
        self.subnet_name_or_id = subnet_name_or_id


class OpenStackBasicTesting():
    os_sdk_conn = None
    os_sdk_admin_conn = None

    # -------------------------------------------------------------------------
    # Tear down
    # -------------------------------------------------------------------------

    instances_clearing = list()
    images_clearing = list()
    snapshots_clearing = list()
    volumes_clearing = list()
    volume_bkps_clearing = list()
    security_groups_clearing = list()
    floating_ips_clearing = list()
    interfaces_clearing = list()
    routers_clearing = list()
    trunks_clearing = list()
    ports_clearing = list()
    subnets_clearing = list()
    networks_clearing = list()
    subnet_pools_clearing = list()
    address_scopes_clearing = list()

    @pytest.fixture(scope='function')
    def tc_teardown(self, request):

        def teardown():

            if debug1:
                print("\nTC Teardown")

            self.os_sdk_conn = self.os_sdk_admin_conn
            for instance_id in self.instances_clearing:
                self._delete_server(instance_id, autoclear=False)
            for image_id in self.images_clearing:
                self._delete_image(image_id, autoclear=False)
            for snap_id in self.snapshots_clearing:
                self._delete_snapshot(snap_id, autoclear=False)
            for vol_id in self.volumes_clearing:
                self._delete_volume(vol_id, autoclear=False)
            for bkp_id in self.volume_bkps_clearing:
                self._delete_volume_backup(bkp_id, autoclear=False)
            for sg_id in self.security_groups_clearing:
                self._delete_security_group(sg_id, autoclear=False)
            for fip_id in self.floating_ips_clearing:
                self._delete_floatingip(fip_id, autoclear=False)
            for ri in self.interfaces_clearing:
                self._delete_interface_from_router(ri, autoclear=False)
            for router_id in self.routers_clearing:
                self._delete_router(router_id, autoclear=False)
            for trunk_id in self.trunks_clearing:
                self._delete_trunk(trunk_id, autoclear=False)
            for port_id in self.ports_clearing:
                self._delete_port(port_id, autoclear=False)
            for subnet_id in self.subnets_clearing:
                self._delete_subnet(subnet_id, autoclear=False)
            for network_id in self.networks_clearing:
                self._delete_network(network_id, autoclear=False)
            for subnet_pool_id in self.subnet_pools_clearing:
                self._delete_subnetpool(subnet_pool_id, autoclear=False)
            for address_scope_id in self.address_scopes_clearing:
                self._delete_addrscope(address_scope_id, autoclear=False)

            self.instances_clearing.clear()
            self.images_clearing.clear()
            self.snapshots_clearing.clear()
            self.volumes_clearing.clear()
            self.volume_bkps_clearing.clear()
            self.security_groups_clearing.clear()
            self.floating_ips_clearing.clear()
            self.interfaces_clearing.clear()
            self.routers_clearing.clear()
            self.trunks_clearing.clear()
            self.ports_clearing.clear()
            self.subnets_clearing.clear()
            self.networks_clearing.clear()
            self.subnet_pools_clearing.clear()
            self.address_scopes_clearing.clear()

        request.addfinalizer(teardown)

        return

    @pytest.fixture(scope='class')
    def create_external_network(self, request):
        self.set_connections_for_user(self.user02)

        args = {'router:external': True}
        network = self._create_network(
            "extnet21",
            shared=True,
            autoclear=False,
            **args)
        assert network is not None
        assert "extnet21" in [n.name for n in self._list_networks()]

        subnet = self._create_subnet(
            "extsubnet21",
            "extnet21",
            cidr="192.168.195.0/24",
            gateway_ip="192.168.195.1", autoclear=False
        )
        assert subnet is not None
        subnet = self._get_subnet("extsubnet21")

        yield network, subnet

        self.set_connections_for_user(self.user02)
        self._delete_subnet("extsubnet21", autoclear=False)
        self._delete_network("extnet21", autoclear=False)

    @pytest.fixture(scope='class')
    def create_router_vr11(self, request, create_external_network):
        extnet, extsubnet = create_external_network

        self.set_connections_for_user(self.user11)
        vr11 = self._create_router("vr11", extnet.name, autoclear=False)
        vr11 = self._get_router("vr11")
        assert vr11 is not None

        yield vr11

        self.set_connections_for_user(self.user11)
        self._delete_router("vr11", autoclear=False)

    @pytest.fixture(scope='class')
    def create_router_vr21(self, request, create_external_network):
        extnet, extsubnet = create_external_network

        self.set_connections_for_user(self.user02)
        vr21 = self._create_router("vr21", extnet.name, autoclear=False)
        vr21 = self._get_router("vr21")
        assert vr21 is not None

        yield vr21

        self.set_connections_for_user(self.user02)
        self._delete_router("vr21", autoclear=False)

    def _get_conn_for(self, user):
        conn = self.os_sdk_admin_conn
        user_obj = conn.identity.find_user(user.get("name"))
        project = conn.get_project(user.get("project"))

        return openstack.connection.Connection(
            auth=dict(
                auth_url=conn.auth.get("auth_url"),
                username=user.get("name"),
                password=user.get("password"),
                project_id=project.id,
                user_domain_id=user_obj.domain_id
            )
        )

    # -------------------------------------------------------------------------
    # API Session Connection
    # -------------------------------------------------------------------------
    # OpenStack Python API
    def _get_session_for_user(self, user):
        creds = os_client_config.OpenStackConfig() \
            .get_one_cloud(cloud=TEST_CLOUD).get_auth_args()
        sloader = loading.get_plugin_loader("password")
        auth = sloader.load_from_options(
            auth_url=self.os_sdk_admin_conn.auth.get("auth_url"),
            username=user.get("name"),
            password=user.get("password"),
            project_name=user.get("project"),
            project_domain_name=creds['project_domain_name'],
            user_domain_name=creds['user_domain_name'],
        )
        return session.Session(auth=auth)

    # CinderClient Python API
    def _get_cclient_for(self, user):
        self.sess = self._get_session_for_user(user)
        return CinderClient.Client('3', session=self.sess, http_log_debug=True)

    # GlanceClient Python API
    def _get_gclient_for(self, user):
        self.sess = self._get_session_for_user(user)
        return GlanceClient('2', session=self.sess)

    # NovaClient Python API
    def _get_nclient_for(self, user):
        self.sess = self._get_session_for_user(user)
        return NovaClient.Client('2', session=self.sess)

    def _get_os_conn_for(self, user):
        self.sess = self._get_session_for_user(user)
        return openstack.connection.Connection(session=self.sess)

    def set_connections_for_user(self, user):
        self.os_sdk_conn = self._get_os_conn_for(user)
        self.nc = self._get_nclient_for(user)
        self.cc = self._get_cclient_for(user)
        self.gc = self._get_gclient_for(user)

    # -------------------------------------------------------------------------
    # Volume methods - Cinder
    # -------------------------------------------------------------------------

    def _create_volume(self, volume_name, autoclear=True):
        vol = self.os_sdk_conn.block_storage.create_volume(
            name=volume_name,
            size=1,
            image="cirros",
            wait=True
        )
        if debug1:
            print("created volume: " + vol.name + " id: " + vol.id)
        if autoclear:
            self.volumes_clearing.append(vol.id)
        self.os_sdk_conn.block_storage.wait_for_status(vol, status="available")
        return vol

    def _create_image_from_volume(self, volume_name, image_name,
                                  autoclear=True):
        volume = self._get_volume(volume_name)
        self.cc.volumes.upload_to_image(
            volume,
            False,
            image_name,
            container_format="bare",
            disk_format="raw"
        )
        image = self._get_image(image_name)
        if debug1:
            print("created image: " + image.name + " id: " + image.id)
        if autoclear:
            self.images_clearing.append(image.id)
        return image

    def _delete_volume(self, volume_name, autoclear=True, **kwargs):
        vol = self.os_sdk_conn.block_storage.find_volume(
            volume_name,
            ignore_missing=False
        )
        if vol:
            self.os_sdk_conn.block_storage.delete_volume(vol.id)
            if debug1:
                print("deleted volume: " + vol.name + " id: " + vol.id)
            if autoclear:
                self.volumes_clearing.remove(vol.id)

    def _list_volumes(self):
        volumes = self.cc.volumes.list()
        return volumes

    def _get_volume(self, volume_name_or_id):
        volume = self._find_volume(volume_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.block_storage.get_volume(volume)

    def _find_volume(self, volume_name_or_id, ignore_missing=True):
        return self.os_sdk_conn.block_storage.find_volume(
            volume_name_or_id,
            ignore_missing=ignore_missing
        )

    def _update_volume(self, volume_name, **kwargs):
        vol = self.os_sdk_conn.update_volume(volume_name, **kwargs)
        return vol

    def _get_volume_metadata(self, volume_name):
        vol = self.cc.volumes.get(self._get_volume(volume_name).id)
        # NOTE(tbrito): cinderclient doesn't call
        # /v3/{project_id}/volumes/{volume_id}/metadata explicitly
        return vol.metadata

    def _update_volume_metadata(self, volume_name, metadata):
        vol = self.cc.volumes.get(self._get_volume(volume_name).id)
        # TODO(tbrito): Refactor after
        #  https://review.opendev.org/c/openstack/openstacksdk/+/777801 merges
        return self.cc.volumes.set_metadata(vol, metadata)

    def _delete_volume_metadata(self, volume_name, metadata_keys: list):
        vol = self.cc.volumes.get(self._get_volume(volume_name).id)
        return self.cc.volumes.delete_metadata(vol, metadata_keys)

    def _set_volume_readonly_flag(self, volume_name, readonly=True):
        vol = self.cc.volumes.get(self._get_volume(volume_name).id)
        return self.cc.volumes.update_readonly_flag(vol, readonly)

    def _retype_volume(self, volume_name, volume_type,
                       migration_policy="never"):
        vol = self.cc.volumes.get(self._get_volume(volume_name).id)
        return self.cc.volumes.retype(vol, volume_type, migration_policy)

    def _extend_volume(self, volume_name, size):
        vol = self._get_volume(volume_name)
        # NOTE(tbrito): Can't use SDK method to extend because it doesn't
        # raise exceptions, only get message
        # self.os_sdk_conn.block_storage.extend_volume(vol, size=size)
        self.cc.volumes.extend(vol, size)
        vol = self.os_sdk_conn.block_storage.get_volume(vol)
        self.os_sdk_conn.block_storage.wait_for_status(vol, status="available")
        return self._get_volume(volume_name)

    def _add_volume_to_server(self, instance_name_or_id, volume_name_or_id):
        instance = self._get_server(instance_name_or_id)
        volume = self._get_volume(volume_name_or_id)
        self.os_sdk_conn.compute.create_volume_attachment(instance,
                                                          volume_id=volume.id)
        self.os_sdk_conn.block_storage.wait_for_status(volume, status="in-use")

    def _remove_volume_from_server(self, instance_name_or_id,
                                   volume_name_or_id):
        instance = self._get_server(instance_name_or_id)
        volume = self._get_volume(volume_name_or_id)
        for attached_volume in instance.attached_volumes:
            if attached_volume.get("id") == volume.id:
                self.os_sdk_conn.compute.delete_volume_attachment(
                    attached_volume.get("id"),
                    instance
                )
                self.os_sdk_conn.block_store.wait_for_status(
                    volume,
                    status='available',
                    failures=['error'],
                    wait=6 * 60
                )

    # -------------------------------------------------------------------------
    # Volume transfer methods
    # -------------------------------------------------------------------------
    def _start_volume_transfer(self, volume_name, transfer_name):
        volume = self._get_volume(volume_name)
        return self.cc.transfers.create(volume.id, transfer_name)

    def _get_volume_transfer(self, transfer_name):
        return self.cc.transfers.get(
            self.cc.transfers.find(name=transfer_name).id
        )

    def _accept_volume_transfer(self, transfer_id, auth_key):
        return self.cc.transfers.accept(transfer_id, auth_key)

    def _list_volume_transfers(self):
        return self.cc.transfers.list()

    def _delete_volume_transfer(self, transfer_name):
        return self.cc.transfers.delete(
            self.cc.transfers.find(name=transfer_name).id
        )

    # -------------------------------------------------------------------------
    # Volume backup methods
    # -------------------------------------------------------------------------

    def _create_volume_backup(self, volume_name, backup_name, autoclear=True):
        vol = self._get_volume(volume_name)
        bkp = self.os_sdk_conn.block_storage.create_backup(
            volume_id=vol.id,
            name=backup_name
        )
        if debug1:
            print("created volume backup: " + bkp.name + " id: " + bkp.id)
        if autoclear:
            self.volume_bkps_clearing.append(bkp.id)
        self.os_sdk_conn.block_storage.wait_for_status(bkp, status="available")
        return bkp

    def _delete_volume_backup(self, backup_name, autoclear=True):
        bkp = self._get_volume_backup(backup_name)
        if bkp:
            self.os_sdk_conn.block_storage.delete_backup(bkp.id)
            if debug1:
                print("deleted volume backup: " + bkp.name + " id: " + bkp.id)
            if autoclear:
                self.volume_bkps_clearing.remove(bkp.id)

    def _restore_volume_backup(self, backup_name, new_volume_name,
                               autoclear=True):
        bkp = self._get_volume_backup(backup_name)
        self.os_sdk_conn.block_storage.restore_backup(bkp,
                                                      name=new_volume_name)
        bkp = self._get_volume_backup(backup_name)
        self.os_sdk_conn.block_storage.wait_for_status(bkp, status="available")
        vol = self._get_volume(new_volume_name)
        if autoclear:
            self.volumes_clearing.append(vol.id)
        return vol

    def _get_volume_backup(self, backup_name):
        return self.os_sdk_conn.block_storage.get_backup(
            self.os_sdk_conn.block_storage.find_backup(backup_name))

    # -------------------------------------------------------------------------
    # Snapshot methods
    # -------------------------------------------------------------------------
    def _create_snapshot(self, volume_name, name, autoclear=True, **kwargs):
        volume = self._get_volume(volume_name)
        snapshot = self.os_sdk_conn.block_storage.create_snapshot(
            volume_id=volume.id,
            name=name,
            **kwargs
        )
        if debug1:
            print("created snapshot: " + snapshot.name + " id: " + snapshot.id)
        if autoclear:
            self.snapshots_clearing.append(snapshot.id)
        self.os_sdk_conn.block_storage.wait_for_status(
            snapshot,
            status="available"
        )
        return snapshot

    def _delete_snapshot(self, snapshot_name, autoclear=True):
        snapshot = self.os_sdk_conn.block_storage.find_snapshot(snapshot_name)
        if snapshot:
            self.os_sdk_conn.block_storage.delete_snapshot(snapshot.id)
            if debug1:
                print("deleted snapshot: " + snapshot.name + " id: " +
                      snapshot.id)
            if autoclear:
                self.snapshots_clearing.remove(snapshot.id)

    def _list_snapshots(self):
        return self.os_sdk_conn.block_storage.snapshots()

    def _get_snapshot(self, snapshot_name):
        return self.os_sdk_conn.block_storage.get_snapshot(
            self.os_sdk_conn.block_storage.find_snapshot(
                snapshot_name,
                ignore_missing=False
            )
        )

    def _update_snapshot(self, snapshot_name, **kwargs):
        snapshot = self.cc.volume_snapshots.get(
            self._get_snapshot(snapshot_name).id
        )
        self.cc.volume_snapshots.update(snapshot, **kwargs)

    def _get_snapshot_metadata(self, snapshot_name):
        return self.os_sdk_conn.block_storage.get_snapshot(
            self.os_sdk_conn.block_storage.find_snapshot(
                snapshot_name,
                ignore_missing=False
            )
        ).metadata

    def _update_snapshot_metadata(self, snapshot_name, metadata):
        snapshot = self.cc.volume_snapshots.get(
            self._get_snapshot(snapshot_name).id
        )
        self.cc.volume_snapshots.set_metadata(snapshot, metadata)

    def _delete_snapshot_metadata(self, snapshot_name, *metadata_keys):
        snapshot = self.cc.volume_snapshots.get(
            self._get_snapshot(snapshot_name).id
        )
        self.cc.volume_snapshots.delete_metadata(snapshot, metadata_keys)

    # -------------------------------------------------------------------------
    # Image methods - Glance
    # -------------------------------------------------------------------------

    def _create_image(self, image_name, filename=None, admin=False,
                      disk_format="qcow2", container_format="bare",
                      visibility="private", wait=True, timeout=3 * 60,
                      autoclear=True):
        """
        # create_image(name, filename=None, container=None, md5=None, sha256=None,
        #              disk_format=None, container_format=None,
        #              disable_vendor_agent=True, allow_duplicates=False,
        #              meta=None, wait=False, timeout=3600, data=None,
        #              validate_checksum=False, use_import=False, stores=None,
        #              all_stores=None, all_stores_must_succeed=None, **kwargs)
        # Upload an image.
        # Parameters
        # name (str) – Name of the image to create. If it is a pathname of an
        # image, the name will be constructed from the extensionless basename of
        # the path.
        # filename (str) – The path to the file to upload, if needed. (optional,
        # defaults to None)
        # data – Image data (string or file-like object). It is mutually exclusive
        # with filename
        # container (str) – Name of the container in swift where images should be
        # uploaded for import if the cloud requires such a thing. (optional,
        # defaults to ‘images’)
        # md5 (str) – md5 sum of the image file. If not given, an md5 will be
        # calculated.
        # sha256 (str) – sha256 sum of the image file. If not given, an md5 will
        # be calculated.
        # disk_format (str) – The disk format the image is in. (optional, defaults
        # to the os-client-config config value for this cloud)
        # container_format (str) – The container format the image is in. (optional,
        # defaults to the os-client-config config value for this cloud)
        # disable_vendor_agent (bool) – Whether or not to append metadata flags to
        # the image to inform the cloud in question to not expect a vendor agent to
        # be runing. (optional, defaults to True)
        # allow_duplicates – If true, skips checks that enforce unique image name.
        # (optional, defaults to False)
        # meta – A dict of key/value pairs to use for metadata that bypasses
        # automatic type conversion.
        # wait (bool) – If true, waits for image to be created. Defaults to true -
        # however, be aware that one of the upload methods is always synchronous.
        # timeout – Seconds to wait for image creation. None is forever.
        # validate_checksum (bool) – If true and cloud returns checksum, compares
        # return value with the one calculated or passed into this call. If value
        # does not match - raises exception. Default is ‘false’
        # use_import (bool) – Use the interoperable image import mechanism to
        # import the image. This defaults to false because it is harder on the
        # target cloud so should only be used when needed, such as when the user
        # needs the cloud to transform image format. If the cloud has disabled
        # direct uploads, this will default to true.
        # stores – List of stores to be used when enabled_backends is activated in
        # glance. List values can be the id of a store or a Store instance. Implies
        # use_import equals True.
        # all_stores – Upload to all available stores. Mutually exclusive with
        # store and stores. Implies use_import equals True.
        # all_stores_must_succeed – When set to True, if an error occurs during the
        # upload in at least one store, the worfklow fails, the data is deleted
        # from stores where copying is done (not staging), and the state of the
        # image is unchanged. When set to False, the workflow will fail (data
        # deleted from stores, …) only if the import fails on all stores specified
        # by the user. In case of a partial success, the locations added to the
        # image will be the stores where the data has been correctly uploaded.
        # Default is True. Implies use_import equals True.
        # Additional kwargs will be passed to the image creation as additional
        # metadata for the image and will have all values converted to string
        # except for min_disk, min_ram, size and virtual_size which will be
        # converted to int.
        # If you are sure you have all of your data types correct or have an
        # advanced need to be explicit, use meta. If you are just a normal
        # consumer, using kwargs is likely the right choice.
        # If a value is in meta and kwargs, meta wins.
        # Returns
        # A munch.Munch of the Image object
        # Raises
        # SDKException if there are problems uploading
        """
        os_sdk_conn = self.os_sdk_conn
        if admin:
            os_sdk_conn = self.os_sdk_admin_conn
        image = os_sdk_conn.image.create_image(name=image_name,
                                               filename=filename,
                                               container_format=container_format,
                                               disk_format=disk_format,
                                               visibility=visibility,
                                               wait=wait, timeout=timeout)
        if debug1:
            print("created image: " + image.name + " id: " + image.id)
        if autoclear:
            self.images_clearing.append(image.id)
        return image

    def _delete_image(self, name_or_id, autoclear=True):
        """
        # Delete an image
        # Parameters
        #       name_or_id – The name or ID of a image.
        #       ignore_missing (bool) – When set to False ResourceNotFound will be
        #       raised when the image does not exist. When set to True, no
        #       exception will be set when attempting to delete a nonexistent
        #       image.
        # Returns
        #       None
        """
        image = self._find_image(name_or_id)
        if image:
            self.os_sdk_conn.image.delete_image(image.id, ignore_missing=False)
            if debug1: print(
                "created image: " + image.name + " id: " + image.id)
            if autoclear:
                self.images_clearing.remove(image.id)

    def _list_images(self, **query):
        """
        # Return a generator of images
        # Parameters
        #       query (kwargs) – Optional query parameters to be sent to limit the
        #       resources being returned.
        # Returns
        #       A generator of image objects
        # Return type
        #       Image
        """
        return self.gc.images.list(**query)

    def _update_image(self, image, **attrs):
        """
        # Update a image
        # Parameters
        #       image – Either the ID of a image or a Image instance.
        #       Attrs kwargs
        #       The attributes to update on the image represented by value.
        # Returns
        #       The updated image
        # Return type
        #       Image
        """
        self.os_sdk_conn.image.update_image(image, **attrs)
        return self._get_image(image.id)

    def _upload_image(self, image_id, filename):
        """
        # upload_image(container_format=None, disk_format=None, data=None, **attrs)
        # Create and upload a new image from attributes
        # Parameters
        #       container_format – Format of the container. A valid value is ami,
        #       ari, aki, bare, ovf, ova, or docker.
        #       disk_format – The format of the disk. A valid value is ami, ari,
        #       aki, vhd, vmdk, raw, qcow2, vdi, or iso.
        #       data – The data to be uploaded as an image.
        #       attrs (dict) – Keyword arguments which will be used to create a
        #       Image, comprised of the properties on the Image class.
        # Returns
        #       The results of image creation
        # Return type
        #       Image
        """
        image = self.gc.images.upload(
            image_id,
            open(filename, 'rb')
        )
        return image

    def _download_image(self, image, stream=False, output=None,
                        chunk_size=1024):
        """
        # Download an image
        # This will download an image to memory when stream=False, or allow
        # streaming downloads using an iterator when stream=True. For examples of
        # working with streamed responses, see Downloading an Image with
        # stream=True.
        # Parameters
        #       image – The value can be either the ID of an image or a Image
        #       instance.
        #       stream (bool) –
        #       When True, return a requests.Response instance allowing you to
        #       iterate over the response data stream instead of storing its
        #       entire contents in memory. See requests.Response.iter_content()
        #       for more details. NOTE: If you do not consume the entirety of the
        #       response you must explicitly call requests.Response.close() or
        #       otherwise risk inefficiencies with the requests library’s
        #       handling of connections.
        #       When False, return the entire contents of the response.
        #       output – Either a file object or a path to store data into.
        #       chunk_size (int) – size in bytes to read from the wire and buffer
        #       at one time. Defaults to 1024
        # Returns
        #       When output is not given - the bytes comprising the given Image
        #       when stream is False, otherwise a requests.Response instance.
        #       When output is given - a Image instance.
        """
        return self.os_sdk_conn.image.download_image(image, stream=True,
                                                     output=output,
                                                     chunk_size=chunk_size)

    def _find_image(self, image_name_or_id, ignore_missing=True):
        """
        # Find a single image
        # Parameters
        #       image_name_or_id – The name or ID of a image.
        #       ignore_missing (bool) – When set to False ResourceNotFound will be
        #       raised when the resource does not exist. When set to True, None
        #       will be returned when attempting to find a nonexistent resource.
        # Returns
        #       One Image or None
        """
        return self.os_sdk_conn.image.find_image(image_name_or_id,
                                                 ignore_missing=ignore_missing)

    def _get_image(self, image_name_or_id):
        """
        # Get a single image
        # Parameters
        #       image_name_or_id – The name or ID of a image.
        # Returns
        #       One Image
        # Raises
        #       ResourceNotFound when no resource can be found.
        """
        image = self._find_image(image_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.image.get_image(image.id)

    def _deactivate_image(self, image):
        """
        # Deactivate an image
        # Parameters
        #       image – Either the ID of a image or a Image instance.
        # Returns
        #       None
        """
        self.os_sdk_conn.image.deactivate_image(image.id)

    def _reactivate_image(self, image):
        """
        # Deactivate an image
        # Parameters
        #       image – Either the ID of a image or a Image instance.
        # Returns
        #       None
        """
        self.os_sdk_conn.image.reactivate_image(image.id)

    # -------------------------------------------------------------------------
    # Network methods - Neutron
    # -------------------------------------------------------------------------

    def _create_floatingip(self, subnet_id, floating_network_id, port_id=None,
                           autoclear=True, **attrs):
        """
        # Create a new floating ip from attributes
        # Parameters
        # autoclear – Used in the teardown mechanism (keep default value)
        # attrs (dict) – Keyword arguments which will be used to create a
        # FloatingIP, comprised of the properties on the FloatingIP class.
        # Returns
        # The results of floating ip creation
        # Return type
        # FloatingIP
        """
        fip = self.os_sdk_conn.network.create_ip(
            subnet_id=subnet_id,
            floating_network_id=floating_network_id,
            port_id=port_id, **attrs
        )
        if debug1: print("created fip: " + fip.name + " id: " + fip.id)
        if autoclear:
            self.floating_ips_clearing.append(fip.id)
        return fip

    def _delete_floatingip(self, fip_name_or_id, if_revision=None,
                           autoclear=True):
        """
        # Delete a floating ip
        # Parameters
        # fip_name_or_id – The name or ID of an IP or a FloatingIP instance.
        # ignore_missing (bool) – When set to False ResourceNotFound will be
        # raised when the floating ip does not exist. When set to True, no
        # exception will be set when attempting to delete a nonexistent ip.
        # if_revision (int) – Revision to put in If-Match header of update
        # request to perform compare-and-swap update.
        # autoclear – Used in the teardown mechanism (keep default value)
        # Returns
        # None
        """
        fip = self._find_floatingip(fip_name_or_id, ignore_missing=False)
        self.os_sdk_conn.network.delete_ip(fip.id, if_revision=if_revision)
        if debug1:
            print("deleted fip: " + fip.name + " id: " + fip.id)
        if autoclear:
            self.floating_ips_clearing.remove(fip.id)

    def _update_floatingip(self, fip_name_or_id, if_revision=None, **args):
        fip = self._find_floatingip(fip_name_or_id, ignore_missing=False)
        """
        # Update a ip
        # Parameters
        # fip_name_or_id – The name or ID of an IP or a FloatingIP instance.
        # if_revision (int) – Revision to put in If-Match header of update request
        # to perform compare-and-swap update.
        # attrs (dict) – The attributes to update on the ip represented by value.
        # Returns
        # The updated ip
        # Return type
        # FloatingIP
        """
        return self.os_sdk_conn.network.update_ip(fip.id,
                                                  if_revision=if_revision,
                                                  **args)

    def _list_floatingips(self, **query):
        """
        # Return a generator of ips
        # Parameters
        # query (dict) –
        # Optional query parameters to be sent to limit
        # the resources being returned. Valid parameters are:
        # description: The description of a floating IP.
        # fixed_ip_address: The fixed IP address associated with a
        # floating IP address.
        # floating_ip_address: The IP address of a floating IP.
        # floating_network_id: The ID of the network associated with
        # a floating IP.
        # port_id: The ID of the port to which a floating IP is
        # associated.
        # project_id: The ID of the project a floating IP is
        # associated with.
        # router_id: The ID of an associated router.
        # status: The status of a floating IP, which can be ACTIVE
        # or DOWN.
        # Returns
        # A generator of floating IP objects
        # Return type
        # FloatingIP
        """
        return self.os_sdk_conn.network.ips(**query)

    def _find_floatingip(self, fip_name_or_id, ignore_missing=True, **args):
        """
        # Find a single FloatingIP
        # Parameters
        # fip_name_or_id – The name or ID of a FloatingIP instance.
        # ignore_missing (bool) – When set to False ResourceNotFound will be raised
        # when the resource does not exist. When set to True, None will be returned
        # when attempting to find a nonexistent resource.
        # args (dict) – Any additional parameters to be passed into underlying
        # methods. such as query filters.
        # Returns
        # One FloatingIP or None
        """
        return self.os_sdk_conn.network.find_ip(fip_name_or_id,
                                                ignore_missing=ignore_missing,
                                                **args)

    def _get_floatingip(self, fip_name_or_id):
        """
        # Get a single floating ip
        # Parameters
        # fip_name_or_id – The name or ID of a FloatingIP instance.
        # Returns
        # One FloatingIP
        # Raises
        # ResourceNotFound when no resource can be found.
        """
        fip = self._find_floatingip(fip_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.get_ip(fip.id)

    def _create_router(self, name, ext_network_name, autoclear=True, **attrs):
        """
        # Create a new router from attributes
        # Parameters
        # autoclear – Used in the teardown mechanism (keep default value)
        # attrs (dict) – Keyword arguments which will be used to create a Router,
        # comprised of the properties on the Router class.
        # Returns
        # The results of router creation
        # Return type
        # Router
        """
        network = self._get_network(ext_network_name)
        router = self.os_sdk_conn.network.create_router(
            name=name,
            external_gateway_info={'network_id': network.id},
            **attrs
        )
        if debug1: print(
            "created router: " + router.name + " id: " + router.id)
        if autoclear:
            self.routers_clearing.append(router.id)
        return router

    def _delete_router(self, router_name_or_id, ignore_missing=True,
                       if_revision=None, autoclear=True):
        """
        # Delete a router
        # Parameters
        # router_name_or_id – The name or ID of a Router instance.
        # ignore_missing (bool) – When set to False ResourceNotFound will be raised
        # when the router does not exist. When set to True, no exception will be
        # set when attempting to delete a nonexistent router.
        # if_revision (int) – Revision to put in If-Match header of update request
        # to perform compare-and-swap update.
        # autoclear – Used in the teardown mechanism (keep default value)
        # Returns
        # None
        """
        router = self._find_router(router_name_or_id, ignore_missing=False)
        self.os_sdk_conn.network.delete_router(router.id,
                                               ignore_missing=ignore_missing,
                                               if_revision=if_revision)
        if debug1: print(
            "deleted router: " + router.name + " id: " + router.id)
        if autoclear:
            self.routers_clearing.remove(router.id)

    def _update_router(self, router_name_or_id, if_revision=None, **args):
        """
        # Update a router
        # Parameters
        # router_name_or_id – The name or ID of a Router instance.
        # if_revision (int) – Revision to put in If-Match header of update request
        # to perform compare-and-swap update.
        # attrs (dict) – The attributes to update on the router represented by
        # router.
        # Returns
        # The updated router
        # Return type
        # Router
        """
        router = self._find_router(router_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.update_router(router.id,
                                                      if_revision=if_revision,
                                                      **args)

    def _list_routers(self, **query):
        """
        # Return a generator of routers
        # Parameters
        # query (dict) –
        # Optional query parameters to be sent to limit
        # the resources being returned. Valid parameters are:
        # description: The description of a router.
        # flavor_id: The ID of the flavor.
        # is_admin_state_up: Router administrative state is up or not
        # is_distributed: The distributed state of a router
        # is_ha: The highly-available state of a router
        # name: Router name
        # project_id: The ID of the project this router is associated
        # with.
        # status: The status of the router.
        # Returns
        # A generator of router objects
        # Return type
        # Router
        """
        return self.os_sdk_conn.network.routers(**query)

    def _find_router(self, router_name_or_id, ignore_missing=True, **args):
        """
        # Find a single router
        # Parameters
        # router_name_or_id – The name or ID of a router.
        # ignore_missing (bool) – When set to False ResourceNotFound will be raised
        # when the resource does not exist. When set to True, None will be returned
        # when attempting to find a nonexistent resource.
        # args (dict) – Any additional parameters to be passed into underlying
        # methods. such as query filters.
        # Returns
        # One Router or None
        """
        return self.os_sdk_conn.network.find_router(router_name_or_id,
                                                    ignore_missing=ignore_missing,
                                                    **args)

    def _get_router(self, router_name_or_id):
        """
        # Get a single router
        # Parameters
        # router_name_or_id – The name or ID of a Router instance.
        # Returns
        # One Router or None
        """
        router = self._find_router(router_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.get_router(router.id)

    def _add_interface_to_router(self, ri, autoclear=True):
        """
        # Add Interface to a router
        # Parameters
        # ri – ID of an OpenStackRouterInterface instance
        # autoclear – Used in the teardown mechanism (keep default value)
        # Returns
        # Router with updated interface
        # Return type
        # class
        # ~openstack.network.v2.router.Router
        """
        router = self._find_router(ri.router_name_or_id, ignore_missing=False)
        subnet = self._find_subnet(ri.subnet_name_or_id, ignore_missing=False)
        interface = self.os_sdk_conn.network.add_interface_to_router(
            router.id,
            subnet_id=subnet.id
        )
        if debug1:
            print("added interface to router " + router.name + " : "
                  + subnet.name + " id: " + subnet.id)
        if autoclear:
            self.interfaces_clearing.append(ri)
        return interface

    def _delete_interface_from_router(self, ri, autoclear=True):
        """
        # Remove Interface from a router
        # Parameters
        # ri – ID of an OpenStackRouterInterface instance
        # autoclear – Used in the teardown mechanism (keep default value)
        # Returns
        # Router with updated interface
        # Return type
        # class
        # ~openstack.network.v2.router.Router
        """
        router = self._find_router(ri.router_name_or_id, ignore_missing=False)
        subnet = self._find_subnet(ri.subnet_name_or_id, ignore_missing=False)
        self.os_sdk_conn.network.remove_interface_from_router(
            router.id,
            subnet_id=subnet.id
        )
        if debug1:
            print("removed interface from router " + router.name + " : " +
                  subnet.name + " id: " + subnet.id)
        if autoclear:
            self.interfaces_clearing.remove(ri)

    def _create_network(self, name, shared=False, autoclear=True, **args):
        """
        # Create a new network from attributes
        # Parameters
        # autoclear – Used in the teardown mechanism (keep default value)
        # attrs (dict) – Keyword arguments which will be used to create a Network,
        # comprised of the properties on the Network class.
        # Returns
        # The results of network creation
        # Return type
        # Network
        """
        conn = self.os_sdk_conn
        network = conn.network.create_network(name=name, shared=shared, **args)
        if debug1: print(
            "created network: " + network.name + " id: " + network.id)
        if autoclear:
            self.networks_clearing.append(network.id)
        return network

    def _delete_network(self, network_name_or_id, if_revision=None,
                        autoclear=True):
        """
        # Delete a network
        # Parameters
        # network_name_or_id – The name or ID of a Network instance.
        # ignore_missing (bool) – When set to False ResourceNotFound will be raised
        # when the network does not exist. When set to True, no exception will be
        # set when attempting to delete a nonexistent network.
        # if_revision (int) – Revision to put in If-Match header of update request
        # to perform compare-and-swap update.
        # autoclear – Used in the teardown mechanism (keep default value)
        # Returns
        # None
        """
        network = self._find_network(network_name_or_id, ignore_missing=False)
        self.os_sdk_conn.network.delete_network(network.id,
                                                if_revision=if_revision)
        if debug1: print(
            "deleted network: " + network.name + " id: " + network.id)
        if autoclear:
            self.networks_clearing.remove(network.id)

    def _update_network(self, network_name_or_id, if_revision=None, **args):
        """
        # Update a network
        # Parameters
        # network_name_or_id – The name or ID of a Network instance.
        # if_revision (int) – Revision to put in If-Match header of update request
        # to perform compare-and-swap update.
        # attrs (dict) – The attributes to update on the network represented by
        # network.
        # Returns
        # The updated network
        # Return type
        # Network
        """
        network = self._find_network(network_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.update_network(network.id,
                                                       if_revision=if_revision,
                                                       **args)

    def _list_networks(self, **query):
        """
        # Return a generator of networks
        # Parameters
        # query (kwargs) –
        # Optional query parameters to be sent to limit the resources being
        # returned. Available parameters include:
        # description: The network description.
        # ipv4_address_scope_id: The ID of the IPv4 address scope for
        # the network.
        # ipv6_address_scope_id: The ID of the IPv6 address scope for
        # the network.
        # is_admin_state_up: Network administrative state
        # is_port_security_enabled: The port security status.
        # is_router_external: Network is external or not.
        # is_shared: Whether the network is shared across projects.
        # name: The name of the network.
        # status: Network status
        # project_id: Owner tenant ID
        # provider_network_type: Network physical mechanism
        # provider_physical_network: Physical network
        # provider_segmentation_id: VLAN ID for VLAN networks or Tunnel
        # ID for GENEVE/GRE/VXLAN networks
        # Returns
        # A generator of network objects
        # Return type
        # Network
        """
        return self.os_sdk_conn.list_networks(**query)

    def _find_network(self, network_name_or_id, ignore_missing=True, **args):
        """
        # Find a single network
        # Parameters
        # network_name_or_id – The name or ID of a Network instance.
        # ignore_missing (bool) – When set to False ResourceNotFound will be raised
        # when the resource does not exist. When set to True, None will be returned when attempting to find a nonexistent resource.
        # args (dict) – Any additional parameters to be passed into underlying
        # methods. such as query filters.
        # Returns
        # One Network or None
        """
        return self.os_sdk_conn.network.find_network(network_name_or_id,
                                                     ignore_missing=ignore_missing,
                                                     **args)

    def _get_network(self, network_name_or_id):
        """
        # Get a single network
        # Parameters
        # network_name_or_id – The name or ID of a Network instance.
        # Returns
        # One Network or None
        """
        network = self._find_network(network_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.get_network(network.id)

    def _create_subnet(self, name, network_name_or_id, enable_dhcp=True,
                       ip_version=4, cidr=None, gateway_ip=None,
                       autoclear=True, **attrs):
        """
        # Create a new subnet from attributes
        # Parameters
        # autoclear – Used in the teardown mechanism (keep default value)
        # attrs (dict) – Keyword arguments which will be used to create a Subnet,
        # comprised of the properties on the Subnet class.
        # Returns
        # The results of subnet creation
        # Return type
        # Subnet
        """
        network = self._find_network(network_name_or_id, ignore_missing=False)
        subnet = self.os_sdk_conn.network.create_subnet(
            name=name,
            network_id=network.id,
            enable_dhcp=enable_dhcp,
            cidr=cidr,
            gateway_ip=gateway_ip,
            ip_version=ip_version,
            **attrs
        )
        if debug1: print(
            "created subnet: " + subnet.name + " id: " + subnet.id)
        if autoclear:
            self.subnets_clearing.append(subnet.id)
        return subnet

    def _delete_subnet(self, subnet_name_or_id, if_revision=None,
                       autoclear=True):
        """
        # Delete a subnet
        # Parameters
        # subnet_name_or_id – The name or ID of a Subnet instance.
        # ignore_missing (bool) – When set to False ResourceNotFound will be raised
        # when the subnet does not exist. When set to True, no exception will be
        # set when attempting to delete a nonexistent subnet.
        # if_revision (int) – Revision to put in If-Match header of update request
        # to perform compare-and-swap update.
        # autoclear – Used in the teardown mechanism (keep default value)
        # Returns
        # None
        """
        subnet = self._find_subnet(subnet_name_or_id, ignore_missing=False)
        self.os_sdk_conn.network.delete_subnet(subnet.id,
                                               if_revision=if_revision)
        if debug1: print(
            "deleted subnet: " + subnet.name + " id: " + subnet.id)
        if autoclear:
            self.subnets_clearing.remove(subnet.id)

    def _update_subnet(self, subnet_name_or_id, if_revision=None, **args):
        """
        # Update a subnet
        # Parameters
        # subnet_name_or_id – The name or ID of a Subnet instance.
        # if_revision (int) – Revision to put in If-Match header of update request
        # to perform compare-and-swap update.
        # attrs (dict) – The attributes to update on the subnet represented by
        # subnet.
        # Returns
        # The updated subnet
        # Return type
        # Subnet
        """
        subnet = self._find_subnet(subnet_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.update_subnet(subnet.id,
                                                      if_revision=if_revision,
                                                      **args)

    def _list_subnets(self, **query):
        """
        # Return a generator of subnets
        # Parameters
        # query (dict) –
        # Optional query parameters to be sent to limit the resources being
        # returned. Available parameters include:
        # cidr: Subnet CIDR
        # description: The subnet description
        # gateway_ip: Subnet gateway IP address
        # ip_version: Subnet IP address version
        # ipv6_address_mode: The IPv6 address mode
        # ipv6_ra_mode: The IPv6 router advertisement mode
        # is_dhcp_enabled: Subnet has DHCP enabled (boolean)
        # name: Subnet name
        # network_id: ID of network that owns the subnets
        # project_id: Owner tenant ID
        # subnet_pool_id: The subnet pool ID from which to obtain a
        # CIDR.
        # Returns
        # A generator of subnet objects
        # Return type
        # Subnet
        """
        return self.os_sdk_conn.list_subnets(**query)

    def _find_subnet(self, subnet_name_or_id, ignore_missing=True, **args):
        """
        # Find a single subnet
        # Parameters
        # subnet_name_or_id – The name or ID of a Subnet instance.
        # ignore_missing (bool) – When set to False ResourceNotFound will be raised
        # when the resource does not exist. When set to True, None will be returned
        # when attempting to find a nonexistent resource.
        # args (dict) – Any additional parameters to be passed into underlying
        # methods. such as query filters.
        # Returns
        # One Subnet or None
        """
        return self.os_sdk_conn.network.find_subnet(
            subnet_name_or_id,
            ignore_missing=ignore_missing,
            **args
        )

    def _get_subnet(self, subnet_name_or_id):
        """
        # Get a single subnet
        # Parameters
        # subnet_name_or_id – The name or ID of a Subnet instance.
        # Returns
        # One Subnet or None
        """
        subnet = self._find_subnet(subnet_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.get_subnet(subnet.id)

    def _create_port(self, port_name, network_name_or_id, autoclear=True,
                     **attrs):
        """
        # Create a new port from attributes
        # Parameters
        # autoclear – Used in the teardown mechanism (keep default value)
        # attrs (dict) – Keyword arguments which will be used to create a Port,
        # comprised of the properties on the Port class.
        # Returns
        # The results of port creation
        # Return type
        # Port
        """
        network = self._find_network(network_name_or_id, ignore_missing=False)
        port = self.os_sdk_conn.network.create_port(name=port_name,
                                                    network_id=network.id,
                                                    **attrs)
        if debug1: print("created port id: " + port.id)
        if autoclear:
            self.ports_clearing.append(port.id)
        return port

    def _delete_port(self, port_name_or_id, if_revision=None, autoclear=True):
        """
        # Delete a port
        # Parameters
        # port_name_or_id – The name or ID of a Port instance.
        # ignore_missing (bool) – When set to False ResourceNotFound will be raised
        # when the port does not exist. When set to True, no exception will be set
        # when attempting to delete a nonexistent port.
        # if_revision (int) – Revision to put in If-Match header of update request
        # to perform compare-and-swap update.
        # autoclear – Used in the teardown mechanism (keep default value)
        # Returns
        # None
        """
        port = self._find_port(port_name_or_id, ignore_missing=False)
        self.os_sdk_conn.network.delete_port(port.id, if_revision=if_revision)
        if debug1: print("deleted port id: " + port.id)
        if autoclear:
            self.ports_clearing.remove(port.id)

    def _update_port(self, port_name_or_id, if_revision=None, **args):
        """
        # Update a port
        # Parameters
        # port_name_or_id – The name or ID of a Port instance.
        # if_revision (int) – Revision to put in If-Match header of update request
        # to perform compare-and-swap update.
        # attrs (dict) – The attributes to update on the port represented by port.
        # Returns
        # The updated port
        # Return type
        # Port
        """
        port = self._find_port(port_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.update_port(port.id,
                                                    if_revision=if_revision,
                                                    **args)

    def _list_ports(self, **kwargs):
        """
        # Return a generator of ports
        # Parameters
        # query (kwargs) –
        # Optional query parameters to be sent to limit the resources being
        # returned. Available parameters include:
        # description: The port description.
        # device_id: Port device ID.
        # device_owner: Port device owner (e.g. network:dhcp).
        # ip_address: IP addresses of an allowed address pair.
        # is_admin_state_up: The administrative state of the port.
        # is_port_security_enabled: The port security status.
        # mac_address: Port MAC address.
        # name: The port name.
        # network_id: ID of network that owns the ports.
        # project_id: The ID of the project who owns the network.
        # status: The port status. Value is ACTIVE or DOWN.
        # subnet_id: The ID of the subnet.
        # Returns
        # A generator of port objects
        # Return type
        # Port
        """
        return self.os_sdk_conn.network.ports(**kwargs)

    def _find_port(self, port_name_or_id, ignore_missing=True, **args):
        """
        # Find a single port
        # Parameters
        # port_name_or_id – The name or ID of a Port instance.
        # ignore_missing (bool) – When set to False ResourceNotFound will be raised
        # when the resource does not exist. When set to True, None will be returned
        # when attempting to find a nonexistent resource.
        # args (dict) – Any additional parameters to be passed into underlying
        # methods. such as query filters.
        # Returns
        # One Port or None
        """
        return self.os_sdk_conn.network.find_port(port_name_or_id,
                                                  ignore_missing=True, **args)

    def _get_port(self, port_name_or_id):
        """
        # Get a single port
        # Parameters
        # port_name_or_id – The name or ID of a Port instance.
        # Returns
        # One Port
        # Raises
        # ResourceNotFound when no resource can be found.
        """
        port = self._find_port(port_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.get_port(port.id)

    def _create_security_group(self, name, autoclear=True, **attrs):
        """
        # Create a new security group from attributes
        # Parameters
        #       autoclear – Used in the teardown mechanism (keep default value)
        #       attrs (dict) – Keyword arguments which will be used to create a
        #       SecurityGroup, comprised of the properties on the SecurityGroup
        #       class.
        # Returns
        #       The results of security group creation
        # Return type
        #       SecurityGroup
        """
        sg = self.os_sdk_conn.network.create_security_group(name=name, **attrs)
        if debug1: print("created SG: " + sg.name + " id: " + sg.id)
        if autoclear:
            self.security_groups_clearing.append(sg.id)
        return sg

    def _delete_security_group(self, sg_name_or_id, ignore_missing=True,
                               if_revision=None, autoclear=True):
        """
        # Delete a security group
        # Parameters
        #       sg_name_or_id – The name or ID of a SecurityGroup instance.
        #       ignore_missing (bool) – When set to False ResourceNotFound will be
        #       raised when the security group does not exist. When set to True, no
        #       exception will be set when attempting to delete a nonexistent
        #       security group.
        #       if_revision (int) – Revision to put in If-Match header of update
        #       request to perform compare-and-swap update.
        #       autoclear – Used in the teardown mechanism (keep default value)
        # Returns
        #       None
        """
        sg = self._find_security_group(sg_name_or_id, ignore_missing=False)
        self.os_sdk_conn.network.delete_security_group(
            sg.id,
            ignore_missing=ignore_missing,
            if_revision=if_revision
        )
        if debug1: print("deleted SG: " + sg.name + " id: " + sg.id)
        if autoclear:
            self.security_groups_clearing.remove(sg.id)

    def _update_security_group(self, sg_name_or_id, description=None,
                               if_revision=None, **attrs):
        """
        # Update a security group
        # Parameters
        #       sg_name_or_id – The name or ID of a SecurityGroup instance.
        #       attrs (dict) – The attributes to update on the security group
        #       represented by security_group.
        # Returns
        #       The updated security group
        # Return type
        #       SecurityGroup
        """
        sg = self._find_security_group(sg_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.update_security_group(
            sg.id,
            description=description,
            if_revision=if_revision,
            **attrs
        )

    def _list_security_groups(self, **query):
        """
        # Return a generator of security groups
        # Parameters
        #       query (dict) –
        #       Optional query parameters to be sent to limit the resources being
        #       returned.
        #       Valid parameters are:
        #           description: Security group description
        #           ìd: The id of a security group, or list of security group ids
        #           name: The name of a security group
        #           project_id: The ID of the project this security group is
        #           associated with.
        # Returns
        #       A generator of security group objects
        # Return type
        #       SecurityGroup
        """
        return self.os_sdk_conn.network.security_groups(**query)

    def _find_security_group(self, sg_name_or_id, ignore_missing=True, **args):
        """
        # Find a single security group
        # Parameters
        #       sg_name_or_id – The name or ID of a SecurityGroup instance.
        #       ignore_missing (bool) – When set to False ResourceNotFound will be
        #       raised when the resource does not exist. When set to True, None
        #       will be returned when attempting to find a nonexistent resource.
        #       args (dict) – Any additional parameters to be passed into
        #       underlying methods. such as query filters.
        # Returns
        #       One SecurityGroup or None
        """
        return self.os_sdk_conn.network.find_security_group(
            sg_name_or_id,
            ignore_missing=ignore_missing,
            **args
        )

    def _get_security_group(self, sg_name_or_id):
        """
        # Get a single security group
        # Parameters
        #       sg_name_or_id – The name or ID of a SecurityGroup instance.
        # Returns
        #       One SecurityGroup
        # Raises
        #       ResourceNotFound when no resource can be found.
        """
        sg = self._find_security_group(sg_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.network.get_security_group(sg.id)

    # -------------------------------------------------------------------------
    # Server methods - Nova
    # -------------------------------------------------------------------------

    def _create_server(self, server_name, image_name_or_id, flavor_name_or_id,
                       network_name=None, autoclear=True, **attrs):
        """
        # Create a new server from attributes
        # Parameters
        #       autoclear – Used in the teardown mechanism (keep default value)
        #       attrs (dict) – Keyword arguments which will be used to create a
        #       Server, comprised of the properties on the Server class.
        # Returns
        #       The results of server creation
        # Return type
        #       Server
        """
        image = self._find_image(image_name_or_id, ignore_missing=False)
        flavor = self._find_flavor(flavor_name_or_id, ignore_missing=False)
        if network_name:
            network = self.os_sdk_conn.network.find_network(network_name)
            instance = self.os_sdk_conn.compute.create_server(
                name=server_name,
                image_id=image.id,
                flavor_id=flavor.id,
                networks=[{"uuid": network.id}],
                **attrs
            )
        else:
            # instance = self.os_sdk_conn.compute.create_server(
            #   name=server_name,
            #   image_id=image.id,
            #   flavor_id=flavor.id,
            #   networks=[],
            #   autoip=False,
            #   **attrs
            # )
            instance = self.os_sdk_conn.compute.create_server(
                name=server_name,
                image_id=image.id,
                flavor_id=flavor.id,
                networks=[],
                **attrs
            )
        if debug1: print(
            "created instance: " + instance.name + " id: " + instance.id)
        if autoclear:
            self.instances_clearing.append(instance.id)
        return self._wait_for_server(instance)

    def _delete_server(self, instance_name_or_id, autoclear=True):
        """
        # Delete a server
        # Parameters
        #       name_or_id – The name or ID of a server.
        #       ignore_missing (bool) – When set to False ResourceNotFound will be
        #       raised when the server does not exist. When set to True, no
        #       exception will be set when attempting to delete a nonexistent
        #       server
        #       force (bool) – When set to True, the server deletion will be forced
        #       immediately.
        #       autoclear – Used in the teardown mechanism (keep default value)
        # Returns
        # None
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        if instance:
            self.os_sdk_conn.compute.delete_server(instance.id,
                                                   ignore_missing=False)
            if debug1: print(
                "deleted instance: " + instance.name + " id: " + instance.id)
            if autoclear:
                self.instances_clearing.remove(instance.id)
            self.os_sdk_conn.compute.wait_for_delete(instance)
        elif debug1:
            print("error: not found instance: " + instance_name_or_id)

    def _update_server(self, instance_name_or_id, **kwargs):
        """
        # Update a server
        # Parameters
        #       instance_name_or_id – The name or ID of a server.
        # Attrs kwargs
        #       The attributes to update on the server represented by server.
        # Returns
        #       The updated server
        # Return type
        #       Server
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        update = None
        if instance:
            update = self.os_sdk_conn.compute.update_server(instance.id,
                                                            **kwargs)
            if debug1: print(
                "updated instance: " + instance.name + " id: " + instance.id)
        elif debug1:
            print("error: not found instance: " + instance_name_or_id)
        return update

    def _wait_for_server(self, server, status='ACTIVE', failures=None,
                         interval=2, wait=120):
        """
        # Wait for a server to be in a particular status.
        # Parameters
        #       server (Server:) – The Server to wait on to reach the specified
        #       status.
        #       status – Desired status.
        #       failures (list) – Statuses that would be interpreted as failures.
        #       interval (int) – Number of seconds to wait before to consecutive
        #       checks. Default to 2.
        #       wait (int) – Maximum number of seconds to wait before the change.
        #       Default to 120.
        # Returns
        #       The resource is returned on success.
        # Raises
        #       ResourceTimeout if transition to the desired status failed to occur
        #       in specified seconds.
        #       ResourceFailure if the resource has transited to one of the failure
        #       statuses.
        #       AttributeError if the resource does not have a status attribute.
        """
        return self.os_sdk_conn.compute.wait_for_server(server, status=status,
                                                        failures=failures,
                                                        interval=interval,
                                                        wait=wait)

    def _list_servers(self, details=True, all_projects=False, **query):
        """
        # Retrieve a generator of servers
        # Parameters
        #       details (bool) – When set to False instances with only basic data
        #       will be returned. The default, True, will cause instances with full
        #       data to be returned.
        #       query (kwargs) – Optional query parameters to be sent to limit the
        #       servers being returned. Available parameters can be seen under
        #       https://docs.openstack.org/api-ref/compute/#list-servers
        # Returns
        #       A generator of server instances.
        ##
        # def _servers(self, details=True, all_projects=False, **query):
        #     return self.os_sdk_conn.compute.servers(details, all_projects,
        #     **query)
        """
        return self.os_sdk_conn.compute.servers(details=details,
                                                all_projects=all_projects,
                                                **query)

    def _find_server(self, instance_name_or_id, ignore_missing=True):
        """
        # Find a single server
        # Parameters
        #       instance_name_or_id – The name or ID of a server.
        #       ignore_missing (bool) – When set to False ResourceNotFound will be
        #       raised when the resource does not exist. When set to True, None
        #       will be returned when attempting to find a nonexistent resource.
        # Returns
        #       One Server or None
        """
        return self.os_sdk_conn.compute.find_server(
            instance_name_or_id,
            ignore_missing=ignore_missing
        )

    def _get_server(self, instance_name_or_id):
        """
        # Get a single server
        # Parameters:
        #       instance_name_or_id – The name or ID of a server.
        # Returns:
        #   One Server
        # Raises:
        #   ResourceNotFound when no resource can be found.
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.compute.get_server(instance.id)

    def _get_flavor(self, flavor_name_or_id, get_extra_specs=False):
        """
        # Get a single flavor
        # Parameters
        #       flavor_name_or_id – The name or ID of a flavor.
        #       get_extra_specs (bool) – When set to True and extra_specs not
        #       present in the response will invoke additional API call to fetch
        #       extra_specs.
        # Returns
        #       One Flavor
        # Raises
        #       ResourceNotFound when no resource can be found.
        """
        flavor = self._find_flavor(flavor_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.compute.get_flavor(flavor.id,
                                                   get_extra_specs=get_extra_specs)

    def _find_flavor(self, flavor_name_or_id, ignore_missing=True,
                     get_extra_specs=False, **query):
        """
        # Find a single flavor
        # Parameters
        #       flavor_name_or_id – The name or ID of a flavor.
        #       ignore_missing (bool) – When set to False ResourceNotFound will be
        #       raised when the resource does not exist. When set to True, None
        #       will be returned when attempting to find a nonexistent resource.
        #       get_extra_specs (bool) – When set to True and extra_specs not
        #       present in the response will invoke additional API call to fetch
        #       extra_specs.
        #       query (kwargs) – Optional query parameters to be sent to limit the
        #       flavors being returned.
        # Returns
        #       One Flavor or None
        """
        return self.os_sdk_conn.compute.find_flavor(flavor_name_or_id,
                                                    ignore_missing=ignore_missing,
                                                    get_extra_specs=get_extra_specs,
                                                    **query)

    def _list_flavors(self, details=True, get_extra_specs=False, **query):
        """
        # Return a generator of flavors
        # Parameters
        #       details (bool) – When True, returns Flavor objects, with additional
        #       attributes filled.
        #       get_extra_specs (bool) – When set to True and extra_specs not
        #       present in the response will invoke additional API call to fetch
        #       extra_specs.
        #       query (kwargs) – Optional query parameters to be sent to limit the
        #       flavors being returned.
        # Returns
        #       A generator of flavor objects
        ##
        # def _flavors(self):
        #     return self.os_sdk_conn.compute.flavors(details=True,
        #     get_extra_specs=False, **query)
        """
        return self.os_sdk_conn.compute.flavors(
            details=details,
            get_extra_specs=get_extra_specs,
            **query
        )
