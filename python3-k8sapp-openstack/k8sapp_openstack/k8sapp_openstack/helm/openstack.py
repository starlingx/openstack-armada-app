#
# Copyright (c) 2019-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import base64
# Adding a try-import as six 1.12.0 doesn't have this move and we are pinned
# at the stein upper-requirements on tox.ini
try:
    from collections import abc as collections_abc
except ImportError:  # Python 2.7-3.2
    import collections as collections_abc

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from eventlet.green import subprocess
import keyring
from oslo_log import log
from oslo_serialization import jsonutils
from sqlalchemy.orm.exc import NoResultFound
from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import kubernetes
from sysinv.common import utils
from sysinv.common.storage_backend_conf import K8RbdProvisioner
from sysinv.helm import base
from sysinv.helm import common

from k8sapp_openstack import utils as app_utils
from k8sapp_openstack.common import constants as app_constants


LOG = log.getLogger(__name__)


class BaseHelm(base.BaseHelm):
    """Class to encapsulate Openstack related service operations for helm"""

    SUPPORTED_NAMESPACES = \
        base.BaseHelm.SUPPORTED_NAMESPACES + [common.HELM_NS_OPENSTACK]
    SUPPORTED_APP_NAMESPACES = {
        app_constants.HELM_APP_OPENSTACK:
            base.BaseHelm.SUPPORTED_NAMESPACES + [common.HELM_NS_OPENSTACK]
    }


class FluxCDBaseHelm(base.FluxCDBaseHelm):
    """Class to encapsulate Openstack related service operations for helm"""

    SUPPORTED_NAMESPACES = \
        base.BaseHelm.SUPPORTED_NAMESPACES + [common.HELM_NS_OPENSTACK]
    SUPPORTED_APP_NAMESPACES = {
        app_constants.HELM_APP_OPENSTACK:
            base.BaseHelm.SUPPORTED_NAMESPACES + [common.HELM_NS_OPENSTACK]
    }


class OpenstackBaseHelm(FluxCDBaseHelm):
    """Class to encapsulate Openstack service operations for helm"""

    SYSTEM_CONTROLLER_SERVICES = [
        app_constants.HELM_CHART_KEYSTONE_API_PROXY,
    ]

    def get_namespaces(self):
        return self.SUPPORTED_NAMESPACES

    def _get_service_config(self, service):
        configs = self.context.setdefault('_service_configs', {})
        if service not in configs:
            configs[service] = self._get_service(service)
        return configs[service]

    def _get_service_parameters(self, service=None):
        service_parameters = []
        if self.dbapi is None:
            return service_parameters
        try:
            service_parameters = self.dbapi.service_parameter_get_all(
                service=service)
        # the service parameter has not been added
        except NoResultFound:
            pass
        return service_parameters

    def _get_service_parameter_configs(self, service):
        configs = self.context.setdefault('_service_params', {})
        if service not in configs:
            params = self._get_service_parameters(service)
            if params:
                configs[service] = params
            else:
                return None
        return configs[service]

    @staticmethod
    def _service_parameter_lookup_one(service_parameters, section, name,
                                      default):
        for param in service_parameters:
            if param['section'] == section and param['name'] == name:
                return param['value']
        return default

    def _get_chart_operator(self, chart_name):
        try:
            return self._operator.get_chart_operator(chart_name)
        except AttributeError:
            return self._operator.chart_operators[chart_name]

    def _get_admin_user_name(self):
        keystone_operator = self._get_chart_operator(app_constants.HELM_CHART_KEYSTONE)
        return keystone_operator.get_admin_user_name()

    def _get_admin_project_name(self):
        keystone_operator = self._get_chart_operator(app_constants.HELM_CHART_KEYSTONE)
        return keystone_operator.get_admin_project_name()

    def _get_admin_project_domain(self):
        keystone_operator = self._get_chart_operator(app_constants.HELM_CHART_KEYSTONE)
        return keystone_operator.get_admin_project_domain()

    def _get_admin_user_domain(self):
        keystone_operator = self._get_chart_operator(app_constants.HELM_CHART_KEYSTONE)
        return keystone_operator.get_admin_user_domain()

    def _get_identity_password(self, service, user):
        passwords = self.context.setdefault('_service_passwords', {})
        if service not in passwords:
            passwords[service] = {}

        if user not in passwords[service]:
            passwords[service][user] = self._get_keyring_password(service, user)

        return passwords[service][user]

    def _get_database_username(self, service):
        return 'admin-%s' % service

    def _get_keyring_password(self, service, user, pw_format=None):
        password = keyring.get_password(service, user)
        if not password:
            if pw_format == common.PASSWORD_FORMAT_CEPH:
                try:
                    cmd = ['ceph-authtool', '--gen-print-key']
                    # pylint is showing a false positive for this subprocess line.
                    # supressing..
                    password = subprocess.check_output(cmd).strip()  # pylint: disable=E1102
                    # TODO: Remove it when Debian is default for
                    # at least two STX releases (prob. ~ stx/9.0)
                    # Python Duck Typing to ensure compatibility with
                    # both Python 2 (CentOS)  and Python 3 (Debian)
                    if hasattr(password, "decode"):
                        password = password.decode()
                except subprocess.CalledProcessError:
                    raise exception.SysinvException(
                        'Failed to generate ceph key')
            else:
                password = self._generate_random_password()
            keyring.set_password(service, user, password)
        # get_password() returns in unicode format, which leads to YAML
        # that Armada doesn't like.  Converting to UTF-8 is safe because
        # we generated the password originally.
        return password.encode('utf8', 'strict')

    def _get_service_region_name(self, service):
        if self._region_config():
            service_config = self._get_service_config(service)
            if (service_config is not None and
                    service_config.region_name is not None):
                return service_config.region_name.encode('utf8', 'strict')

        return self._region_name()

    def _get_configured_service_name(self, service, version=None):
        if self._region_config():
            service_config = self._get_service_config(service)
            if service_config is not None:
                name = 'service_name'
                if version is not None:
                    name = version + '_' + name
                service_name = service_config.capabilities.get(name)
                if service_name is not None:
                    return service_name
        elif version is not None:
            return service + version
        else:
            return service

    def _get_configured_service_type(self, service, version=None):
        if self._region_config():
            service_config = self._get_service_config(service)
            if service_config is not None:
                stype = 'service_type'
                if version is not None:
                    stype = version + '_' + stype
                return service_config.capabilities.get(stype)
        return None

    def _get_or_generate_password(self, chart, namespace, field):
        # Get password from the db for the specified chart overrides
        if not self.dbapi:
            return None

        try:
            app = utils.find_openstack_app(self.dbapi)
            override = self.dbapi.helm_override_get(app_id=app.id,
                                                    name=chart,
                                                    namespace=namespace)
        except exception.HelmOverrideNotFound:
            # Override for this chart not found, so create one
            try:
                values = {
                    'name': chart,
                    'namespace': namespace,
                    'app_id': app.id,
                }
                override = self.dbapi.helm_override_create(values=values)
            except Exception as e:
                LOG.exception(e)
                return None

        password = override.system_overrides.get(field, None)
        if password:
            return password.encode('utf8', 'strict')

        # The password is not present, dump from inactive app if available,
        # otherwise generate one and store it to the override
        try:
            openstack_app = utils.find_openstack_app(self.dbapi)
            inactive_apps = self.dbapi.kube_app_get_inactive(openstack_app.name)
            app_override = self.dbapi.helm_override_get(app_id=inactive_apps[0].id,
                                                        name=chart,
                                                        namespace=namespace)
            password = app_override.system_overrides.get(field, None)
        except (IndexError, exception.HelmOverrideNotFound):
            # No inactive app or no overrides for the inactive app
            pass

        if not password:
            password = self._generate_random_password()
        values = {'system_overrides': override.system_overrides}
        values['system_overrides'].update({
            field: password,
        })
        try:
            self.dbapi.helm_override_update(
                app_id=app.id, name=chart, namespace=namespace, values=values)
        except Exception as e:
            LOG.exception(e)

        return password.encode('utf8', 'strict')

    def _update_overrides(self, dictionary, updates):
        for key, value in updates.items():
            if isinstance(value, collections_abc.Mapping):
                dictionary[key] = self._update_overrides(
                    dictionary.get(key, {}),
                    value
                )
            else:
                dictionary[key] = value
        return dictionary

    def _update_image_tag_overrides(self,
                                    overrides: dict,
                                    images: list,
                                    tag: str):
        """Overrides the images.tags for a given list of images

        Args:
            overrides (dict): base overrides to be updated
            images (list): list of images to be updated, as defined in the
                           images.tags keys of the chart values
            tags (str): new image to override the values of the the given
                        images.tags. Must be in the standard <repo:tag> format
        """
        tags_overrides = dict(zip(images, [tag] * len(images)))
        images_overrides = {
            'images': {
                'tags': tags_overrides
            }
        }
        overrides_updated = self._update_overrides(overrides, images_overrides)
        return overrides_updated

    def _get_endpoints_identity_overrides(self, service_name, users,
                                          service_users=()):
        # Returns overrides for admin and individual users
        overrides = {}
        overrides.update(self._get_common_users_overrides(service_name))

        for user in users + list(service_users):
            overrides.update({
                user: {
                    'region_name': self._get_service_region_name(service_name),
                    'password': self._get_or_generate_password(
                        # Service user passwords already exist in other chart overrides
                        # Notice the use of username as 'chart' on
                        # self._get_or_generate_password for SERVICE_USERS
                        chart=user if user in service_users else service_name,
                        namespace=common.HELM_NS_OPENSTACK,
                        field=user)
                }
            })

            if self._is_openstack_https_ready():
                overrides = self._update_overrides(overrides, {
                    user: {
                        'cacert': self.get_ca_file()
                    }
                })

        return overrides

    def _get_endpoint_public_tls(self, service_name):
        overrides = {}

        certificates = app_utils.get_openstack_certificate_values(service_name)
        cert_file = certificates[app_constants.OPENSTACK_CERT]
        cert_key_file = certificates[app_constants.OPENSTACK_CERT_KEY]
        cert_ca_file = certificates[app_constants.OPENSTACK_CERT_CA]

        if (cert_file and cert_key_file):
            overrides.update({
                'crt': cert_file,
                'key': cert_key_file,
            })
        if cert_ca_file:
            overrides.update({'ca': cert_ca_file})
        return overrides

    def _get_endpoints_host_fqdn_overrides(self, service_name):
        overrides = {'public': {}}
        endpoint_domain = self._get_service_parameter(
            constants.SERVICE_TYPE_OPENSTACK,
            constants.SERVICE_PARAM_SECTION_OPENSTACK_HELM,
            constants.SERVICE_PARAM_NAME_ENDPOINT_DOMAIN)
        if endpoint_domain is not None:
            # Define endpoint domain based on pattern
            fqdn_pattern = app_utils.get_services_fqdn_pattern()
            service_endpoint = fqdn_pattern.format(
                    service_name=service_name,
                    endpoint_domain=str(endpoint_domain.value),
            ).lower()
            overrides['public'].update({'host': service_endpoint})

        if self._is_openstack_https_ready():
            tls_overrides = self._get_endpoint_public_tls(service_name)
            if tls_overrides:
                overrides['public'].update({
                    'tls': tls_overrides
                })
        return overrides

    def _get_endpoints_hosts_admin_overrides(self, service_name):
        return {}

    def _get_network_api_ingress_overrides(self):
        return {'admin': False}

    def _get_endpoints_scheme_public_overrides(self):
        overrides = {}
        if self._is_openstack_https_ready():
            overrides = {
                'public': 'https'
            }
        return overrides

    def _get_endpoints_port_api_public_overrides(self):
        overrides = {}
        if self._is_openstack_https_ready():
            overrides = {
                'api': {
                    'public': 443
                }
            }
        return overrides

    def _get_endpoints_oslo_db_overrides(self, service_name, users):
        overrides = {
            'admin': {
                'password': self._get_common_password('admin_db'),
            }
        }

        for user in users:
            overrides.update({
                user: {
                    'password': self._get_or_generate_password(
                        service_name, common.HELM_NS_OPENSTACK,
                        user + '_db'),
                }
            })

        return overrides

    def _get_endpoints_oslo_messaging_overrides(self, service_name, users):
        overrides = {
            'admin': {
                'username': 'rabbitmq-admin',
                'password': self._get_common_password('rabbitmq-admin')
            }
        }

        for user in users:
            overrides.update({
                user: {
                    'username': user + '-rabbitmq-user',
                    'password': self._get_or_generate_password(
                        service_name, common.HELM_NS_OPENSTACK,
                        user + '_rabbit')
                }
            })

        return overrides

    def _get_common_password(self, name):
        # Admin passwords are stored on keystone's helm override entry
        return self._get_or_generate_password(
            'keystone', common.HELM_NS_OPENSTACK, name)

    def _get_common_users_overrides(self, service):
        overrides = {}
        for user in common.USERS:
            if user == common.USER_ADMIN:
                o_user = self._get_admin_user_name()
                o_service = common.SERVICE_ADMIN
            elif user == common.USER_STX_ADMIN:
                o_user = user
                o_service = common.SERVICE_ADMIN
            else:
                o_user = user
                o_service = service

            overrides.update({
                user: {
                    'region_name': self._get_service_region_name(service),
                    'username': o_user,
                    'password': self._get_identity_password(o_service, o_user)
                }
            })

            if self._is_openstack_https_ready():
                overrides = self._update_overrides(overrides, {
                    user: {
                        'cacert': self.get_ca_file()
                    }
                })

        return overrides

    def _get_ceph_password(self, service, user):
        passwords = self.context.setdefault('_ceph_passwords', {})
        if service not in passwords:
            passwords[service] = {}

        if user not in passwords[service]:
            passwords[service][user] = self._get_keyring_password(
                service, user, pw_format=common.PASSWORD_FORMAT_CEPH)

        return passwords[service][user]

    def _get_or_generate_ssh_keys(self, chart, namespace):
        try:
            app = utils.find_openstack_app(self.dbapi)
            override = self.dbapi.helm_override_get(app_id=app.id,
                                                    name=chart,
                                                    namespace=namespace)
        except exception.HelmOverrideNotFound:
            # Override for this chart not found, so create one
            values = {
                'name': chart,
                'namespace': namespace,
                'app_id': app.id
            }
            override = self.dbapi.helm_override_create(values=values)

        privatekey = override.system_overrides.get('privatekey', None)
        publickey = override.system_overrides.get('publickey', None)

        if privatekey and publickey:
            return str(privatekey), str(publickey)

        # ssh keys are not set, dump from inactive app if available,
        # otherwise generate them and store in overrides
        newprivatekey = None
        newpublickey = None
        try:
            openstack_app = utils.find_openstack_app(self.dbapi)
            inactive_apps = self.dbapi.kube_app_get_inactive(openstack_app.name)
            app_override = self.dbapi.helm_override_get(app_id=inactive_apps[0].id,
                                                        name=chart,
                                                        namespace=namespace)
            newprivatekey = str(app_override.system_overrides.get('privatekey', None))
            newpublickey = str(app_override.system_overrides.get('publickey', None))
        except (IndexError, exception.HelmOverrideNotFound):
            # No inactive app or no overrides for the inactive app
            pass

        if not newprivatekey or not newpublickey:
            private_key = rsa.generate_private_key(public_exponent=65537,
                                                   key_size=2048,
                                                   backend=default_backend())
            public_key = private_key.public_key()
            newprivatekey = str(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()).decode('utf-8'))
            newpublickey = str(public_key.public_bytes(
                serialization.Encoding.OpenSSH,
                serialization.PublicFormat.OpenSSH).decode('utf-8'))
        values = {'system_overrides': override.system_overrides}
        values['system_overrides'].update({'privatekey': newprivatekey,
                                           'publickey': newpublickey})
        self.dbapi.helm_override_update(
            app_id=app.id, name=chart, namespace=namespace, values=values)

        return newprivatekey, newpublickey

    def _oslo_multistring_override(self, name=None, values=None):
        """
        Generate helm multistring dictionary override for specified option
        name with multiple values.

        This generates oslo_config.MultiStringOpt() compatible config
        with multiple input values. This routine JSON encodes each value for
        complex types (eg, dict, list, set).

        Return a multistring type formatted dictionary override.
        """
        override = None
        if name is None or not values:
            return override

        mvalues = []
        for value in values:
            if isinstance(value, (dict, list, set)):
                mvalues.append(jsonutils.dumps(value))
            else:
                mvalues.append(value)

        override = {
            name: {'type': 'multistring',
                   'values': mvalues,
                   }
        }
        return override

    def _get_public_protocol(self):
        return 'https' if self._is_openstack_https_ready() else 'http'

    def _get_service_default_dns_name(self, service):
        return "{}.{}.svc.{}".format(service, common.HELM_NS_OPENSTACK,
                                     constants.DEFAULT_DNS_SERVICE_DOMAIN)

    def _get_mount_uefi_overrides(self):

        # This path depends on OVMF packages and for starlingx
        # we don't care about aarch64.
        # This path will be used by nova-compute and libvirt pods.
        uefi_loader_path = ["/usr/share/OVMF", "/usr/share/qemu"]

        uefi_config = {
            'volumes': [
                {
                    'name': 'ovmf',
                    'hostPath': {
                        'path': uefi_loader_path[0]
                    }
                },
                {
                    'name': 'qemu-ovmf',
                    'hostPath': {
                        'path': uefi_loader_path[1]
                    }
                }
            ],
            'volumeMounts': [
                {
                    'name': 'ovmf',
                    'mountPath': uefi_loader_path[0]
                },
                {
                    'name': 'qemu-ovmf',
                    'mountPath': uefi_loader_path[1]
                }
            ]
        }
        return uefi_config

    def _get_ceph_client_overrides(self):
        self._rook_ceph, _ = app_utils.is_ceph_backend_available(
                ceph_type=constants.SB_TYPE_CEPH_ROOK)

        if self._rook_ceph:
            return {
                'user_secret_name': constants.K8S_RBD_PROV_ADMIN_SECRET_NAME,
            }
        # A secret is required by the chart for ceph client access. Use the
        # secret for the kube-rbd pool associated with the primary ceph tier
        return {
            'user_secret_name':
            K8RbdProvisioner.get_user_secret_name({
                'name': constants.SB_DEFAULT_NAMES[constants.SB_TYPE_CEPH]})
        }

    def _get_interface_datanets(self):
        """
        Builds a dictionary of interface datanetworks indexed by interface id
        """
        ifdatanets = {}
        db_ifdatanets = self.dbapi.interface_datanetwork_get_all()
        for ifdatanet in db_ifdatanets:
            ifdatanets.setdefault(ifdatanet.interface_id, []).append(ifdatanet)
        return ifdatanets

    def _get_host_interfaces(self, sort_key=None):
        """
        Builds a dictionary of interfaces indexed by host id
        """
        interfaces = {}
        db_interfaces = self.dbapi.iinterface_get_list()
        if sort_key:
            db_interfaces = sorted(db_interfaces, key=sort_key)

        for iface in db_interfaces:
            interfaces.setdefault(iface.forihostid, []).append(iface)
        return interfaces

    def _get_interface_networks(self):
        """
        Builds a dictionary of interface networks indexed by interface id
        """
        interface_networks = {}

        db_interface_networks = self.dbapi.interface_network_get_all()
        for iface_net in db_interface_networks:
            interface_networks.setdefault(iface_net.interface_id, []).append(iface_net)
        return interface_networks

    def _get_interface_network_query(self, interface_id, network_id):
        """
        Return the interface network of the supplied interface id and network id
        """
        interface_networks_by_ifaceid = self._get_interface_networks()
        for iface_net in interface_networks_by_ifaceid.get(interface_id, []):
            if iface_net.interface_id == interface_id and iface_net.network_id == network_id:
                return iface_net

        raise exception.InterfaceNetworkNotFoundByHostInterfaceNetwork(
            interface_id=interface_id, network_id=network_id)

    def _get_cluster_host_iface(self, host, cluster_host_net_id):
        """
        Returns the host cluster interface.
        """
        cluster_host_iface = None
        interfaces_by_hostid = self._get_host_interfaces()
        for iface in interfaces_by_hostid.get(host.id, []):
            try:
                self._get_interface_network_query(iface.id, cluster_host_net_id)
                cluster_host_iface = iface
            except exception.InterfaceNetworkNotFoundByHostInterfaceNetwork:
                LOG.debug("Host: {} Interface: {} is not "
                          "a cluster-host interface".format(host.id, iface))

        LOG.debug("Host: {} Interface: {}".format(host.id, cluster_host_iface))
        return cluster_host_iface

    def _get_cluster_host_ip(self, host, addresses_by_hostid):
        """
        Returns the host cluster IP.
        """
        cluster_host_network = self.dbapi.network_get_by_type(
            constants.NETWORK_TYPE_CLUSTER_HOST)

        cluster_host_iface = self._get_cluster_host_iface(
            host, cluster_host_network.id)
        if cluster_host_iface is None:
            LOG.info("None cluster-host interface "
                     "found for Host: {}".format(host.id))
            return

        cluster_host_ip = None

        for addr in addresses_by_hostid.get(host.id, []):
            if addr.interface_id == cluster_host_iface.id:
                cluster_host_ip = addr.address

        LOG.debug("Host: {} Host IP: {}".format(host.id, cluster_host_ip))
        return cluster_host_ip

    def _get_host_labels(self):
        """
        Builds a dictionary of labels indexed by host id
        """
        labels = {}
        db_labels = self.dbapi.label_get_all()
        for label in db_labels:
            labels.setdefault(label.host_id, []).append(label)
        return labels

    def _get_host_addresses(self):
        """
        Builds a dictionary of addresses indexed by host id
        """
        addresses = {}
        db_addresses = self.dbapi.addresses_get_all()
        db_interfaces = self.dbapi.iinterface_get_list()
        for addr in db_addresses:
            for iface in db_interfaces:
                if iface.id == addr.interface_id:
                    addresses.setdefault(iface.forihostid, []).append(addr)
                    break
        return addresses

    def execute_kustomize_updates(self, operator):
        """
        Update the elements of FluxCD kustomize manifests.

        This allows a helm chart plugin to use the FluxCDKustomizeOperator to
        make dynamic structural changes to the application manifest based on the
        current conditions in the platform

        Changes currenty include updates to the top level kustomize manifest to
        disable helm releases.

        :param operator: an instance of the FluxCDKustomizeOperator
        """
        if not self._is_enabled(operator.APP, self.CHART,
                                common.HELM_NS_OPENSTACK):
            operator.helm_release_resource_delete(self.HELM_RELEASE)

    def _is_enabled(self, app_name, chart_name, namespace):
        """
        Check if the chart is enable at a system level

        :param app_name: Application name
        :param chart_name: Chart supplied with the application
        :param namespace: Namespace where the chart will be executed

        Returns true by default if an exception occurs as most charts are
        enabled.
        """
        return super(OpenstackBaseHelm, self)._is_enabled(
            app_name, chart_name, namespace)

    def _is_rook_ceph(self):
        # TODO: this function can be completely replaced by the app utils
        # function in the future. For now, it will be left here for backward
        # compatibility, reducing the code changes initially required for rook
        # ceph integration.
        self._rook_ceph, _ = app_utils.is_ceph_backend_available(
                ceph_type=constants.SB_TYPE_CEPH_ROOK)

        return self._rook_ceph

    def get_vswitch_label_combinations(self) -> list:
        """
        Get the available vswitch label combinations for this chart

        Returns:
            list: The collection containing the available vswitch label combinations
        """
        return app_constants.VSWITCH_ALLOWED_COMBINATIONS

    def is_openvswitch_enabled(self) -> bool:
        """
        Check if Openvswitch is enabled

        Returns:
            bool: True if Openvswitch is enabled; False otherwise
        """
        return app_utils.is_openvswitch_enabled(self.get_vswitch_label_combinations())

    def is_openvswitch_dpdk_enabled(self) -> bool:
        """
        Check if Openvswitch-DPDK is enabled

        Returns:
            bool: True if Openvswitch-DPDK is enabled; False otherwise
        """
        return app_utils.is_openvswitch_dpdk_enabled(self.get_vswitch_label_combinations())

    def _get_rook_ceph_admin_keyring(self):
        try:
            kube = kubernetes.KubeOperator()
            keyring = kube.kube_get_secret(constants.K8S_RBD_PROV_ADMIN_SECRET_NAME,
                 app_constants.HELM_NS_ROOK_CEPH)
            return base64.b64decode(keyring.data['key']).decode('utf-8')
        except Exception:
            pass

        return 'null'

    def _is_openstack_https_ready(self, service_name=None):
        """
        Check if OpenStack is ready for HTTPS

        Returns true if the openstack certificate file is present.
        """
        if not service_name:
            # Default to clients service
            service_name = app_constants.HELM_CHART_CLIENTS
        return app_utils.is_openstack_https_ready()

    @staticmethod
    def get_ca_file():
        # This function returns the path for the CA cert file INSIDE the container,
        # no on the host machine. If you're changing this, be mindful of changing
        # the same path in the helm-toolkit.
        return '/etc/ssl/certs/openstack-helm.crt'

    def _enable_certificates(self, overrides):
        overrides = self._update_overrides(overrides, {
            'manifests': {
                'certificates': True
            }
        })
        return overrides
