%global sha 7803000a545687ec40b0ddc41d46a6b377dea45f
%global helm_folder  /usr/lib/helm
%global toolkit_version 0.2.19
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

Patch01: 0001-Remove-stale-Apache2-service-pids-when-a-POD-starts.patch
Patch02: 0002-Nova-console-ip-address-search-optionality.patch
Patch03: 0003-Nova-chart-Support-ephemeral-pool-creation.patch
Patch04: 0004-Support-ingress-creation-for-keystone-admin-endpoint.patch
Patch05: 0005-Allow-set-public-endpoint-url-for-keystone-endpoints.patch
Patch06: 0006-Wrong-usage-of-rbd_store_chunk_size.patch
Patch07: 0007-Add-stx_admin-account.patch
Patch09: 0009-Add-flavor-extra-spec-hw-pci_irq_affinity_mask.patch
Patch10: 0010-Enable-taint-toleration-for-Openstack-services.patch
Patch11: 0011-Fix-nova-compute-ssh-init-to-execute-as-runAsUser.patch
Patch12: 0012-Replace-deprecated-Nova-VNC-configurations.patch
Patch13: 0013-Remove-TLS-from-openstack-services.patch
Patch14: 0014-Remove-mariadb-and-rabbit-tls.patch
Patch15: 0015-Decrease-terminationGracePeriodSeconds-on-glance-api.patch
Patch16: 0016-Network-Resources-Cleanup-before-OpenStack-Removal.patch
Patch17: 0017-Update-RBAC-authorization-api-to-v1.patch
Patch18: 0018-Fixing-cinder-helm-release-hooks-weights-helmv3.patch
Patch19: 0019-Fixing-placement-helm-release-hooks.patch
Patch20: 0020-Fixing-nova-helm-release-hooks-and-weights.patch

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
%patch09 -p1
%patch10 -p1
%patch11 -p1
%patch12 -p1
%patch13 -p1
%patch14 -p1
%patch15 -p1
%patch16 -p1
%patch17 -p1
%patch18 -p1
%patch19 -p1
%patch20 -p1

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
