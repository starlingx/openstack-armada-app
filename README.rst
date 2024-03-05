StarlingX Openstack App
=======================

This repository contains the files for STX-Openstack, containing containerized
OpenStack services delivered as a StarlingX application.

To learn more about Openstack, you can visit the `project's official website <OPENSTACK>`_.

This repository is divided into the following sections:

- Openstack services (upstream/openstack)

  - Python packages
  - Service clients
  - Docker images

- Helm charts (openstack-helm, openstack-helm-infra and stx-openstack-helm-fluxcd)

  - Openstack Helm (openstack-helm)
  - Openstack Helm Infra (openstack-helm-infra)
  - STX-Openstack specific helm charts (stx-openstack-helm-fluxcd)

- FluxCD manifests (stx-openstack-helm-fluxcd)

- StarlingX app lifecycle plugins (python3-k8sapp-openstack)

- Enhanced app policies (enhanced-policies)

These folders holds all the necessary parts for the application tarball to be
assembled, including:

Openstack Services
------------------

Delivered via Docker images built using LOCI_, a project designed to quickly
build Lightweight OCI_ compatible images of OpenStack services.

When the OpenStack service is supposed to be delivered without patches, its OCI_
image file must mainly contain the BUILDER (i.e., loci), the PROJECT (i.e.,
OpenStack service name) and the PROJECT_REF (i.e., OpenStack service release)
information.

Example stx-cinder_:

::

    BUILDER=loci
    LABEL=stx-cinder
    PROJECT=cinder
    PROJECT_REF=stable/2023.1

Whenever a patch (for Debian build files and/or source code) is needed for a
given package, a reference to the original Debian package is created, and the
proper Debian package build structure is created (identically to any other
StarlingX Debian package) to enable the patching process.

In this case it is also possible to control the base version for the package
(e.g., to match the delivered OpenStack release) and later our internally built
and patched package MUST be referenced on the image build instruction.

To learn more about the StarlingX Debian package build structure, check `here <BUILD>`_

For example the python-openstackclient_ package requires patches on the source
code and also on the debian build file structure. So, the package meta_data.yaml
file is created pointing to a fixed base version (e.g., 6.2.0-1) to be downloaded
from `Salsa Debian <SALSA>`_ and later patched:

::

    ---
    debname: python-openstackclient
    debver: 6.2.0-1
    dl_path:
      name: python-openstackclient-debian-6.2.0-1.tar.gz
      url: https://salsa.debian.org/openstack-team/clients/python-openstackclient/-/archive/debian/6.2.0-1/python-openstackclient-debian-6.2.0-1.tar.gz
      md5sum: db8235ad534de91738f1dab8e3865a8a
      sha256sum: 91e35f3e6bc8113cdd228709360b383e0c4e7c7f884bb3ec47e61f37c4110da3
    revision:
      dist: $STX_DIST
      GITREVCOUNT:
        BASE_SRCREV: 27acda9a6b4885a50064cebc0858892e71aa37ce
        SRC_DIR: ${MY_REPO}/stx/openstack-armada-app/upstream/openstack/python-openstackclient

Inside the same Debian package folder are created directories to hold StarlingX
specific patches. Each directory has a "series" file listing the patch files
(and order) in which it will be applied during the build process:

- deb_patches: contains the debian build files patches

- patches: contains the package source code patches

Finally, any image that will require the "python-openstackclient" installed will
then have to set the PROJECT_REPO to "nil" and install the package as any other
DIST_PACKAGE that has to be installed.

Example stx-openstackclients_:

::

    BUILDER=loci
    LABEL=stx-openstackclients
    PROJECT=infra
    PROJECT_REPO=nil
    DIST_REPOS="OS +openstack"
    PIP_PACKAGES="
      httplib2 \
      ndg-httpsclient \
      pyasn1 \
      pycryptodomex \
      pyopenssl
    "
    DIST_PACKAGES="
      bash-completion \
      libffi-dev \
      openssl \
      python3-dev \
      python3-aodhclient \
      python3-barbicanclient \
      python3-cinderclient \
      python3-glanceclient \
      python3-heatclient \
      python3-keystoneclient \
      python3-neutronclient \
      python3-novaclient \
      python3-openstackclient \
      python3-osc-placement \
      python3-swiftclient
    "

Helm Charts
-----------

The OpenStack community provides two upstream repositories delivering helm-charts
for its services (openstack-helm_) and for its required infrastructure
(openstack-helm-infra_).

Both repositories are used by STX-Openstack. Since it might be needed to control
the version of Helm charts we are using and/or apply specific patches to the Helm
charts source, both repositories points to a fixed base commit SHA and are
delivered as any other StarlignX Debian package.

The common approach when developing a patch for such Helm charts is to first
understand if it is a StarlingX specific patch (i.e., for STX-Openstack use case
only) or if it is a "generic" code enhancement. The process of creating a Debian
patch is described on the `StarlingX Debian package build structure docs. <BUILD>`_

Whenever it is a generic code enhancement, the approach is to create the patch to
quickly fix the STX-Openstack issue/feature but also propose it upstream to the
openstack-helm and/or openstack-helm-infra community. If the change is accepted,
later it will be available on a newest base commit SHA, and when STX-Openstack
uprevs its base version for such packages, the patch can be deleted.

There are also cases when the issue can be solved by simply changing the Helm
override values for the chart, in that case, you can go for the static overrides
route described in the "FluxCD Manifests" section below.

Additionally, not all the Helm charts used by STX-Openstack are delivered by the
OpenStack community as part of openstack-helm and openstack-helm-infra repositories.
Some charts are custom to the application and are therefore developed/maintained
by the StarlingX community itself.
Such helm-charts can be found under `the stx-openstack-helm-fluxcd folder <STX-CHARTS>`__.
Currently the list contains the following charts:

- Clients

- Dcdbsync

- Garbd

- Keystone-api-proxy

- Nginx-ports-control

- Nova-api-proxy

- Pci-irq-affinity-agent

FluxCD Manifests
----------------

Identically to any other StarlingX applications, STX-Openstack uses FluxCD to
manage the dependencies between multiple Helm charts, control the expression of
charts relationships and provide static and default configuration attributes
(i.e., values.yaml overrides).

The application main metadata.yaml is placed `on the stx-openstack-helm-fluxcd
folder <STX-O-APP-METADATA>`__, and is used to hold the "app_name" and "app_version"
values (although those are overwritten later on the app build process) along with
directives regarding: disabled helm-charts, upgrade behavior and automatic
re-apply behavior.

The application main kustomization.yaml file is also placed under the `on the
stx-openstack-helm-fluxcd folder <STX-O-APP-KUSTOMIZATION>`__ and is used to
describe the kustomization resources, including the application namespace and
the resources available for this application. Each resource will match with a
directory under the same `stx-openstack-helm-fluxcd folder <STX-CHARTS>`__.

Each application manifest is usually specific to a given Helm chart, since it
will contain:

- The Helm release resource description

- The Helm release system and static helm override files

- Specific kustomization.yaml file listing the resources and describing how the
  system and static override files are generating secrets.

As described in the section above, some issues can be solved by modifying the
static overrides for the specific Helm chart. As an easy example, all images used
by the STX-Openstack application are updated by changing their values in the
static overrides for each chart. Example: `Cinder chart static overrides <CINDER-STATIC-OVERRIDES>`_.

Lifecycle plugins
-----------------

StarlingX applications are managed by the platform sysinv service, a Python
package that enables customization of its functionalities via plugins.
Whenever an application requires lifecycle plugins to customize actions /
configurations necessary for it to properly work, it can use systemconfig
entrypoints to "plugin its own Python code" to be executed as part of that
application lifecycle.

The STX-Openstack Python plugins are delivered as Debian packages containing the
Python code and its built version delivered as wheels. All of those plugins are
required to integrate the STX-Openstack application into the StarlingX application
framework and to support the various StarlingX deployments.

All plugins entrypoints are listed in the "setup.cfg" file, placed under the
`python3-k8sapp-openstack folder <K8S-APP>`__. Such plugins might be general to
the whole application (e.g., OpenstackBaseHelm, OpenstackAppLifecycleOperator and
OpenstackFluxCDKustomizeOperator) or specific to a given Helm Release (e.g.,
CinderHelm, NeutronHelm). Usually, specific Helm release plugins will extend the
base class of OpenstackBaseHelm.

- OpenstackAppLifecycleOperator: class containing methods used to describe
  lifecycle actions for an application, including:

  - Pre-apply actions
  - Pre-remove actions
  - Post-remove actions

- OpenstackFluxCDKustomizeOperator: class containing methods used to update the
  application top-level kustomization resource list, including actions like:

  - Enabling or disabling Helm releases on a given namespace
  - Enabling or disabling charts in a chart group.

- OpenstackBaseHelm: base class used to encapsulate OpenStack services operations
  for helm. This class is later extended for each OpenStack service or
  infrastructure component helm release that requires a plugin.

- Helm Release plugins: child class of OpenstackBaseHelm, used to encapsulate Helm
  operations for a specific Helm release.

Enhanced Policies
-----------------

This directory contains a series of examples for YAML overrides in order to customize OpenStack RBAC policies.

.. _OPENSTACK: https://www.openstack.org/
.. _LOCI: https://opendev.org/openstack/loci/
.. _OCI: https://opencontainers.org/
.. _stx-cinder: https://opendev.org/starlingx/openstack-armada-app/src/branch/master/upstream/openstack/python-cinder/debian/stx-cinder.stable_docker_image
.. _stx-openstackclients: https://opendev.org/starlingx/openstack-armada-app/src/branch/master/upstream/openstack/python-openstackclient/debian/stx-openstackclient.stable_docker_image
.. _python-openstackclient: https://opendev.org/starlingx/openstack-armada-app/src/branch/master/upstream/openstack/python-openstackclient
.. _BUILD: https://wiki.openstack.org/wiki/StarlingX/DebianBuildStructure
.. _SALSA: https://salsa.debian.org/openstack-team
.. _openstack-helm: https://opendev.org/openstack/openstack-helm
.. _openstack-helm-infra: https://opendev.org/openstack/openstack-helm-infra
.. _STX-CHARTS: https://opendev.org/starlingx/openstack-armada-app/src/branch/master/stx-openstack-helm-fluxcd/stx-openstack-helm-fluxcd/helm-charts
.. _STX-O-APP-METADATA: https://opendev.org/starlingx/openstack-armada-app/src/branch/master/stx-openstack-helm-fluxcd/stx-openstack-helm-fluxcd/files/metadata.yaml
.. _STX-O-APP-KUSTOMIZATION: https://opendev.org/starlingx/openstack-armada-app/src/branch/master/stx-openstack-helm-fluxcd/stx-openstack-helm-fluxcd/manifests/kustomization.yaml
.. _CINDER-STATIC-OVERRIDES: https://opendev.org/starlingx/openstack-armada-app/src/branch/master/stx-openstack-helm-fluxcd/stx-openstack-helm-fluxcd/manifests/cinder/cinder-static-overrides.yaml
.. _K8S-APP: https://opendev.org/starlingx/openstack-armada-app/src/branch/master/python3-k8sapp-openstack/k8sapp_openstack