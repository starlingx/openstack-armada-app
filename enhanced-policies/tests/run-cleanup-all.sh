#
# This script cleans up any remaining resource created by RBAC test scenarios
#
# Usage example:
# bash run-cleanup-all.sh
#

printf "WARNING: This script might DELETE some existing configuration if not \
used carefully, do you want to continue? \
('yes' to continue, anything else to cancel): "
read CONFIRMATION
if [[ ${CONFIRMATION^^} != 'YES' ]]; then
    echo "Script execution cancelled."
    exit 0
fi

printf "Cleaning up test resources...\n"

if [[ -z "${OS_CLOUD}" ]]; then
    echo "\$OS_CLOUD needs to be set before running this script"
    exit
else
    echo "Running cleanup script using OS_CLOUD=$OS_CLOUD"
fi

echo "removing security groups"
openstack security group list | grep "sg" | \
awk '{ system("openstack security group delete " $2) }'

echo "removing floating ips"
FIPS=$(openstack floating ip list | grep -vE "ID|---" | awk '{ print $2 }')
for FIP in $FIPS; do
    FIP_PFS=$(openstack floating ip port forwarding list $FIP |\
    grep -vE "ID|---" | awk '{ print $2 }')
    for FIP_PF in $FIP_PFS; do
        openstack floating ip port forwarding delete $FIP $FIP_PF
    done
    openstack floating ip delete $FIP
done
echo "removing routers"
ROUTERS=$(openstack router list | grep "vr" | awk '{ print $2 }')
for ROUTER in $ROUTERS; do
    SUBNET=$(openstack router show $ROUTER | grep interfaces_info | \
    awk '{ print $5 }' | sed 's/[",]//g')
    openstack router remove subnet $ROUTER $SUBNET
    openstack router delete $ROUTER
done
echo "removing servers"
openstack server list --all-projects | grep -E "vm[12]" | \
awk '{ system("openstack server delete " $2 " --wait") }'
echo "removing trunks"
openstack network trunk list | grep -E "trunk" | \
awk '{ system("openstack network trunk delete " $2) }'
echo "removing ports"
openstack port list | grep -E "port[12]" | \
awk '{ system("openstack port delete " $2) }'
echo "removing subnets"
openstack subnet list | grep -E "[^-]subnet[12]" | \
awk '{ system("openstack subnet delete " $2) }'
echo "removing networks"
openstack network list | grep -E "network[12]|extnet[12]" | \
awk '{ system("openstack network delete " $2) }'
echo "removing subnet pools"
openstack subnet pool list | grep "subnetpool" | \
awk '{ system("openstack subnet pool delete " $2) }'
echo "removing address scopes"
openstack address scope list | grep "addrscope" | \
awk '{ system("openstack address scope delete " $2) }'

openstack user delete user11 user12 user13 user21 user22 user23
openstack project delete project1 project2
openstack image delete cirros

printf "Cleanup finished.\n"
