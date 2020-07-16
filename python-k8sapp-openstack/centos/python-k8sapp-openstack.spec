%global pypi_name k8sapp-openstack
%global sname k8sapp_openstack

Name:           python-%{pypi_name}
Version:        1.0
Release:        %{tis_patch_ver}%{?_tis_dist}
Summary:        StarlingX sysinv extensions: Openstack K8S app

License:        Apache-2.0
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires: python3-setuptools
BuildRequires: python3-pbr
BuildRequires: python3-pip
BuildRequires: python3-wheel

%description
StarlingX sysinv extensions: Openstack K8S app

%package -n     python3-%{pypi_name}
Summary:        StarlingX sysinv extensions: Openstack K8S app

Requires:       python3-pbr >= 2.0.0
Requires:       sysinv >= 1.0

%description -n python3-%{pypi_name}
StarlingX sysinv extensions: Openstack K8S app

%prep
%setup
# Remove bundled egg-info
rm -rf %{pypi_name}.egg-info

%build
export PBR_VERSION=%{version}
%{__python3} setup.py build

%py3_build_wheel

%install
export PBR_VERSION=%{version}.%{tis_patch_ver}
export SKIP_PIP_INSTALL=1
%{__python3} setup.py install --skip-build --root %{buildroot}
mkdir -p ${RPM_BUILD_ROOT}/plugins
install -m 644 dist/*.whl ${RPM_BUILD_ROOT}/plugins/

%files
%{python3_sitelib}/%{sname}
%{python3_sitelib}/%{sname}-*.egg-info

%package wheels
Summary: %{name} wheels

%description wheels
Contains python wheels for %{name}

%files wheels
/plugins/*


%changelog
* Wed Sep 20 2019 Robert Church <robert.church@windriver.com>
- Initial version
