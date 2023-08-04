#!/bin/bash
#
# Copyright (c) 2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# OpenStack clients wrapper responsible for executing commands
# passed as arguments in a containerized environment.
#

WORKING_DIR={{ .Values.workingDirectoryPath }}

# Set `KUBECONFIG`.
if [[ -z "${KUBECONFIG}" ]]; then
  KUBECONFIG=/etc/kubernetes/admin.conf
fi

# Set `env` arguments.
OPENSTACK_VARIABLES=(
  OS_AUTH_TYPE
  OS_AUTH_URL
  OS_CACERT
  OS_IDENTITY_API_SERVICE
  OS_INTERFACE
  OS_PASSWORD
  OS_PROJECT_DOMAIN_ID
  OS_PROJECT_DOMAIN_NAME
  OS_PROJECT_ID
  OS_PROJECT_NAME
  OS_REGION_NAME
  OS_USERNAME
  OS_USER_DOMAIN_NAME
)

ENV_ARGUMENTS=()
for variable in "${OPENSTACK_VARIABLES[@]}"; do
  if [[ ! -z "$(printenv ${variable})" ]]; then
    ENV_ARGUMENTS+=("${variable}=$(printenv ${variable})")
  fi
done

# Check if script is running on a controller node.
# If not, then abort.
CONTROLLER=$(hostname)
if [[ "${CONTROLLER}" != 'controller'* ]]; then
  echo "OpenStack CLIs can only be accessed from a controller node."
  exit 1
fi

# Check if controller node contains a healthy `clients` pod.
# If not, then abort.
POD=$(
  kubectl --kubeconfig "${KUBECONFIG}" -n openstack get pods \
    | grep -i "clients-${CONTROLLER}.*Running" | awk '{print $1}'
)
if [[ -z "${POD}" ]]; then
  echo "Could not find \`clients\` pod in ${CONTROLLER}."
  echo "Make sure the pod is running and try again."
  exit 1
fi

if grep -q "^${USER}:" /etc/passwd; then
  kubectl --kubeconfig "${KUBECONFIG}" -n openstack exec -it "${POD}" \
    -c clients -- env ${ENV_ARGUMENTS[@]} /bin/bash -c "$*"
else
  if [[ ! -d "${WORKING_DIR}/${USER}" ]]; then
    mkdir -p "${WORKING_DIR}/${USER}"
    chgrp -R openstack "${WORKING_DIR}/${USER}"
  fi

  kubectl --kubeconfig "${KUBECONFIG}" -n openstack exec -it "${POD}" \
    -c clients -- env ${ENV_ARGUMENTS[@]} /bin/bash -c "cd ${USER}; $*"
fi
