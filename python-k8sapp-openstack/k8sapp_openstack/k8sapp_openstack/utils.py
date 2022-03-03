#
# Copyright (c) 2022 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import constants


def is_openstack_https_ready(plugin):
    """
    Check if OpenStack is ready for HTTPS

    Returns true if the https_enabled flag is set to true and if the openstack, openstack_ca
    and ssl_ca certificates are installed in the system.
    """
    cert_openstack, cert_openstack_ca, cert_ssl_ca = False, False, False
    if plugin._https_enabled():
        certificates = plugin.dbapi.certificate_get_list()
        for certificate in certificates:
            if certificate.certtype == constants.CERT_MODE_OPENSTACK:
                cert_openstack = True
            elif certificate.certtype == constants.CERT_MODE_OPENSTACK_CA:
                cert_openstack_ca = True
            elif certificate.certtype == constants.CERT_MODE_SSL_CA:
                cert_ssl_ca = True

    return cert_openstack and cert_openstack_ca and cert_ssl_ca
