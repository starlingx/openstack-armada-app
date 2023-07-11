#!/bin/bash
#
# Copyright (c) 2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# Clears OpenStack service aliases.
#

SERVICES=(
  cinder
  glance
  heat
  nova
  openstack
)

for service in "${SERVICES[@]}"; do
  unalias "${service}" 2> /dev/null
done
