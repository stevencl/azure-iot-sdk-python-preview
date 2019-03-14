# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------
"""This module contains a class representing method calls that are received and responded to.
"""


class MethodCall(object):
    """Represents a call to a device or module method.

    :ivar str name: The name of the method being called.
    :ivar payload: The payload being sent with the call.
    :ivar int response_timeout: The time in seconds before a response to the call is invalid.
    """

    def __init__(self, name, payload, response_timeout):
        """Initializer for a MethodCall.

        :param str name: The name of the method being called.
        :param payload: The payload being sent with the call.
        :param int response_timeout: The time in seconds before a response to the call is invalid.
        """
        self._name = name
        self._payload = payload
        self._response_timeout = response_timeout

    @property
    def name(self):
        return self._name

    @property
    def payload(self):
        return self._payload

    @property
    def response_timeout(self):
        return self._response_timeout
