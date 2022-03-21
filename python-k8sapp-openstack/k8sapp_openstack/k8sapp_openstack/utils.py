#
# Copyright (c) 2022 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import constants
from sysinv.db import api as dbapi


def https_enabled():
    db = dbapi.get_instance()
    if db is None:
        return False

    isystem = db.isystem_get_one()
    return isystem.capabilities.get("https_enabled", False)


def is_openstack_https_certificates_ready():
    """Return whether the openstack certificates are ready or not.

    Returns True if the openstack, openstack_ca and ssl_ca
    certificates are installed in the system.
    """
    db = dbapi.get_instance()
    if db is None:
        return False

    cert_openstack, cert_openstack_ca, cert_ssl_ca = False, False, False
    certificates = db.certificate_get_list()
    for certificate in certificates:
        if certificate.certtype == constants.CERT_MODE_OPENSTACK:
            cert_openstack = True
        elif certificate.certtype == constants.CERT_MODE_OPENSTACK_CA:
            cert_openstack_ca = True
        elif certificate.certtype == constants.CERT_MODE_SSL_CA:
            cert_ssl_ca = True

    return cert_openstack and cert_openstack_ca and cert_ssl_ca


def is_openstack_https_ready():
    """Check if OpenStack is ready for HTTPS.

    Returns true if https is enabled and https certificates are
    installed in the system.
    """
    return https_enabled() and is_openstack_https_certificates_ready()
