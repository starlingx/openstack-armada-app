#!/bin/bash

{{/*
Copyright (c) 2023 Wind River Systems, Inc.

SPDX-License-Identifier: Apache-2.0
*/}}

if [[ ${BASH_SOURCE} = '/'* ]]; then
  PATH_TO_SCRIPT=$(dirname ${BASH_SOURCE})
else
  PATH_TO_SCRIPT=$(pwd)/$(dirname ${BASH_SOURCE})
fi

SERVICES="
  openstack
  nova
  cinder
  glance
  heat
"

for service in ${SERVICES}; do
  alias "${service}"="${PATH_TO_SCRIPT}/wrapper.sh ${service}"
done
