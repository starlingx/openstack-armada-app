%global sha 5d356f9265b337b75f605dee839faa8cd0ed3ab2
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

BuildArch:     noarch

Patch01: 0001-gnocchi-remove-gnocchi-upgrade-option-and-set-coordi.patch

BuildRequires: helm

%description
Openstack Helm Infra charts

%prep
%setup -n openstack-helm-infra
%patch01 -p1

%build
# initialize helm and build the toolkit
helm init --client-only
make helm-toolkit

# Host a server for the charts
helm serve /tmp/charts --address localhost:8879 --url http://localhost:8879/charts &
helm repo rm local
helm repo add local http://localhost:8879/charts

# Make the charts. These produce tgz files
make gnocchi
make ingress
make libvirt
make mariadb
make memcached
make openvswitch
make rabbitmq

%install
install -d -m 755 ${RPM_BUILD_ROOT}%{helm_folder}
install -p -D -m 755 *.tgz ${RPM_BUILD_ROOT}%{helm_folder}

%files
%dir %attr(0755,root,root) %{helm_folder}
%defattr(-,root,root,-)
%{helm_folder}/*
