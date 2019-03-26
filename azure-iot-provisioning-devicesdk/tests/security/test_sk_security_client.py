# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------

import pytest
from azure.iot.provisioning.devicesdk.security.sk_security_client import SymmetricKeySecurityClient

fake_symmetric_key = "Zm9vYmFy"
key_name = "registration"
fake_provisioning_host = "beauxbatons.academy-net"
fake_registration_id = "MyPensieve"
module_id = "Divination"
fake_id_scope = "Enchanted0000Ceiling7898"
signature = "IsolemnlySwearThatIamuUptoNogood"
expiry = "1539043658"


def test_getters_after_create_security_client():
    security_client = SymmetricKeySecurityClient(
        fake_registration_id, fake_symmetric_key, fake_id_scope
    )
    assert security_client.id_scope == fake_id_scope
    assert security_client.registration_id == fake_registration_id


def test_create_sas():
    security_client = SymmetricKeySecurityClient(
        fake_registration_id, fake_symmetric_key, fake_id_scope
    )
    sas_value = security_client.create_shared_access_signature()
    assert key_name in sas_value
    assert fake_registration_id in sas_value
    assert fake_id_scope in sas_value
