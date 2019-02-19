%global sha 9d72fe1a501bc609a875eebf7b6274e18600ed70
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
Source1: repositories.yaml
Source2: index.yaml

BuildArch:     noarch

Patch01: 0001-ceilometer-chart-updates.patch
Patch02: 0002-Add-Aodh-Chart.patch
Patch03: 0003-Add-Panko-Chart.patch
Patch04: Remove-stale-Apache2-service-pids-when-a-POD-starts.patch
Patch05: 0005-Add-heat-purge-deleted-cron-job.patch
Patch06: 0006-Enable-cold-migration-in-nova-helm-chart.patch
Patch07: 0007-Glance-chart-add-images-pool-replication.patch
Patch08: 0007-Stein-Remove-ceilometer-upgrade-option.patch
Patch09: 0008-Stein-Update-Cinder-to-include-resource_filters.json.patch
Patch10: 0009-Stein-add-log_config_append-to-neutron-etc.patch
Patch11: 0010-Stein-Nova-console-address-config-optionality.patch
Patch12: 0011-Support-per-host-overrides-of-auto_bridge_add.patch
Patch13: 0012-Nova-chart-Add-ephemeral-pool.patch

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
%patch06 -p1
%patch07 -p1
%patch08 -p1
%patch09 -p1
%patch10 -p1
%patch11 -p1
%patch12 -p1
%patch13 -p1

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

# Stage a local repo index that can be updated by the build
cp %{SOURCE2} %{helm_home}/repository/local/index.yaml

# Stage helm-toolkit in the local repo
cp %{helm_folder}/helm-toolkit-%{toolkit_version}.tgz .

# Host a server for the charts
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

