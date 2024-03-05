StarlingX Openstack Style Commandments
======================================

- Step 1: Read the OpenStack style commandments
  https://docs.openstack.org/hacking/latest/
- Step 2: Read on

STX-Openstack Specific Commandments
---------------------------------------------------------

None so far

Running tests
-------------
The approach to running tests is to simply run the command ``tox``. This will
create virtual environments, populate them with dependencies and run all of
the tests that OpenStack CI systems run.
