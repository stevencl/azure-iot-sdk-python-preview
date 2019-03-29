# --------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------


class TransportAction(object):
    """
    base class representing various actions that can be taken
    when the transport is connected.  When the MqttTransport user
    calls a function that requires the transport to be connected,
    a TransportAction object is created and added to the action
    queue.  Then, when the transport is actually connected, it
    loops through the objects in the action queue and executes them
    one by one.
    """

    def __init__(self, callback):
        self.callback = callback


class SendRegistrationAction(TransportAction):
    """
    TransportAction object used to send a registration request
    """

    def __init__(self, publish_topic, request, callback):
        TransportAction.__init__(self, callback)
        self.publish_topic = publish_topic
        self.request = request


class SubscribeAction(TransportAction):
    """
    TransportAction object used to subscribe to a specific MQTT topic
    """

    def __init__(self, subscribe_topic, qos, callback):
        TransportAction.__init__(self, callback)
        self.subscribe_topic = subscribe_topic
        self.qos = qos


class UnsubscribeAction(TransportAction):
    """
    TransportAction object used to unsubscribe from a specific MQTT topic
    """

    def __init__(self, topic, callback):
        TransportAction.__init__(self, callback)
        self.topic = topic


class MethodResponseAction(TransportAction):
    """
    TransportAction object used to send a method response back to the service.
    """

    def __init__(self, method_response, callback):
        TransportAction.__init__(self, callback)
        self.method_response = method_response
