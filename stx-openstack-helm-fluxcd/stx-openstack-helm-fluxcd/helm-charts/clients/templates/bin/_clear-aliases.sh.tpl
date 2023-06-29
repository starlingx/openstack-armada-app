#!/bin/bash

{{/*
Copyright (c) 2023 Wind River Systems, Inc.

SPDX-License-Identifier: Apache-2.0
*/}}

SERVICES="
  openstack
  nova
  cinder
  glance
  heat
"

for service in ${SERVICES}; do
  unalias "${service}" 2> /dev/null
done
