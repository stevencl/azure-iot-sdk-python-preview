import os
import logging
from azure.iot.provisioning.devicesdk.security.sk_security_client import SymmetricKeySecurityClient
from azure.iot.provisioning.devicesdk.device.registration_client_factory import (
    create_from_security_provider,
)

import time

logging.basicConfig(level=logging.DEBUG)

provisioning_host = os.getenv("PROVISIONING_HOST")
id_scope = os.getenv("PROVISIONING_IDSCOPE")
registration_id = os.getenv("PROVISIONING_REGISTRATION_ID")
symmetric_key = os.getenv("PROVISIONING_SYMMETRIC_KEY")


symmetric_key_security_provider = SymmetricKeySecurityClient(
    registration_id, symmetric_key, id_scope
)
registration_client = create_from_security_provider(
    provisioning_host, symmetric_key_security_provider, "mqtt"
)


def registration_status_callback(topic, payload):
    result = str(payload)
    print(result)
    if "operationId" in result:
        print("Device is registering")


registration_client.on_registration_complete = registration_status_callback

registration_client.register()

time.sleep(10)

while True:
    selection = input("Press Q: Quit for exiting\n")
    if selection == "Q" or selection == "q":
        print("Quitting")
        registration_client.disconnect()
        break


# Output looks like
# """
# Device has been registered
# b'{"operationId":"4.550cb20c3349a409.9dc0a05d-1773-45a1-9270-750f42111573","status":"assigning"}'
# """
