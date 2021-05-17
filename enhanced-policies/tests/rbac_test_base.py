#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

import os
import unittest

from cinderclient import client
from glanceclient import Client
from keystoneauth1 import loading
from keystoneauth1 import session
import openstack
import os_client_config
import pytest

TEST_CLOUD = os.getenv("OS_CLOUD")


@pytest.mark.usefixtures("rbac_setup")
class TestClass(unittest.TestCase):
    os_sdk_conn = None

    def setUp(self):
        print("\nTest initialization")

        self.volumes_cleanup = []
        self.snapshots_cleanup = []
        self.instances_cleanup = []
        self.volume_bkps_cleanup = []
        self.images_cleanup = []

        self.os_sdk_admin_conn = openstack.connect(cloud=TEST_CLOUD)

        # Create users
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
            self.user21,
            self.user22,
            self.user23
        )

    # Tear down
    def tearDown(self):
        for instance_id in self.instances_cleanup:
            instance = self.os_sdk_admin_conn.compute.find_server(instance_id)
            self.os_sdk_admin_conn.compute.delete_server(instance, force=True)
            self.os_sdk_admin_conn.compute.wait_for_delete(instance)

        for image_id in self.images_cleanup:
            image = self.os_sdk_admin_conn.image.find_image(image_id)
            self.os_sdk_admin_conn.image.delete_image(image)

        for snap_id in self.snapshots_cleanup:
            snap = self.os_sdk_admin_conn.block_storage.find_snapshot(snap_id)
            self.os_sdk_admin_conn.block_storage.delete_snapshot(snap)
            self.os_sdk_admin_conn.block_storage.wait_for_delete(snap)

        for bkp_id in self.volume_bkps_cleanup:
            bkp = self.os_sdk_admin_conn.block_storage.find_backup(bkp_id)
            self.os_sdk_admin_conn.delete_volume_backup(bkp)
            self.os_sdk_admin_conn.block_storage.wait_for_delete(bkp)

        for vol_id in self.volumes_cleanup:
            vol = self.os_sdk_admin_conn.block_storage.find_volume(vol_id)
            self.os_sdk_admin_conn.delete_volume(vol, force=True)
            self.os_sdk_admin_conn.block_storage.wait_for_delete(vol)

    def _get_session_for_user(self, user):
        creds = os_client_config.OpenStackConfig()\
            .get_one_cloud(cloud=TEST_CLOUD)\
            .get_auth_args()
        loader = loading.get_plugin_loader("password")
        auth = loader.load_from_options(
            auth_url=self.os_sdk_admin_conn.auth.get("auth_url"),
            username=user.get("name"),
            password=user.get("password"),
            project_name=user.get("project"),
            project_domain_name=creds['project_domain_name'],
            user_domain_name=creds['user_domain_name'],
        )
        return session.Session(auth=auth)

    def _get_conn_for(self, user):
        self.sess = self._get_session_for_user(user)
        return openstack.connection.Connection(session=self.sess)

    #Cinder
    def _get_cclient_for(self, user):
        self.sess = self._get_session_for_user(user)
        return client.Client('3', session=self.sess, http_log_debug=True)

    #Glance
    def _get_gclient_for(self, user):
        self.sess = self._get_session_for_user(user)
        return Client('2', session=self.sess)

    def set_connections_for_user(self, user):
        self.os_sdk_conn = self._get_conn_for(user)
        self.cinderclient = self._get_cclient_for(user)
        self.gc = self._get_gclient_for(user)

    # Volume methods
    def _create_volume(self, volume_name):
        vol = self.os_sdk_conn.block_storage.create_volume(
            name=volume_name,
            size=1,
            image="cirros",
            wait=True
        )
        self.os_sdk_conn.block_storage.wait_for_status(vol, status="available")
        self.volumes_cleanup.append(vol.id)
        return vol

    def _list_volumes(self):
        volumes = self.cinderclient.volumes.list()
        return volumes

    def _get_volume(self, volume_name):
        volume = self.os_sdk_conn.block_storage.find_volume(
            volume_name,
            ignore_missing=False
        )
        return self.os_sdk_conn.block_storage.get_volume(volume)

    def _update_volume(self, volume_name, **kwargs):
        vol = self.os_sdk_conn.update_volume(volume_name, **kwargs)
        return vol

    def _get_volume_metadata(self, volume_name):
        vol = self.cinderclient.volumes.get(self._get_volume(volume_name).id)
        # NOTE(tbrito): cinderclient doesn't call /v3/{project_id}/volumes/{volume_id}/metadata explicitly
        return vol.metadata

    def _update_volume_metadata(self, volume_name, metadata):
        vol = self.cinderclient.volumes.get(self._get_volume(volume_name).id)
        # TODO: Refactor after https://review.opendev.org/c/openstack/openstacksdk/+/777801 merges
        return self.cinderclient.volumes.set_metadata(vol, metadata)

    def _delete_volume_metadata(self, volume_name, metadata_keys: list):
        vol = self.cinderclient.volumes.get(self._get_volume(volume_name).id)
        return self.cinderclient.volumes.delete_metadata(vol, metadata_keys)

    def _set_volume_readonly_flag(self, volume_name, readonly=True):
        vol = self.cinderclient.volumes.get(self._get_volume(volume_name).id)
        return self.cinderclient.volumes.update_readonly_flag(vol, readonly)

    def _retype_volume(self, volume_name, volume_type, migration_policy="never"):
        vol = self.cinderclient.volumes.get(self._get_volume(volume_name).id)
        return self.cinderclient.volumes.retype(vol, volume_type, migration_policy)

    def _extend_volume(self, volume_name, size):
        vol = self._get_volume(volume_name)
        # NOTE(tbrito): Can't use SDK method to extend because it doesn't raise
        # exceptions, only get message
        # self.os_sdk_conn.block_storage.extend_volume(vol, size=size)
        self.cinderclient.volumes.extend(vol, size)
        vol = self.os_sdk_conn.block_storage.get_volume(vol)
        self.os_sdk_conn.block_storage.wait_for_status(vol, status="available")
        return self._get_volume(volume_name)

    def _delete_volume(self, volume_name, **kwargs):
        vol = self.os_sdk_conn.block_storage.find_volume(volume_name, ignore_missing=False)
        self.os_sdk_conn.block_storage.delete_volume(vol)
        self.volumes_cleanup.remove(vol.id)

    # Volume transfer methods
    def _start_volume_transfer(self, volume_name, transfer_name):
        volume = self._get_volume(volume_name)
        return self.cinderclient.transfers.create(volume.id, transfer_name)

    def _get_volume_transfer(self, transfer_name):
        return self.cinderclient.transfers.get(
            self.cinderclient.transfers.find(name=transfer_name).id
        )

    def _accept_volume_transfer(self, transfer_id, auth_key):
        return self.cinderclient.transfers.accept(transfer_id, auth_key)

    def _list_volume_transfers(self):
        return self.cinderclient.transfers.list()

    def _delete_volume_transfer(self, transfer_name):
        return self.cinderclient.transfers.delete(
            self.cinderclient.transfers.find(name=transfer_name).id
        )

    # Volume backup methods
    def _create_volume_backup(self, volume_name, backup_name):
        vol = self._get_volume(volume_name)
        bkp = self.os_sdk_conn.block_storage.create_backup(
            volume_id=vol.id,
            name=backup_name
        )
        self.os_sdk_conn.block_storage.wait_for_status(bkp, status="available")
        self.volume_bkps_cleanup.append(bkp.id)
        return bkp

    def _get_volume_backup(self, backup_name):
        return self.os_sdk_conn.block_storage.get_backup(self.os_sdk_conn.block_storage.find_backup(backup_name))

    def _restore_volume_backup(self, backup_name, new_volume_name):
        bkp = self._get_volume_backup(backup_name)
        self.os_sdk_conn.block_storage.restore_backup(bkp, name=new_volume_name)
        bkp = self._get_volume_backup(backup_name)
        self.os_sdk_conn.block_storage.wait_for_status(bkp, status="available")
        volume = self._get_volume(new_volume_name)
        self.volumes_cleanup.append(volume.id)
        return volume

    def _delete_volume_backup(self, backup_name):
        bkp = self._get_volume_backup(backup_name)
        self.os_sdk_conn.block_storage.delete_backup(bkp)
        self.volume_bkps_cleanup.remove(bkp.id)

    # Server methods
    def _create_server(self, server_name, image_name, flavor_name):
        image = self.os_sdk_conn.image.find_image(image_name)
        flavor = self.os_sdk_conn.compute.find_flavor(flavor_name)
        server = self.os_sdk_conn.compute.create_server(
            name=server_name,
            image_id=image.id,
            flavor_id=flavor.id,
            networks=[],
            autoip=False
        )
        self.instances_cleanup.append(server.id)
        return self.os_sdk_conn.compute.wait_for_server(server)

    def _update_server(self, server, **kwargs):
        self.os_sdk_conn.compute.update_server(server, **kwargs)

    def _get_server(self, server_name):
        return self.os_sdk_conn.compute.get_server(
            self.os_sdk_conn.compute.find_server(server_name)
        )

    def _add_volume_to_server(self, server_name, volume_name):
        server = self._get_server(server_name)
        volume = self._get_volume(volume_name)
        self.os_sdk_conn.compute.create_volume_attachment(
            server,
            volume_id=volume.id
        )
        self.os_sdk_conn.block_storage.wait_for_status(volume, status="in-use")

    def _remove_volume_from_server(self, volume_name, server_name):
        server = self._get_server(server_name)
        volume = self._get_volume(volume_name)
        for attached_volume in server.attached_volumes:
            if attached_volume.get("id") == volume.id:
                self.os_sdk_conn.compute.delete_volume_attachment(
                    attached_volume.get("id"),
                    server
                )
                self.os_sdk_conn.block_store.wait_for_status(
                    volume,
                    status='available',
                    failures=['error'],
                    wait=360
                )
                
    # Snapshot methods
    def _create_snapshot(self, volume_name, name, **kwargs):
        volume = self._get_volume(volume_name)
        snapshot = self.os_sdk_conn.block_storage.create_snapshot(
            volume_id=volume.id,
            name=name,
            **kwargs
        )
        self.os_sdk_conn.block_storage.wait_for_status(
            snapshot,
            status="available"
        )
        self.snapshots_cleanup.append(snapshot.id)
        return snapshot

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
        snapshot = self.cinderclient.volume_snapshots.get(
            self._get_snapshot(snapshot_name).id
        )
        self.cinderclient.volume_snapshots.update(snapshot, **kwargs)

    def _get_snapshot_metadata(self, snapshot_name):
        return self.os_sdk_conn.block_storage.get_snapshot(
            self.os_sdk_conn.block_storage.find_snapshot(
                snapshot_name,
                ignore_missing=False
            )
        ).metadata

    def _update_snapshot_metadata(self, snapshot_name, metadata):
        snapshot = self.cinderclient.volume_snapshots.get(
            self._get_snapshot(snapshot_name).id
        )
        self.cinderclient.volume_snapshots.set_metadata(snapshot, metadata)

    def _delete_snapshot_metadata(self, snapshot_name, *metadata_keys):
        snapshot = self.cinderclient.volume_snapshots.get(
            self._get_snapshot(snapshot_name).id
        )
        self.cinderclient.volume_snapshots.delete_metadata(
            snapshot,
            metadata_keys
        )

    def _delete_snapshot(self, snapshot_name):
        snapshot = self.os_sdk_conn.block_storage.find_snapshot(snapshot_name)
        self.os_sdk_conn.block_storage.delete_snapshot(snapshot)
        self.snapshots_cleanup.remove(snapshot.id)

    # Image methods - Glance
    def _create_image_from_volume(self, volume_name, image_name):
        volume = self._get_volume(volume_name)
        self.cinderclient.volumes.upload_to_image(
            volume,
            False,
            image_name,
            container_format="bare",
            disk_format="raw"
        )
        image = self._get_image_by_name(image_name)
        self.images_cleanup.append(image.id)
        return image

    def _get_image_by_name(self, image_name):
        return self.os_sdk_conn.image.get_image(
            self.os_sdk_conn.image.find_image(image_name, ignore_missing=False)
        )
    
    def _get_image_by_id(self, image_id):
        return self.os_sdk_conn.image.get_image(image_id)

    def _create_image(self, image_name, filename=None, admin=False,
                      disk_format="qcow2", container_format="bare",
                      visibility="private", wait=True, timeout=3*60):
        os_sdk_conn = self.os_sdk_conn
        if admin:
            os_sdk_conn = self.os_sdk_admin_conn
        image = os_sdk_conn.image.create_image(
            name=image_name,
            filename=filename,
            container_format=container_format,
            disk_format=disk_format,
            visibility=visibility,
            wait=wait,
            timeout=timeout
        )
        self.images_cleanup.append(image.id)
        return image

    def _upload_image(self, image_id, filename):
        image = self.gc.images.upload(
            image_id,
            open(filename, 'rb')
        )
        return image

    def _delete_image(self, image):
        self.os_sdk_conn.image.delete_image(image)
        self.images_cleanup.remove(image.id)

    def _list_images(self):
        return self.gc.images.list()

    def _update_image(self, image, **attrs):
        self.os_sdk_conn.image.update_image(image, **attrs)
        return self._get_image_by_id(image.id)

    def _download_image(self, image):
        return self.os_sdk_conn.image.download_image(image, stream=True)

    def _deactivate_image(self, image):
        self.os_sdk_conn.image.deactivate_image(image.id)

    def _reactivate_image(self, image):
        self.os_sdk_conn.image.reactivate_image(image.id)
