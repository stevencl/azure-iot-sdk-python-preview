# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from .internal_client import InternalClient
from .message import Message


class ModuleClient(InternalClient):
    def send_to_output(self, message, output_name):
        """
        Sends an event/message to the given module output.
        This is an outgoing events and  means to be "output events"
        :param output_name: Name of the output to send the event to.
        :param message: message to send to the given output
        """
        if not isinstance(message, Message):
            message = Message(message)

        message.output_name = output_name
        self.send_event(message)
