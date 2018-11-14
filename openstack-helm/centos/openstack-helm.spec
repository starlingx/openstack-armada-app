%global sha add7a9bc1175f6fafa8ea2918bc1d62209aaf243
%global helm_folder  /usr/lib/helm
%global toolkit_version 0.1.0
%global helmchart_version 0.1.0

Summary: Openstack-Helm charts
Name: openstack-helm
Version: 1.0
Release: %{tis_patch_ver}%{?_tis_dist}
License: Apache-2.0
Group: base
Packager: Wind River <info@windriver.com>
URL: https://github.com/openstack/openstack-helm

Source0: %{name}-%{sha}.tar.gz

BuildArch:     noarch

Patch01: 0001-Revert-Neutron-TaaS-support-as-L2-Extension.patch
Patch02: 0002-Revert-Openstack-Use-k8s-secret-to-store-config.patch
Patch03: 0003-ceilometer-chart-updates.patch
Patch04: 0004-Add-Aodh-Chart.patch
Patch05: 0005-Add-Panko-Chart.patch

BuildRequires: helm
BuildRequires: openstack-helm-infra
Requires: openstack-helm-infra

%description
Openstack Helm charts

%prep
%setup -n openstack-helm
%patch01 -p1
%patch02 -p1
%patch03 -p1
%patch04 -p1
%patch05 -p1

%build
# initialize helm and stage the toolkit
helm init --client-only
# Host a server for the charts
cp  %{helm_folder}/helm-toolkit-%{toolkit_version}.tgz .
helm serve --repo-path . &
helm repo rm local
helm repo add local http://localhost:8879/charts

# Make the charts. These produce a tgz file
make aodh
make barbican
make ceilometer
make cinder
make glance
make heat
make horizon
make ironic
make keystone
make magnum
make neutron
make nova
make panko

# Remove the helm-toolkit tarball
rm  helm-toolkit-%{toolkit_version}.tgz

%install
# helm_folder is created by openstack-helm-infra
install -d -m 755 ${RPM_BUILD_ROOT}%{helm_folder}
install -p -D -m 755 *.tgz ${RPM_BUILD_ROOT}%{helm_folder}

%files
#helm_folder is owned by openstack-helm-infra
%defattr(-,root,root,-)
%{helm_folder}/*

