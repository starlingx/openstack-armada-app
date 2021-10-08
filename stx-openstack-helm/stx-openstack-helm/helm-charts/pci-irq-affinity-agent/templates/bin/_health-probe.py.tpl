#!/usr/bin/env python

#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

"""
Health probe script PCI IRQ Affinity Agent.

Script returns failure to Kubernetes only when
  a. Fails to call nova to get instances

sys.stderr.write() writes to pod's events on failures.

Usage example:
# python health-probe.py

"""

import json
import os
import signal
import sys

import psutil

from pci_irq_affinity.nova_provider import novaClient


def test_rabbit_connection():
    rabbit_ok = False
    for p in psutil.process_iter():
        if 'python' in ' '.join(p.cmdline()):
            conns = p.connections()
            for c in conns:
                if c.raddr[1] == 5672 and c.status == 'ESTABLISHED':
                    rabbit_ok = True
    return rabbit_ok


def test_nova_availability():
    try:
        novaClient.get_nova()
        novaClient.get_instances({})
    except:
        return False
    return True


def check_pid_running(pid):
    if psutil.pid_exists(int(pid)):
        return True
    else:
        return False


if __name__ == "__main__":
    if "liveness-probe" in ','.join(sys.argv):
        pidfile = "/tmp/liveness.pid"  # nosec
    else:
        pidfile = "/tmp/readiness.pid"  # nosec
    data = {}
    if os.path.isfile(pidfile):
        with open(pidfile, 'r') as f:
            data = json.load(f)
        if check_pid_running(data['pid']):
            if data['exit_count'] > 1:
                # Third time in, kill the previous process
                os.kill(int(data['pid']), signal.SIGTERM)
                sys.exit(1)
            else:
                data['exit_count'] = data['exit_count'] + 1
                with open(pidfile, 'w') as f:
                    json.dump(data, f)
                sys.exit(0)
    data['pid'] = os.getpid()
    data['exit_count'] = 0
    with open(pidfile, 'w') as f:
        json.dump(data, f)
    if test_rabbit_connection() and test_nova_availability():
        sys.exit(0)  # return success
    else:
        sys.exit(1)
