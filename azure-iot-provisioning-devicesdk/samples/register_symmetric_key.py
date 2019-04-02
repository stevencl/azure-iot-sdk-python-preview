import os
import logging
import time
from six.moves import input
from azure.iot.provisioning.devicesdk.security.sk_security_client import SymmetricKeySecurityClient
from azure.iot.provisioning.devicesdk.registration_client_factory import create_from_security_client


logging.basicConfig(level=logging.ERROR)

provisioning_host = os.getenv("PROVISIONING_HOST")
id_scope = os.getenv("PROVISIONING_IDSCOPE")
registration_id = os.getenv("PROVISIONING_REGISTRATION_ID")
symmetric_key = os.getenv("PROVISIONING_SYMMETRIC_KEY")


symmetric_key_security_client = SymmetricKeySecurityClient(registration_id, symmetric_key, id_scope)
registration_client = create_from_security_client(
    provisioning_host, symmetric_key_security_client, "mqtt"
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
    selection = input("Press Q to quit\n")
    if selection == "Q" or selection == "q":
        registration_client.disconnect()
        print("Quitting...")
        break


# Output looks like
# """
# Device has been registered
# b'{"operationId":"4.550cb20c3349a409.9dc0a05d-1773-45a1-9270-750f42111573","status":"assigning"}'
# """
