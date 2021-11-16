#!/usr/bin/env python

#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

"""
Startup script for PCI IRQ Affinity Agent.

Usage example:
# python start.py

"""

from pci_irq_affinity import agent

if __name__ == '__main__':
    agent.process_main()
