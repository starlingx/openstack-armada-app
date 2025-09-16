import mock
from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm import helm
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base

from k8sapp_openstack.helm import clients
from k8sapp_openstack.tests import test_plugins


class ClientsHelmTestCase(test_plugins.K8SAppOpenstackAppMixin,
                          base.HelmTestCaseMixin):

    def setUp(self):
        super(ClientsHelmTestCase, self).setUp()
        self.app = dbutils.create_test_app(name=self.app_name)


class ClientsGetOverridesTest(ClientsHelmTestCase,
                              dbbase.ControllerHostTestCase):

    def setUp(self):
        super(ClientsGetOverridesTest, self).setUp()
        self.operator = helm.HelmOperator(self.dbapi)
        self.clients = clients.ClientsHelm(self.operator)

    @mock.patch('k8sapp_openstack.helm.clients.ClientsHelm.'
                '_is_openstack_https_ready', return_value=False)
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_endpoints_identity_overrides',
                return_value='auth')
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_endpoints_host_fqdn_overrides',
                return_value='host_fqdn_override')
    def test_openstack_https_disabled_should_not_contain_manifest(self, *_):
        """
        Validates that the manifest is NOT inserted when the function _is_openstack_https_ready returns false,
        exiting at the first condition of the get_overrides function.
        """
        overrides = self.clients.get_overrides()

        assert 'openstack' in overrides

        assert 'identity' in overrides['openstack']['endpoints']
        assert 'auth' in overrides['openstack']['endpoints']['identity']
        assert 'clients' in overrides['openstack']['endpoints']
        assert 'host_fqdn_override' in overrides['openstack']['endpoints']['clients']

        assert 'manifests' not in overrides['openstack']

    @mock.patch('k8sapp_openstack.helm.clients.ClientsHelm.'
                '_is_openstack_https_ready', return_value=True)
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_endpoints_identity_overrides',
                return_value='auth')
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_endpoints_host_fqdn_overrides',
                return_value='host_fqdn_override')
    def test_openstack_https_enabled_should_contain_manifest(self, *_):
        """
        Validates that the manifest and its values is inserted when the function _is_openstack_https_ready returns true,
        falls into the first condition of the get_overrides function.
        """
        overrides = self.clients.get_overrides()

        assert 'openstack' in overrides

        assert 'manifests' in overrides['openstack']
        assert overrides['openstack']['manifests']['job_bootstrap']
        assert overrides['openstack']['manifests']['certificates']

    @mock.patch('k8sapp_openstack.helm.clients.ClientsHelm.'
                '_is_openstack_https_ready', return_value=True)
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_endpoints_identity_overrides',
                return_value='auth')
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_endpoints_host_fqdn_overrides',
                return_value='host_fqdn_override')
    def test_namespace_is_supported_should_contain_only_namespace_values(self, *_):
        """
        Validates that the namespace passed as a parameter is supported and, if so,
        returns only the values of the namespace object.
        """
        overrides = self.clients.get_overrides(namespace='openstack')

        assert 'openstack' not in overrides

        assert 'endpoints' in overrides
        assert 'identity' in overrides['endpoints']

    @mock.patch('k8sapp_openstack.helm.clients.ClientsHelm.'
                '_is_openstack_https_ready', return_value=True)
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_endpoints_identity_overrides',
                return_value='auth')
    @mock.patch('k8sapp_openstack.helm.openstack.OpenstackBaseHelm._get_endpoints_host_fqdn_overrides',
                return_value='host_fqdn_override')
    def test_namespace_is_not_supported_should_raise_exception(self, *_):
        """
        Validates that if the namespace passed as a parameter is not supported,
        an InvalidHelmNamespace exception is raised.
        """
        try:
            self.clients.get_overrides(namespace='invalid')
        except Exception as e:
            if (isinstance(e, exception.InvalidHelmNamespace)):
                pass


class ClientsGetPerHostOverridesTest(ClientsHelmTestCase,
                                     dbbase.ControllerHostTestCase):
    HOST_1 = 'Host 1'
    HOST_2 = 'Host 2'
    HOST_3 = 'Host 3'
    HOST_4 = 'Host 4'

    def setUp(self):
        super(ClientsGetPerHostOverridesTest, self).setUp()
        self.operator = helm.HelmOperator(self.dbapi)
        self.clients = clients.ClientsHelm(self.operator)

    class DummyHost(object):

        def __init__(self, hostname, invprovision, subfunctions):
            self.hostname = hostname
            self.invprovision = invprovision
            self.subfunctions = subfunctions

    @mock.patch('k8sapp_openstack.helm.clients.ClientsHelm.dbapi')
    def test_host_upgrading_conditions_for_each_personality(self, mock_dbapi):
        """
        Validates that when the host's provision status is UPGRADING,
        no hosts are returned, regardless of the host personality.
        """
        hosts = [
            self.DummyHost(self.HOST_1, constants.UPGRADING, constants.CONTROLLER),
            self.DummyHost(self.HOST_2, constants.UPGRADING, constants.STORAGE),
            self.DummyHost(self.HOST_3, constants.UPGRADING, constants.WORKER),
            self.DummyHost(self.HOST_4, constants.UPGRADING, constants.EDGEWORKER)
        ]
        mock_dbapi.ihost_get_list.return_value = hosts

        per_host_overrides = self.clients._get_per_host_overrides()
        host_name_list = [obj['name'] for obj in per_host_overrides]

        for host_name in [self.HOST_1, self.HOST_2, self.HOST_3, self.HOST_4]:
            assert host_name not in host_name_list

    @mock.patch('k8sapp_openstack.helm.clients.ClientsHelm.dbapi')
    def test_host_provisioning_conditions_for_each_personality(self, mock_dbapi):
        """
        Validates that when the host's provision status is PROVISIONING,
        only hosts with the controller personality are returned.
        """
        hosts = [
            self.DummyHost(self.HOST_1, constants.PROVISIONING, constants.CONTROLLER),
            self.DummyHost(self.HOST_2, constants.PROVISIONING, constants.STORAGE),
            self.DummyHost(self.HOST_3, constants.PROVISIONING, constants.WORKER),
            self.DummyHost(self.HOST_4, constants.PROVISIONING, constants.EDGEWORKER)
        ]
        mock_dbapi.ihost_get_list.return_value = hosts

        per_host_overrides = self.clients._get_per_host_overrides()
        host_name_list = [obj['name'] for obj in per_host_overrides]

        assert self.HOST_1 in host_name_list

        for host_name in [self.HOST_2, self.HOST_3, self.HOST_4]:
            assert host_name not in host_name_list

    @mock.patch('k8sapp_openstack.helm.clients.ClientsHelm.dbapi')
    def test_host_provisioned_conditions_for_each_personality(self, mock_dbapi):
        """
        Validates that when the host's provision status is PROVISIONED,
        only hosts with the controller personality are returned.
        """
        hosts = [
            self.DummyHost(self.HOST_1, constants.PROVISIONED, constants.CONTROLLER),
            self.DummyHost(self.HOST_2, constants.PROVISIONED, constants.STORAGE),
            self.DummyHost(self.HOST_3, constants.PROVISIONED, constants.WORKER),
            self.DummyHost(self.HOST_4, constants.PROVISIONED, constants.EDGEWORKER)
        ]
        mock_dbapi.ihost_get_list.return_value = hosts

        per_host_overrides = self.clients._get_per_host_overrides()
        host_name_list = [obj['name'] for obj in per_host_overrides]

        assert self.HOST_1 in host_name_list

        for host_name in [self.HOST_2, self.HOST_3, self.HOST_4]:
            assert host_name not in host_name_list

    @mock.patch('k8sapp_openstack.helm.clients.ClientsHelm.dbapi')
    def test_host_unprovisioned_conditions_for_each_personality(self, mock_dbapi):
        """
        Validates that when the host's provision status is UNPROVISIONED,
        no hosts are returned, regardless of the host personality.
        """
        hosts = [
            self.DummyHost(self.HOST_1, constants.UNPROVISIONED, constants.CONTROLLER),
            self.DummyHost(self.HOST_2, constants.UNPROVISIONED, constants.STORAGE),
            self.DummyHost(self.HOST_3, constants.UNPROVISIONED, constants.WORKER),
            self.DummyHost(self.HOST_4, constants.UNPROVISIONED, constants.EDGEWORKER)
        ]
        mock_dbapi.ihost_get_list.return_value = hosts

        per_host_overrides = self.clients._get_per_host_overrides()
        host_name_list = [obj['name'] for obj in per_host_overrides]

        for host_name in [self.HOST_1, self.HOST_2, self.HOST_3, self.HOST_4]:
            assert host_name not in host_name_list

    @mock.patch('k8sapp_openstack.helm.clients.ClientsHelm.dbapi')
    def test_controller_host_for_each_provision_stage(self, mock_dbapi):
        """
        Validates that when all hosts have the controller personality,
        only those with the provision status PROVISIONING or PROVISIONED are returned.
        """
        hosts = [
            self.DummyHost(self.HOST_1, constants.UPGRADING, constants.CONTROLLER),
            self.DummyHost(self.HOST_2, constants.PROVISIONING, constants.CONTROLLER),
            self.DummyHost(self.HOST_3, constants.PROVISIONED, constants.CONTROLLER),
            self.DummyHost(self.HOST_4, constants.UNPROVISIONED, constants.CONTROLLER)
        ]
        mock_dbapi.ihost_get_list.return_value = hosts

        per_host_overrides = self.clients._get_per_host_overrides()
        host_name_list = [obj['name'] for obj in per_host_overrides]

        assert self.HOST_2 in host_name_list
        assert self.HOST_3 in host_name_list

        for host_name in [self.HOST_1, self.HOST_4]:
            assert host_name not in host_name_list
