#!/bin/bash

{{/*
#
# Copyright (c) 2019 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
*/}}

set -ex

# Create user
USER_ID=$( openstack user list -f value \
    --domain ${SERVICE_OS_USER_DOMAIN_NAME} \
    | grep ${SERVICE_OS_USERNAME} | awk '{print $1}' )

if [ "x${USER_ID}" = "x" ]; then
    USER_ID=$( openstack user create -f value -c id \
        --domain ${SERVICE_OS_USER_DOMAIN_NAME} \
        --password ${SERVICE_OS_PASSWORD} \
        ${SERVICE_OS_USERNAME} )
fi

openstack user show ${USER_ID}

# Create project role assignment
ROLE_ID=$( openstack role assignment list -f value --name \
    --user ${SERVICE_OS_USERNAME} \
    --user-domain ${SERVICE_OS_USER_DOMAIN_NAME} \
    --project ${SERVICE_OS_PROJECT_NAME} \
    --project-domain ${SERVICE_OS_PROJECT_DOMAIN_NAME} \
    | awk '{print $1}' )

if [ "${ROLE_ID}" != "admin" ]; then
    openstack role add \
        --project ${SERVICE_OS_PROJECT_NAME} \
        --project-domain ${SERVICE_OS_PROJECT_DOMAIN_NAME} \
        --user ${SERVICE_OS_USERNAME} \
        --user-domain ${SERVICE_OS_USER_DOMAIN_NAME} \
        ${SERVICE_OS_ROLE}
fi

openstack role assignment list --name

# Create service
SERVICE_ID=$( openstack service list -f value \
    | grep ${OS_SERVICE_NAME} | awk '{print $1}' )

if [ "x${SERVICE_ID=}" = "x" ]; then
    SERVICE_ID=$( openstack service create -f value -c id \
        --name ${OS_SERVICE_NAME} \
        --description "${OS_SERVICE_DESCRIPION}" \
        ${OS_SERVICE_TYPE} )
fi

openstack service show ${SERVICE_ID}

# Create endpoint (internal only)
ENDPOINT_ID=$( openstack endpoint list -f value \
    --region ${SERVICE_OS_REGION_NAME} \
    --interface ${INTERFACE_NAME} \
    --service ${OS_SERVICE_NAME} \
    | awk '{print $1}')

if [ "x${ENDPOINT_ID}" = "x" ]; then
    ENDPOINT_ID=$( openstack endpoint create -f value -c id \
        --region ${SERVICE_OS_REGION_NAME} \
        ${OS_SERVICE_NAME} \
        ${OS_SERVICE_ENDPOINT_INTERFACE} \
        ${OS_SERVICE_ENDPOINT_URL} )
fi

openstack endpoint show ${ENDPOINT_ID}

