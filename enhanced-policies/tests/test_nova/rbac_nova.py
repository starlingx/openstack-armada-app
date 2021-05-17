#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

from tests.fv_rbac import OpenStackBasicTesting

class OpenStackComputeTesting(OpenStackBasicTesting):

    def _get_server_console_output(self, instance_name_or_id, length=10):
        """
        Return the console output for a server.
        Parameters
            instance_name_or_id – The name or ID of a server.
            length – Optional number of line to fetch from the end of console log. All lines will be returned if this is not specified.
        Returns
            The console output as a dict. Control characters will be escaped to create a valid JSON string.
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.compute.get_server_console_output(instance.id, length)
 
    def _get_vnc_console(self, instance_name_or_id, console_type):
        """
        Get a vnc console for an instance
        Parameters
            instance_name_or_id – The name or ID of a server.
            console_type – Type of vnc console to get (‘novnc’ or ‘xvpvnc’)
        Returns
            An instance of novaclient.base.DictWithMeta
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        return self.nc.servers.get_vnc_console(instance.id, console_type)

    def _create_server_image(self, server, name, metadata=None, wait=False, timeout=120):
        """
        Create an image from a server
        Parameters
            server – Either the ID of a server or a Server instance.
            name (str) – The name of the image to be created.
            metadata (dict) – A dictionary of metadata to be set on the image.
        Returns
            Image object
        """
        return self.os_sdk_conn.compute.create_server_image(server.id, name, metadata=metadata, wait=wait, timeout=timeout)

    def _rebuild_server(self, instance_name_or_id, new_instance_name, user_password, image_name_or_id, **attrs):
        """
        Rebuild a server
        Parameters
            instance_name_or_id – The name or ID of a server.
            new_instance_name (str) – Name of the new server instance
            user_password (str) – The user password
            preserve_ephemeral (bool) – Indicates whether the server is rebuilt with the preservation of the ephemeral partition. Default: False
            image_name_or_id – The name or ID of an image to rebuild with
            access_ipv4 (str) – The IPv4 address to rebuild with. Default: None
            access_ipv6 (str) – The IPv6 address to rebuild with. Default: None
            metadata (dict) – A dictionary of metadata to rebuild with. Default: None
            personality – A list of dictionaries, each including a path and contents key, to be injected into the rebuilt server at launch. Default: None
        Returns
            The rebuilt Server instance.
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        image = self._find_image(image_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.rebuild_server(instance.id, new_instance_name, user_password, image=image.id, **attrs)
        instance = self._wait_for_server(instance, status='REBUILD', wait=60)
        return self._wait_for_server(instance, wait=60)

    def _start_server(self, instance_name_or_id):
        """
        Starts a stopped server and changes its state to ACTIVE.
        Parameters
            instance_name_or_id – The name or ID of a server.
        Returns
            Server instance
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.start_server(instance.id)
        return self._wait_for_server(instance, wait=60)

    def _stop_server(self, instance_name_or_id):
        """
        Stops a running server and changes its state to SHUTOFF.
        Parameters
            instance_name_or_id – The name or ID of a server.
        Returns
            Server instance
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.stop_server(instance.id)
        return self._wait_for_server(instance, status='SHUTOFF', wait=60)

    def _shelve_server(self, instance_name_or_id):
        """
        Shelves a server.
        All associated data and resources are kept but anything still in memory is not retained. Policy defaults enable only users with administrative role or the owner of the server to perform this operation. Cloud provides could change this permission though.
        Parameters
            instance_name_or_id – The name or ID of a server.
        Returns
            Server instance
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.shelve_server(instance.id)
        return self._wait_for_server(instance, status='SHELVED_OFFLOADED', wait=60)

    def _unshelve_server(self, instance_name_or_id):
        """
        Unselves or restores a shelved server.
        Policy defaults enable only users with administrative role or the owner of the server to perform this operation. Cloud provides could change this permission though.
        Parameters
            instance_name_or_id – The name or ID of a server.
        Returns
            Server instance
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.unshelve_server(instance.id)
        return self._wait_for_server(instance, status='ACTIVE', wait=60)

    def _lock_server(self, instance_name_or_id):
        """
        Locks a server.
        Parameters
            instance_name_or_id – The name or ID of a server.
        Returns
            Server instance
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.lock_server(instance.id)
        return self._get_server(instance.id)

    def _unlock_server(self, instance_name_or_id):
        """
        Unlocks a locked server.
        Parameters
            instance_name_or_id – The name or ID of a server.
        Returns
            Server instance
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.unlock_server(instance.id)
        return self._get_server(instance.id)

    def _reboot_server(self, instance_name_or_id, reboot_type):
        """
        Reboot a server
        Parameters
            instance_name_or_id – The name or ID of a server.
            reboot_type (str) – The type of reboot to perform. “HARD” and “SOFT” are the current options.
        Returns
            Server instance
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.reboot_server(instance.id, reboot_type)
        if reboot_type is 'soft':
            instance = self._wait_for_server(instance,status='REBOOT', wait=60)
        elif reboot_type is 'hard':
            instance = self._wait_for_server(instance,status='HARD_REBOOT', wait=60)
        return self._wait_for_server(instance, wait=60)

    def _pause_server(self, instance_name_or_id):
        """
        Pauses a server and changes its status to PAUSED.
        Parameters
            instance_name_or_id – The name or ID of a server.
        Returns
            Server instance
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.pause_server(instance.id)
        return self._wait_for_server(instance,status='PAUSED', wait=60)

    def _unpause_server(self, instance_name_or_id):
        """
        Unpauses a paused server and changes its status to ACTIVE.
        Parameters
            instance_name_or_id – The name or ID of a server.
        Returns
            Server instance
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.unpause_server(instance.id)
        return self._wait_for_server(instance, wait=60)

    def _suspend_server(self, instance_name_or_id):
        """
        Suspends a server and changes its status to SUSPENDED.
        Parameters
            instance_name_or_id – The name or ID of a server.
        Returns
            Server instance
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.suspend_server(instance.id)
        return self._wait_for_server(instance,status='SUSPENDED', wait=60)

    def _resume_server(self, instance_name_or_id):
        """
        Resumes a suspended server and changes its status to ACTIVE.
        Parameters
            instance_name_or_id – The name or ID of a server.
        Returns
            Server instance
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.resume_server(instance.id)
        return self._wait_for_server(instance, wait=60)

    def _resize_server(self, instance_name_or_id, flavor_name_or_id):
        """
        Resize a server
        Parameters
            instance_name_or_id – The name or ID of a server.
            flavor_name_or_id – The name or ID of a flavor.
        Returns
            Server instance.
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        flavor = self._find_flavor(flavor_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.resize_server(instance.id, flavor.id)
        instance = self._wait_for_server(instance, status='RESIZE', wait=120)
        return self._wait_for_server(instance, status='VERIFY_RESIZE', wait=300)

    def _confirm_server_resize(self, instance_name_or_id):
        """
        Confirm a server resize
        Parameters
            instance_name_or_id – The name or ID of a server.
        Returns
            Server instance.
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.confirm_server_resize(instance.id)
        return self._wait_for_server(instance, wait=60)

    def _revert_server_resize(self, instance_name_or_id):
        """
        Revert a server resize
        Parameters
            instance_name_or_id – The name or ID of a server.
        Returns
            Server instance.
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.revert_server_resize(instance.id)
        return self._wait_for_server(instance, wait=60)

    def _set_server_metadata(self, instance_name_or_id, **metadata):
        """
        Update metadata for a server
        Parameters
            instance_name_or_id – The name or ID of a server.
            metadata (kwargs) – Key/value pairs to be updated in the server’s metadata. No other metadata is modified by this call. All keys and values are stored as Unicode.
        Returns
            A Server with only the server’s metadata. All keys and values are Unicode text.
        Return type
            Server
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.compute.set_server_metadata(instance.id, **metadata)

    def _delete_server_metadata(self, instance_name_or_id, keys):
        """
        Delete metadata for a server
        Note: This method will do a HTTP DELETE request for every key in keys.
        Parameters
            instance_name_or_id – The name or ID of a server.
            keys – The keys to delete
        Return type
            None
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.delete_server_metadata(instance.id, keys)

    def _get_server_metadata(self, instance_name_or_id):
        """
        Return a dictionary of metadata for a server
        Parameters
            instance_name_or_id – The name or ID of a server.
        Returns
            A Server with only the server’s metadata. All keys and values are Unicode text.
        Return type
            Server
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.compute.get_server_metadata(instance.id)

    def _add_floating_ip_to_server(self, instance_name_or_id, fip, fixed_address=None):
        """
        Adds a floating IP address to a server instance.
        Parameters
            instance_name_or_id – The name or ID of a server.
            fip – The floating IP address to be added to the server.
            fixed_address – The fixed IP address to be associated with the floating IP address. Used when the server is connected to multiple networks.
        Returns
            None
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.add_floating_ip_to_server(instance.id, fip.floating_ip_address)

    def _remove_floating_ip_from_server(self, instance_name_or_id, fip):
        """
        Removes a floating IP address from a server instance.
        Parameters
            instance_name_or_id – The name or ID of a server.
            address – The floating IP address to be disassociated from the server.
        Returns
            None
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.remove_floating_ip_from_server(instance.id, fip.floating_ip_address)

    def _list_server_ips(self, instance_name_or_id, network_label=None):
        """
        Return a generator of server IPs
        Parameters
            instance_name_or_id – The name or ID of a server.
            network_label – The name of a particular network to list IP addresses from.
        Returns
            A generator of ServerIP objects
        Return type
            ServerIP
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.compute.server_ips(instance.id, network_label=network_label)

    def _fetch_server_security_groups(self, instance_name_or_id):
        """
        Fetch security groups with details for a server.
        Parameters
            instance_name_or_id – The name or ID of a server.
        Returns
            updated Server instance
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        return self.os_sdk_conn.compute.fetch_server_security_groups(instance.id)

    def _add_security_group_to_server(self, instance_name_or_id, sg_name_or_id):
        """
        Add a security group to a server
        Parameters
            instance_name_or_id – The name or ID of a server.
            sg_name_or_id – The name or ID of a security group.
        Returns
            None
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        sg = self._find_security_group(sg_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.add_security_group_to_server(instance.id, sg)

    def _remove_security_group_from_server(self, instance_name_or_id, sg_name_or_id):
        """
        Remove a security group from a server
        Parameters
            instance_name_or_id – The name or ID of a server.
            sg_name_or_id – The name or ID of a security group.
        Returns
            None
        """
        instance = self._find_server(instance_name_or_id, ignore_missing=False)
        sg = self._find_security_group(sg_name_or_id, ignore_missing=False)
        self.os_sdk_conn.compute.remove_security_group_from_server(instance.id, sg)
