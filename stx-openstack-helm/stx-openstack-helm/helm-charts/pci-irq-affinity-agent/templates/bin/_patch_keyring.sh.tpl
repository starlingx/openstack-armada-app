#!/bin/bash

#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

# Script to patch the keyring library so that it allows automation
# by not asking for user input on the keyring password
# This 'change' was taken from the platform keyring library
KEYRING_LIB=$(find / -name file.py)
sed -i '/self.keyring_key *= *getpass.getpass(/,/)/s/^/#/;/self.keyring_key *= *getpass.getpass/i\        # TAKEN FROM PLATFORM KEYRING CODE\n\        self.keyring_key = "Please set a password for your new keyring: "' $KEYRING_LIB
