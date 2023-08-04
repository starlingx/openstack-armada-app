#!/bin/bash
#
# Copyright (c) 2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# Creates OpenStack service aliases.
#
# All aliases created redirect OpenStack commands to a wrapper script,
# which executes them in a containerized environment.
#

SERVICES=(
  cinder
  glance
  heat
  nova
  openstack
)

for service in "${SERVICES[@]}"; do
  alias "${service}"="{{ .Values.workingDirectoryPath }}/clients-wrapper.sh ${service}"
done
