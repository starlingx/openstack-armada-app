%global sha 8351fdd0f1228717342c2accc96977b0cdc36dc3
%global helm_folder  /usr/lib/helm

Summary: Openstack-Helm-Infra charts
Name: openstack-helm-infra
Version: 1.0
Release: %{tis_patch_ver}%{?_tis_dist}
License: Apache-2.0
Group: base
Packager: Wind River <info@windriver.com>
URL: https://github.com/openstack/openstack-helm-infra

Source0: %{name}-%{sha}.tar.gz
Source1: repositories.yaml

BuildArch:     noarch

Patch01: 0001-Add-imagePullSecrets-in-service-account.patch
Patch03: 0003-Partial-revert-of-31e3469d28858d7b5eb6355e88b6f49fd6.patch
Patch04: 0004-Fix-pod-restarts-on-all-workers-when-worker-added-re.patch
Patch05: 0005-Add-io_thread_pool-for-rabbitmq.patch
Patch06: 0006-Enable-override-of-rabbitmq-probe-parameters.patch
Patch09: 0009-Enable-override-of-mariadb-server-probe-parameters.patch
Patch11: 0011-Add-mariadb-database-config-override-to-support-ipv6.patch
Patch12: 0012-enable-Values.conf.database.config_override-for-mari.patch
Patch13: 0013-Allow-set-public-endpoint-url-for-all-openstack-types.patch
Patch16: 0016-Disabling-helm3_hooks.patch
Patch17: 0017-Enable-taint-toleration-for-Openstack-services.patch
Patch18: 0018-Add-GaleraDB-Secure-Replica-Traffic.patch
Patch19: 0019-Add-force_boot-command-to-rabbit-start-template.patch
Patch20: 0020-Fix-tls-in-openstack-helm-infra.patch
Patch21: 0021-Remove-mariadb-tls.patch
Patch22: 0022-Remove-rabbitmq-tls.patch

BuildRequires: helm
BuildRequires: chartmuseum

%description
Openstack Helm Infra charts

%prep
%setup -n openstack-helm-infra
%patch01 -p1
%patch03 -p1
%patch04 -p1
%patch05 -p1
%patch06 -p1
%patch09 -p1
%patch11 -p1
%patch12 -p1
%patch13 -p1
%patch16 -p1
%patch17 -p1
%patch18 -p1
%patch19 -p1
%patch20 -p1
%patch21 -p1
%patch22 -p1

%build
# Host a server for the charts
chartmuseum --debug --port=8879 --context-path='/charts' --storage="local" --storage-local-rootdir="." &
sleep 2
helm repo add local http://localhost:8879/charts

# Make the charts. These produce tgz files
make helm-toolkit
make gnocchi
make ingress
make libvirt
make mariadb
make memcached
make openvswitch
make rabbitmq
make ceph-rgw

# terminate helm server (the last backgrounded task)
kill %1

%install
install -d -m 755 ${RPM_BUILD_ROOT}%{helm_folder}
install -p -D -m 755 *.tgz ${RPM_BUILD_ROOT}%{helm_folder}

%files
%dir %attr(0755,root,root) %{helm_folder}
%defattr(-,root,root,-)
%{helm_folder}/*
