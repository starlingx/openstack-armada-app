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
  aodh
  barbican
  cinder
  glance
  heat
  nova
  neutron
  openstack
  swift
)

for service in "${SERVICES[@]}"; do
  alias "${service}"="{{ .Values.workingDirectoryPath }}/clients-wrapper.sh ${service}"
done
