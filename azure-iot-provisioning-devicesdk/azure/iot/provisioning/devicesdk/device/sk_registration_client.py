# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------
"""
This module contains one of the implementations of the Registration Client which uses Symmetric Key authentication.
"""
import logging
from threading import Event
from .registration_client import RegistrationClient

logger = logging.getLogger(__name__)


class SymmetricKeyRegistrationClient(RegistrationClient):
    """
    Client which can be used to run the registration of a device using Symmetric Key authentication.
    """

    def __init__(self, transport):
        """
        Initializer for the Symmetric Key Registration Client
        """
        RegistrationClient.__init__(self, transport)
        self._transport.on_transport_connected = self._on_state_change
        self._transport.on_transport_disconnected = self._on_state_change
        self._transport.on_transport_registration_update = self._on_device_registration_update

    def register(self):
        """
        Register the device with the provisioning service.
        """
        logger.info("Sending message to Hub...")
        subscribe_complete = Event()
        send_request_complete = Event()

        def callback_subscribe():
            subscribe_complete.set()
            logger.info("Successfully subscribed to Hub")

        def callback_request():
            send_request_complete.set()
            logger.info("Successfully sent request to Hub")

        self._transport.send_registration_request(
            callback_subscribe=callback_subscribe, callback_request=callback_request
        )
        subscribe_complete.wait() and send_request_complete.wait()

    def cancel(self):
        """
        Cancels the current registration process.
        """
        pass

    def disconnect(self):
        """
        Disconnects the registration client from the IoT Hub
        """
        logger.info("Disconnecting from IoT Hub...")
        unsubscribe_complete = Event()
        disconnect_complete = Event()

        def callback_unsubscribe():
            unsubscribe_complete.set()
            logger.info("Successfully unsubscribed from IoT Hub")

        def callback_disconnect():
            disconnect_complete.set()
            logger.info("Successfully disconnected from IoT Hub")

        self._transport.disconnect(
            callback_disconnect=callback_disconnect, callback_unsubscribe=callback_unsubscribe
        )

        # unsubscribe_complete.wait()
        disconnect_complete.wait()

    def _on_device_registration_update(self, topic, payload):
        """Handler to be called by the transport when registration changes status."""
        logger.info("on_device_registration_complete")
        self.on_registration_complete(topic, payload)

    def _on_state_change(self, new_state):
        """Handler to be called by the transport upon a connection state change."""
        self.state = new_state
        logger.info("Connection State - {}".format(self.state))
