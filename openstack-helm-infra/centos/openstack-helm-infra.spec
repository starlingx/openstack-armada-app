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
Patch14: 0014-Add-tolerations-to-rabbitmq-chart.patch
Patch15: 0015-Add-tolerations-to-mariadb-chart.patch
Patch16: 0016-Disabling-helm3_hooks.patch

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
%patch14 -p1
%patch15 -p1
%patch16 -p1

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
