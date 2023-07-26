#!/bin/bash
#
# Copyright (c) 2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# Copies setup scripts to the volume mount directory and creates an openrc
# file for admin access to the OpenStack clients container.
#

set -ex

TMP_DIR=/tmp
OPENSTACK_DIR=/var/opt/openstack

OPENSTACK_SETUP_SCRIPTS=(
  clear-aliases.sh
  setup-aliases.sh
  clients-wrapper.sh
  local_openstackrc
)

# Store ownership of the volume mount directory to use it later on other files.
ownership=$(ls -nd "${OPENSTACK_DIR}" | awk '{print $3":"$4}')

# Copy setup scripts to volume mount directory and adjust their mode/ownership
# to make them only usable by their corresponding owners and/or groups.
for setup_script in "${OPENSTACK_SETUP_SCRIPTS[@]}"; do

  cp "${TMP_DIR}/${setup_script}" "${OPENSTACK_DIR}"
  chmod 550 "${OPENSTACK_DIR}/${setup_script}"
  chown "${ownership}" "${OPENSTACK_DIR}/${setup_script}"

done

# Create openrc file for admin access.
ADMIN_OPENRC="${OPENSTACK_DIR}/admin-openrc"

touch "${ADMIN_OPENRC}"
chmod 600 "${ADMIN_OPENRC}"
chown "${ownership}" "${ADMIN_OPENRC}"

cat << EOF > "${ADMIN_OPENRC}"
source /etc/platform/openrc --no_credentials

if [[ "$?" -ne 0 ]]; then
  return 1
fi

source "${OPENSTACK_DIR}/setup-aliases.sh"

if [[ "$?" -ne 0 ]]; then
  return 1
fi

export OS_USERNAME={{ .Values.endpoints.identity.auth.admin.username }}
export OS_PASSWORD={{ .Values.endpoints.identity.auth.admin.password }}

export OS_AUTH_URL=\
{{ .Values.endpoints.identity.scheme.default }}://\
{{ .Values.endpoints.identity.name }}.openstack.svc.\
{{ .Values.endpoints.cluster_domain_suffix }}\
{{ .Values.endpoints.identity.path.default }}

export PS1='[\u@\h \W(keystone_\$OS_USERNAME)]\$ '

return 0
EOF
