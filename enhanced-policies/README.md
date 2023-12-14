Enhanced Policies
==========================

This repository aims to provide enhanced policies for stx-openstack.

It's important that all the overrides files get applied, some of the rules present in a policy from one service might depend on other services to work (e.g. nova commands might depend on glance/cinder/neutron permissions). They should not be used separately.

|Design|Roles|Permissions summary|
|:-------------|-------------|:-----|
|Default Role:|member|Users with 'member' can manage certain resources of the project.|
|New Role to add:|project_admin|Users with role 'project_admin' could manage all resources of the project|
|New Role to add:|project_readonly|Users with role 'project_readonly' can only get list and detail of resources of the project, and shared resources of other projects|

Setting up the environment
--------------------------

Make sure you have access to the Openstack CLI, follow the instructions on [this doc.](https://docs.starlingx.io/system_configuration/openstack/enhanced-rbac-policies.html)

1. Transfer the policies to your cloud's controller:
    ```
    rsync -avP *-policy-overrides.yml <user>@<controller-floating-ip>:~/rbac
    ```
2. Log into your active controller
3. Create your clouds.yaml file
   ```bash
   cat <<EOF >clouds.yaml
   clouds:
     openstack:
       region_name: RegionOne
       identity_api_version: 3
       endpoint_type: internalURL
       auth:
         username: 'admin'
         password: '<PASSWORD FOR ADMIN>'
         project_name: 'admin'
         project_domain_name: 'default'
         user_domain_name: 'default'
         auth_url: 'http://keystone.openstack.svc.cluster.local/v3'
   EOF
   ```
4. Create the custom roles:
    ```
    # Assuming you are using method 1
    export OS_CLOUD=openstack

    openstack role create project_admin
    openstack role create project_readonly
    ```
5. In order to enable the extensions required for some of the Neutron tests, include the following configuration to the Neutron helm override YML file:
   ```
   conf:
    neutron:
        DEFAULT:
            service_plugins:
            - router
            - network_segment_range
            - qos
            - segments
            - port_forwarding
            - trunk
    plugins:
        ml2_conf:
            ml2:
                extension_drivers:
                - port_security
                - qos
    openvswitch_agent:
        agent:
            extensions:
            - qos
            - port_forwarding
   ```
6. Apply the policy overrides for each service to your cloud
    ```
    source /etc/platform/openrc

    system helm-override-update stx-openstack keystone openstack --reuse-values --values=rbac/keystone-policy-overrides.yml
    system helm-override-update stx-openstack cinder openstack --reuse-values --values=rbac/cinder-policy-overrides.yml
    system helm-override-update stx-openstack nova openstack --reuse-values --values=rbac/nova-policy-overrides.yml
    system helm-override-update stx-openstack neutron openstack --reuse-values --values=rbac/neutron-policy-overrides.yml
    system helm-override-update stx-openstack glance openstack --reuse-values --values=rbac/glance-policy-overrides.yml
    system helm-override-update stx-openstack horizon openstack --reuse-values --values=rbac/horizon-policy-overrides.yml
    system helm-override-update stx-openstack horizon openstack --reuse-values --values=rbac/horizon-nova-policy-overrides.yml

    system application-apply stx-openstack
    ```
7. Watch for application overrides to finish applying
    ```
    watch system application-show stx-openstack
    ```

Running tests
-------------

Please follow the instructions below to test the enhanced policies on your system. We assume that the New Roles were created on you system and the overrides were successfully applied.

1. Get to the rbac folder you transfered into your controller node
    ```
    cd ~/rbac
    ```

2. IMPORTANT: create a venv and install the test dependencies
    ```
    if [ ! -d .venv ]; then
        python3 -m venv .venv
    fi

    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r test-requirements.txt
    ```
3. Download CirrOS image (dependency for nova and cinder tests)
    ```
    wget http://download.cirros-cloud.net/0.3.4/cirros-0.3.4-x86_64-disk.img
    ```
4. Execute the tests
    On StarlingX:
    ```
    export OS_CLOUD=openstack
    pytest tests/
    ```

    On Custom envs (Openstack):
    ```
    export OS_CLOUD=openstack
    pytest tests/ --env custom-o
    ```
   
If things go awry...
--------------------

**WARNING: The following script might DELETE some existing configuration if not used carefully!**

One can use the run-cleanup-all.sh script to remove any leftovers from the test
on the environment:

```bash
export OS_CLOUD=openstack
bash run-cleanup-all.sh
```

Role Permission Details
-----------------------

|Role Permissions|identity(keystone)|compute(nova)|networking(neutron)|image(glance)|volume(cinder)|
|---|:---|:---|:---|:---|:---|
|member|All operations that legacy role '_member_' can do|1 - Can get list and detail of instances<br>2 - Can create instance/Can open console of instances<br>3 -  Can access log of instance<br>4 - Can manage keypairs of his/her own|1 - Can only create/update/delete port<br>2 - Can get list and detail of resources: subnetpool, address scope, networks, subnets, etc.|1,can create and update image, upload image content<br>|1 - Can create volume<br>2 - Can create volume from image<br>3 - Can create volume snapshot<br>4 - Can create volume-backup|
|project_admin|all operations that legacy role '_member_' can do;|all operations that legacy role '_member_' can do<br>|1 - All operations that legacy role '_member_' can do<br>2 - Can create/update/delete 'shared' subnetpool<br>3 - Can create/update/delete address scope<br>4 - Can create/update/delete shared network<br>|1 - All operations that legacy role '_member_' can do<br>2 - Can publicize_image<br>|1 - All operations that legacy role '_member_' can do|
|project_readonly|all operations that legacy role '_member_' can do<br>|1 - Can only get list and detail of instances<br>2 - Can manage key-pairs of his/her own|1 - Can only get list and detail of resources: subnetpool, address scopes, networks, subnets,etc.|1 - Can only get list and detail of images|1 - Can only get list and detail of volumes, backups, snapshots|
