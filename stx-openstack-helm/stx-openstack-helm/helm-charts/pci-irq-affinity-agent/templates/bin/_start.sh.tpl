#!/bin/bash

#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

# Script to encapsulate the starting routines
sh -c /tmp/patch_keyring.sh
python /tmp/start.py
