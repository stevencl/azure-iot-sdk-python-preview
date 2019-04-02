# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------

import pytest
from azure.iot.provisioning.devicesdk.security.sk_security_client import SymmetricKeySecurityClient
from azure.iot.provisioning.devicesdk.transport.mqtt_transport import MQTTTransport
from azure.iot.provisioning.devicesdk.sk_registration_client import SymmetricKeyRegistrationClient


@pytest.fixture
def provisioning_host():
    return "fakehost.com"


@pytest.fixture
def security_client():
    return SymmetricKeySecurityClient("fake_registration_id", "fake_symmetric_key", "fake_id_scope")


class FakeMQTTTransport(MQTTTransport):
    def disconnect(self, callback_disconnect, callback_unsubscribe):
        callback_unsubscribe()
        callback_disconnect()

    def send_registration_request(self, callback_subscribe, callback_request):
        callback_subscribe()
        callback_request()

    def query_operation_status(self):
        pass


@pytest.fixture
def transport(mocker):
    return mocker.MagicMock(wraps=FakeMQTTTransport(mocker.MagicMock(), mocker.MagicMock()))


def test_client_register_calls_transport_register(provisioning_host, security_client, transport):
    client = SymmetricKeyRegistrationClient(transport)
    client.register()

    assert transport.send_registration_request.call_count == 1
