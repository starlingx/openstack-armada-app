#!/bin/bash

{{/*
Copyright (c) 2023 Wind River Systems, Inc.

SPDX-License-Identifier: Apache-2.0
*/}}

set -ex

OPENSTACK_DIR=/var/opt/openstack

OPENSTACK_SCRIPTS=(
  /tmp/clear-aliases.sh
  /tmp/setup-aliases.sh
  /tmp/wrapper.sh
)

mkdir -p ${OPENSTACK_DIR}/sysadmin
cp ${OPENSTACK_SCRIPTS[@]} ${OPENSTACK_DIR}
chmod -R 755 ${OPENSTACK_DIR}
