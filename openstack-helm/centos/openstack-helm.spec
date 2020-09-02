%global sha 34a7533b6484a157c8725889d0d68e792e13fc8d
%global helm_folder  /usr/lib/helm
%global toolkit_version 0.1.0
%global helmchart_version 0.1.0
%global _default_patch_flags --no-backup-if-mismatch --prefix=/tmp/junk

Summary: Openstack-Helm charts
Name: openstack-helm
Version: 1.0
Release: %{tis_patch_ver}%{?_tis_dist}
License: Apache-2.0
Group: base
Packager: Wind River <info@windriver.com>
URL: https://github.com/openstack/openstack-helm

Source0: %{name}-%{sha}.tar.gz
Source1: repositories.yaml
Source2: index.yaml

BuildArch:     noarch

Patch01: 0001-Ceilometer-chart-add-the-ability-to-publish-events-t.patch
Patch02: 0002-Remove-stale-Apache2-service-pids-when-a-POD-starts.patch
Patch03: 0003-Nova-console-ip-address-search-optionality.patch
Patch04: 0004-Nova-chart-Support-ephemeral-pool-creation.patch
Patch05: 0005-Nova-Add-support-for-disabling-Readiness-Liveness-pr.patch
Patch06: 0006-Support-ingress-creation-for-keystone-admin-endpoint.patch
Patch07: 0007-Allow-more-generic-overrides-for-placeme.patch
Patch08: 0008-Allow-set-public-endpoint-url-for-keystone-endpoints.patch

BuildRequires: helm
BuildRequires: openstack-helm-infra
BuildRequires: chartmuseum
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
%patch06 -p1
%patch07 -p1
%patch08 -p1

%build
# Stage helm-toolkit in the local repo
cp %{helm_folder}/helm-toolkit-%{toolkit_version}.tgz .

# Host a server for the charts
chartmuseum --debug --port=8879 --context-path='/charts' --storage="local" --storage-local-rootdir="." &
sleep 2
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
make placement

# terminate helm server (the last backgrounded task)
kill %1

# Remove the helm-toolkit tarball
rm helm-toolkit-%{toolkit_version}.tgz

%install
# helm_folder is created by openstack-helm-infra
install -d -m 755 ${RPM_BUILD_ROOT}%{helm_folder}
install -p -D -m 755 *.tgz ${RPM_BUILD_ROOT}%{helm_folder}

%files
#helm_folder is owned by openstack-helm-infra
%defattr(-,root,root,-)
%{helm_folder}/*

