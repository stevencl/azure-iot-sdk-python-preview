# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------

import pytest
from azure.iot.provisioning.devicesdk.security.sk_security_client import SymmetricKeySecurityClient
from azure.iot.provisioning.devicesdk.transport.mqtt_transport import MQTTTransport
from azure.iot.provisioning.devicesdk.device.sk_registration_client import (
    SymmetricKeyRegistrationClient,
)


@pytest.fixture
def provisioning_host():
    return "fakehost.com"


@pytest.fixture
def security_client():
    return SymmetricKeySecurityClient("fake_registration_id", "fake_symmetric_key", "fake_id_scope")


def test_client_register_calls_transport_register(provisioning_host, security_client, mocker):
    mock_transport = mocker.MagicMock(wraps=MQTTTransport)
    mocker.patch.object(mock_transport, "send_registration_request")
    client = SymmetricKeyRegistrationClient(mock_transport)

    client.register()

    assert mock_transport.send_registration_request.call_count == 1
