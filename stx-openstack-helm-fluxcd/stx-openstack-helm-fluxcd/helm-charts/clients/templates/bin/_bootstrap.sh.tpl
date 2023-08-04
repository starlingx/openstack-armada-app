#!/bin/bash
#
# Copyright (c) 2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

set -ex
{{ .Values.bootstrap.script | default "echo 'Not enabled'" }}
