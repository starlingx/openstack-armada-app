%global helm_folder  /usr/lib/helm
%global armada_folder  /usr/lib/armada
%global app_folder  /usr/lib/application
%global toolkit_version 0.1.0
%global helmchart_version 0.1.0

Summary: StarlingX Openstack Application Helm charts
Name: stx-openstack-helm
Version: 1.0
Release: %{tis_patch_ver}%{?_tis_dist}
License: Apache-2.0
Group: base
Packager: Wind River <info@windriver.com>
URL: unknown

Source0: %{name}-%{version}.tar.gz

BuildArch: noarch

BuildRequires: helm
BuildRequires: openstack-helm-infra
BuildRequires: chartmuseum
Requires: openstack-helm-infra
Requires: openstack-helm
Requires: python-k8sapp-openstack-wheels

%description
StarlingX Openstack Application Helm charts

%prep
%setup

%build
# Stage helm-toolkit in the local repo
cp %{helm_folder}/helm-toolkit-%{toolkit_version}.tgz helm-charts/

# Host a server for the charts
chartmuseum --debug --port=8879 --context-path='/charts' --storage="local" --storage-local-rootdir="./helm-charts" &
sleep 2
helm repo add local http://localhost:8879/charts

# Make the charts. These produce a tgz file
cd helm-charts
make nova-api-proxy
make garbd
make keystone-api-proxy
make fm-rest-api
make nginx-ports-control
make dcdbsync
cd -

# terminate helm server (the last backgrounded task)
kill %1

# remove helm-toolkit. This will be packaged with openstack-helm-infra
rm  ./helm-charts/helm-toolkit-%{toolkit_version}.tgz

%install
# helm_folder is created by openstack-helm-infra
install -d -m 755 ${RPM_BUILD_ROOT}%{app_folder}
install -p -D -m 755 files/metadata.yaml ${RPM_BUILD_ROOT}%{app_folder}
install -d -m 755 ${RPM_BUILD_ROOT}%{helm_folder}
install -p -D -m 755 helm-charts/*.tgz ${RPM_BUILD_ROOT}%{helm_folder}
install -d -m 755 ${RPM_BUILD_ROOT}%{armada_folder}
install -p -D -m 755 manifests/*.yaml ${RPM_BUILD_ROOT}%{armada_folder}

%files
#helm_folder is owned by openstack-helm-infra
%defattr(-,root,root,-)
%{helm_folder}/*
%{armada_folder}/*
%{app_folder}/*
