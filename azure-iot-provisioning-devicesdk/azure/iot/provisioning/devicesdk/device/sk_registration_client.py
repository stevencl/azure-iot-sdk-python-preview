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
        self._transport.on_transport_registration_complete = self.on_device_registration_complete

    def register(self):
        """
        Register the device with the provisioning service.
        """
        logger.info("Sending message to Hub...")
        subscribe_complete = Event()
        send_request_complete = Event()

        def callback_request():
            send_request_complete.set()
            logger.info("Successfully sent request to Hub")

        def callback_subscribe():
            subscribe_complete.set()
            logger.info("Successfully subscribed to Hub")

        self._transport.send_registration_request(
            callback_subscribe=callback_subscribe, callback_request=callback_request
        )
        subscribe_complete.wait()
        send_request_complete.wait()

    def cancel(self):
        pass

    def disconnect(self):
        self._transport.disconnect()

    def on_device_registration_complete(self, topic, payload):
        """Handler to be called by the transport when registration is done change."""
        logger.info("on_device_registration_complete")
        self.on_registration_complete(topic, payload)

    def _on_state_change(self, new_state):
        """Handler to be called by the transport upon a connection state change."""
        self.state = new_state
        logger.info("Connection State - {}".format(self.state))
