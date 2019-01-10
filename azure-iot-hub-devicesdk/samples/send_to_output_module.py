# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
import os
import time
from azure.iot.hub.devicesdk.module_client import ModuleClient
from azure.iot.hub.devicesdk.auth.authentication_provider_factory import from_environment
from azure.iot.hub.devicesdk.message import Message
import uuid

# The connection string for a device should never be stored in code. For the sake of simplicity we're using an environment variable here.
# conn_str = os.getenv("IOTHUB_MODULE_CONNECTION_STRING")
# The "Authentication Provider" is the object in charge of creating authentication "tokens" for the device client.
auth_provider = from_environment()
# For now, the SDK only supports MQTT as a protocol. the client object is used to interact with your Azure IoT hub.
# It needs an Authentication Provider to secure the communication with the hub, using either tokens or x509 certificates
module_client = ModuleClient.from_authentication_provider(auth_provider, "mqtt")


# The connection state callback allows us to detect when the client is connected and disconnected:
def connection_state_callback(status):
    print("connection status: " + status)


# Register the connection state callback with the client...
# it is not necessary to do so , but always better to know connection was successful
module_client.on_connection_state = connection_state_callback

# ... and connect the client.
module_client.connect()

# send 5 messages with a 1 second pause between each message
for i in range(0, 5):
    print("sending message #" + str(i))
    msg = Message("test wind speed " + str(i))
    msg.message_id = uuid.uuid4()
    msg.correlation_id = "correlation-1234"
    msg.custom_properties["tornado-warning"] = "yes"
    module_client.send_to_output(msg, "twister")
    time.sleep(1)

# send only string messages
for i in range(5, 10):
    print("sending message #" + str(i))
    module_client.send_to_output("test payload message " + str(i), "tracking")
    time.sleep(1)


# finally, disconnect
module_client.disconnect()
