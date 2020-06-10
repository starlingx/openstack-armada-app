%global sha c9d6676bf9a5aceb311dc31dadd07cba6a3d6392
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

Patch01: 0001-Allow-multiple-containers-per-daemonset-pod.patch
Patch02: 0002-Add-imagePullSecrets-in-service-account.patch
Patch03: 0003-Set-Min-NGINX-handles.patch
Patch04: 0004-Partial-revert-of-31e3469d28858d7b5eb6355e88b6f49fd6.patch
Patch05: 0005-Add-TLS-support-for-Gnocchi-public-endpoint.patch
Patch06: 0006-Fix-pod-restarts-on-all-workers-when-worker-added-re.patch
Patch07: 0007-Add-io_thread_pool-for-rabbitmq.patch
Patch08: 0008-Enable-override-of-rabbitmq-probe-parameters.patch
Patch09: 0009-Fix-ipv6-address-issue-causing-mariadb-ingress-not-ready.patch
Patch10: 0010-Fix-rabbitmq-could-not-bind-port-to-ipv6-address-iss.patch
Patch11: 0011-Enable-override-of-mariadb-server-probe-parameters.patch
Patch12: 0012-Mariadb-use-utf8_general_ci-collation-as-default.patch

BuildRequires: helm

%description
Openstack Helm Infra charts

%prep
%setup -n openstack-helm-infra
%patch01 -p1
%patch02 -p1
%patch03 -p1
%patch04 -p1
%patch05 -p1
%patch06 -p1
%patch07 -p1
%patch08 -p1
%patch09 -p1
%patch10 -p1
%patch11 -p1
%patch12 -p1

%build
# initialize helm and build the toolkit
# helm init --client-only does not work if there is no networking
# The following commands do essentially the same as: helm init
%define helm_home %{getenv:HOME}/.helm
mkdir %{helm_home}
mkdir %{helm_home}/repository
mkdir %{helm_home}/repository/cache
mkdir %{helm_home}/repository/local
mkdir %{helm_home}/plugins
mkdir %{helm_home}/starters
mkdir %{helm_home}/cache
mkdir %{helm_home}/cache/archive

# Stage a repository file that only has a local repo
cp %{SOURCE1} %{helm_home}/repository/repositories.yaml

# Host a server for the charts
helm serve /tmp/charts --address localhost:8879 --url http://localhost:8879/charts &
helm repo rm local
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
