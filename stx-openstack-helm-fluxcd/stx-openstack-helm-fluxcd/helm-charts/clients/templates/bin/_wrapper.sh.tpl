#!/bin/bash -i

{{/*
Copyright (c) 2023 Wind River Systems, Inc.

SPDX-License-Identifier: Apache-2.0
*/}}

OPENSTACK_VARIABLES="
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
"

ENV_ARGUMENTS=()
for variable in ${OPENSTACK_VARIABLES}; do
  if [[ ! -z "$(printenv ${variable})" ]]; then
    ENV_ARGUMENTS+=("${variable}=$(printenv ${variable})")
  fi
done

CONTROLLER=$(echo ${PS1@P} | grep -Po 'controller-\d+')
if [[ -z "${CONTROLLER}" ]]; then
  echo "OpenStack CLIs can only be accessed from a controller node."
  exit 1
fi

POD=$(kubectl -n openstack get pods | grep -i "clients-${CONTROLLER}.*Running" | awk '{print $1}')
if [[ -z "${POD}" ]]; then
  echo "Could not find \`clients\` pod in ${CONTROLLER}."
  echo "Make sure the pod is running and try again."
  exit 1
fi

kubectl -n openstack exec -it ${POD} -c clients -- env ${ENV_ARGUMENTS[@]} $*
