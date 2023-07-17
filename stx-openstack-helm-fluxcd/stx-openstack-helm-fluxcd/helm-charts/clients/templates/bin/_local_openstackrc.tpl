#!/bin/bash
#
# Copyright (c) 2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# Creates and/or loads local file "~/$USER-openrc-openstack".
#
# Assumes the Keystone username is the same as the logged in username.
#

OPENSTACK_DIR=/var/opt/openstack
OPENSTACK_OPENRC=${HOME}/${USER}-openrc-openstack

# Check if local openrc file exists.
if [[ -e "${OPENSTACK_OPENRC}" ]]; then

  # If it does, source it.
  source "${OPENSTACK_OPENRC}"
  return $?

fi

# Otherwise, create and source it.
read -s -p "Enter password for Keystone user \`${USER}\`: " password

touch "${OPENSTACK_OPENRC}"
chmod 600 "${OPENSTACK_OPENRC}"

cat << EOF >> "${OPENSTACK_OPENRC}"
source /etc/platform/openrc --no_credentials

if [[ "$?" -ne 0 ]]; then
  return 1
fi

source "${OPENSTACK_DIR}/setup-aliases.sh"

if [[ "$?" -ne 0 ]]; then
  return 1
fi

export OS_USERNAME="${USER}"
export OS_PASSWORD="${password}"

export OS_AUTH_URL=\
{{ .Values.endpoints.identity.scheme.default }}://\
{{ .Values.endpoints.identity.name }}.openstack.svc.\
{{ .Values.endpoints.cluster_domain_suffix }}\
{{ .Values.endpoints.identity.path.default }}

export PS1='[\u@\h \W(keystone_\$OS_USERNAME)]\$ '

return 0
EOF

echo
echo "Created file \`${OPENSTACK_OPENRC}\`."
source "${OPENSTACK_OPENRC}"
return $?
