# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------
import pytest
from azure.iot.provisioning.devicesdk.security.sk_security_client import SymmetricKeySecurityClient
from azure.iot.provisioning.devicesdk.transport.mqtt_transport import MQTTTransport
from azure.iot.provisioning.devicesdk.sk_registration_client import SymmetricKeyRegistrationClient
from azure.iot.provisioning.devicesdk.registration_client_factory import create_from_security_client


xfail_notimplemented = pytest.mark.xfail(raises=NotImplementedError, reason="Unimplemented")


@pytest.fixture
def provisioning_host():
    return "fakehost.com"


@pytest.fixture
def security_client():
    return SymmetricKeySecurityClient("fake_registration_id", "fake_symmetric_key", "fake_id_scope")


@pytest.mark.parametrize(
    "protocol,expected_transport",
    [
        pytest.param("mqtt", MQTTTransport, id="mqtt"),
        pytest.param("amqp", None, id="amqp", marks=xfail_notimplemented),
        pytest.param("http", None, id="http", marks=xfail_notimplemented),
    ],
)
def test_create_from_security_provider_instantiates_client(
    provisioning_host, security_client, protocol, expected_transport
):
    client = create_from_security_client(provisioning_host, security_client, protocol)
    assert isinstance(client, SymmetricKeyRegistrationClient)
    assert isinstance(client._transport, expected_transport)
    assert client._transport.on_transport_registration_update is not None


def test_raises_when_client_created_from_no_host(security_client):
    with pytest.raises(ValueError, match="Provisioning Host must be provided."):
        create_from_security_client("", security_client, "mqtt")


def test_raises_when_client_created_from_security_provider_with_not_symmetric_security():
    with pytest.raises(
        ValueError,
        match="A symmetric key security provider must be provided for instantiating MQTT",
    ):
        not_symmetric_security_client = NonSymmetricSecurityClientTest()
        create_from_security_client(provisioning_host, not_symmetric_security_client, "mqtt")


class NonSymmetricSecurityClientTest(object):
    def __init__(self):
        pass
