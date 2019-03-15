# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------

import logging
from datetime import date
import six.moves.urllib as urllib
import six.moves.queue as queue
from .mqtt_provider import MQTTProvider
from transitions import Machine
from azure.iot.hub.devicesdk.transport.abstract_transport import AbstractTransport
from azure.iot.hub.devicesdk.transport import constant
from azure.iot.hub.devicesdk.message import Message


"""
The below import is for generating the state machine graph.
"""
# from transitions.extensions import LockedGraphMachine as Machine

logger = logging.getLogger(__name__)


TOPIC_POS_DEVICE = 4
TOPIC_POS_MODULE = 6
TOPIC_POS_INPUT_NAME = 5


class TransportAction:
    pass


class SendMessageAction(TransportAction):
    def __init__(self, message, callback):
        self.message = message
        self.callback = callback


class SubscribeAction(TransportAction):
    def __init__(self, topic, qos, callback):
        self.topic = topic
        self.qos = qos
        self.callback = callback


class UnsubscribeAction(TransportAction):
    def __init__(self, topic, callback):
        self.topic = topic
        self.callback = callback


class MethodReponseAction(TransportAction):
    def __init__(self, method_response, callback):
        self.method_response = method_response
        self.callback = callback


class MQTTTransport(AbstractTransport):
    def __init__(self, auth_provider):
        """
        Constructor for instantiating a transport
        :param auth_provider: The authentication provider
        """
        AbstractTransport.__init__(self, auth_provider)
        self.topic = self._get_telemetry_topic()
        self._mqtt_provider = None
        self.on_transport_connected = None
        self.on_transport_disconnected = None
        self._action_queue = queue.Queue()
        self._callback_map = {}
        self._connect_callback = None
        self._disconnect_callback = None

        self._c2d_topic = None
        self._input_topic = None

        states = ["disconnected", "connecting", "connected", "disconnecting"]

        transitions = [
            {
                "trigger": "_trig_connect",
                "source": "disconnected",
                "dest": "connecting",
                "after": "_call_provider_connect",
            },
            {"trigger": "_trig_connect", "source": ["connecting", "connected"], "dest": None},
            {
                "trigger": "_trig_provider_connect_complete",
                "source": "connecting",
                "dest": "connected",
                "after": "_do_actions_in_queue",
            },
            {
                "trigger": "_trig_disconnect",
                "source": ["disconnected", "disconnecting"],
                "dest": None,
            },
            {
                "trigger": "_trig_disconnect",
                "source": "connected",
                "dest": "disconnecting",
                "after": "_call_provider_disconnect",
            },
            {
                "trigger": "_trig_provider_disconnect_complete",
                "source": "disconnecting",
                "dest": "disconnected",
            },
            {
                "trigger": "_trig_queue_action",
                "source": "connected",
                "before": "_add_action_to_queue",
                "dest": None,
                "after": "_do_actions_in_queue",
            },
            {
                "trigger": "_trig_queue_action",
                "source": "connecting",
                "before": "_add_action_to_queue",
                "dest": None,
            },
            {
                "trigger": "_trig_queue_action",
                "source": "disconnected",
                "before": "_add_action_to_queue",
                "dest": "connecting",
                "after": "_call_provider_connect",
            },
            {
                "trigger": "_trig_on_shared_access_string_updated",
                "source": "connected",
                "dest": "connecting",
                "after": "_call_provider_reconnect",
            },
            {
                "trigger": "_trig_on_shared_access_string_updated",
                "source": ["disconnected", "disconnecting"],
                "dest": None,
            },
        ]

        def _on_transition_complete(event_data):
            if not event_data.transition:
                dest = "[no transition]"
            else:
                dest = event_data.transition.dest
            logger.info(
                "Transition complete.  Trigger=%s, Dest=%s, result=%s, error=%s",
                event_data.event.name,
                dest,
                str(event_data.result),
                str(event_data.error),
            )

        self._state_machine = Machine(
            model=self,
            states=states,
            transitions=transitions,
            initial="disconnected",
            send_event=True,  # This has nothing to do with telemetry events.  This tells the machine use event_data structures to hold transition arguments
            finalize_event=_on_transition_complete,
            queued=True,
        )

        # to render the state machine as a PNG:
        # 1. apt install graphviz
        # 2. pip install pygraphviz
        # 3. change import line at top of this file to import LockedGraphMachine as Machine
        # 4. uncomment the following line
        # 5. run this code
        # self.get_graph().draw('mqtt_transport.png', prog='dot')

        self._create_mqtt_provider()

    def _call_provider_connect(self, event_data):
        """
        Call into the provider to connect the transport.
        This is meant to be called by the state machine as part of a state transition
        """
        logger.info("Calling provider connect")
        password = self._auth_provider.get_current_sas_token()
        self._mqtt_provider.connect(password)

        if hasattr(self._auth_provider, "token_update_callback"):
            self._auth_provider.token_update_callback = self._on_shared_access_string_updated

    def _call_provider_disconnect(self, event_data):
        """
        Call into the provider to disconnect the transport.
        This is meant to be called by the state machine as part of a state transition
        """
        logger.info("Calling provider disconnect")
        self._mqtt_provider.disconnect()
        self._auth_provider.disconnect()

    def _call_provider_reconnect(self, event):
        """
        reconnect the transport
        """
        password = self._auth_provider.get_current_sas_token()
        self._mqtt_provider.reconnect(password)

    def _on_provider_connect_complete(self):
        """
        Callback that is called by the provider when the connection has been established
        """
        logger.info("_on_provider_connect_complete")
        self._trig_provider_connect_complete()

        if self.on_transport_connected:
            self.on_transport_connected("connected")
        callback = self._connect_callback
        if callback:
            self._connect_callback = None
            callback()

    def _on_provider_disconnect_complete(self):
        """
        Callback that is called by the provider when the connection has been disconnected
        """
        logger.info("_on_provider_disconnect_complete")
        self._trig_provider_disconnect_complete()

        if self.on_transport_disconnected:
            self.on_transport_disconnected("disconnected")
        callback = self._disconnect_callback
        if callback:
            self._disconnect_callback = None
            callback()

    def _on_provider_publish_complete(self, mid):
        """
        Callback that is called by the provider when a publish operation is complete.
        """
        if mid in self._callback_map:
            callback = self._callback_map[mid]
            del self._callback_map[mid]
            callback()
        else:
            # TODO: tests for unkonwn MID cases
            logger.warning("PUBACK received with unknown MID: %s", str(mid))

    def _on_provider_subscribe_complete(self, mid):
        """
        Callback that is called by the provider when a subscribe operation is complete.
        """
        if mid in self._callback_map:
            callback = self._callback_map[mid]
            del self._callback_map[mid]
            callback()
        else:
            # TODO: tests for unkonwn MID cases
            logger.warning("SUBACK received with unknown MID: %s", str(mid))

    def _on_provider_message_received_callback(self, topic, payload):
        """
        Callback that is called by the provider when a message is received.
        """
        logger.info("Message received on topic %s", topic)
        message_received = Message(payload)
        # TODO : Discuss everything in bytes , need to be changed, specially the topic
        topic_str = topic.decode("utf-8")
        topic_parts = topic_str.split("/")

        if _is_input_topic(topic_str):
            input_name = topic_parts[TOPIC_POS_INPUT_NAME]
            message_received.input_name = input_name
            _extract_properties(topic_parts[TOPIC_POS_MODULE], message_received)
            self.on_transport_input_message_received(input_name, message_received)
        elif _is_c2d_topic(topic_str):
            _extract_properties(topic_parts[TOPIC_POS_DEVICE], message_received)
            self.on_transport_c2d_message_received(message_received)
        else:
            pass  # is there any other case

    def _on_provider_unsubscribe_complete(self, mid):
        if mid in self._callback_map:
            callback = self._callback_map[mid]
            del self._callback_map[mid]
            callback()
        else:
            # TODO: tests for unkonwn MID cases
            logger.warning("UNSUBACK received with unknown MID: %s", str(mid))

    def _add_action_to_queue(self, event_data):
        """
        Queue an action for running later.  All actions that need to run while connected end up in
        this queue, even if they're going to be run immediately.
        """
        action = event_data.args[0]
        if isinstance(action, TransportAction):
            self._action_queue.put_nowait(event_data.args[0])
        else:
            assert False

    def _do_single_action(self, action):
        if isinstance(action, SendMessageAction):
            logger.info("running SendMessageAction")
            message_to_send = action.message
            base_topic = self._get_telemetry_topic()

            if isinstance(message_to_send, Message):
                encoded_topic = _encode_properties(message_to_send, base_topic)
            else:
                encoded_topic = base_topic
                message_to_send = Message(message_to_send)

            mid = self._mqtt_provider.publish(encoded_topic, message_to_send.data)
            self._callback_map[mid] = action.callback

        elif isinstance(action, SubscribeAction):
            logger.info("running SubscribeAction topic=%s qos=%s", action.topic, action.qos)
            mid = self._mqtt_provider.subscribe(action.topic, action.qos)
            logger.info("subscribe mid = %s", mid)
            self._callback_map[mid] = action.callback

        elif isinstance(action, UnsubscribeAction):
            logger.info("running UnsubscribeAction")
            mid = self._mqtt_provider.unsubscribe(action.topic)
            self._callback_map[mid] = action.callback

        elif isinstance(action, MethodReponseAction):
            logger.info("running MethodResponseAction")
            topic = "TODO"
            mid = self._mqtt_provider.publish(topic, action.method_response)
            self._callback_map[mid] = action.callback

        else:
            logger.error("Removed unknown action type from queue.")

    def _do_actions_in_queue(self, event_data):
        """
        Publish any events that are waiting in the event queue.  This function
        actually calls down into the provider to publish the events.  For each
        event that is published, it saves the message id (mid) and the callback
        that needs to be called when the result of the publish operation is i
        available.
        """
        logger.info("checking _action_queue")
        while True:
            try:
                action = self._action_queue.get_nowait()
            except queue.Empty:
                logger.info("done checking queue")
                return

            self._do_single_action(action)

    def _create_mqtt_provider(self):
        client_id = self._auth_provider.device_id

        if self._auth_provider.module_id is not None:
            client_id += "/" + self._auth_provider.module_id

        username = self._auth_provider.hostname + "/" + client_id + "/" + "?api-version=2018-06-30"

        hostname = None
        if hasattr(self._auth_provider, "gateway_hostname"):
            hostname = self._auth_provider.gateway_hostname
        if not hostname or len(hostname) == 0:
            hostname = self._auth_provider.hostname

        if hasattr(self._auth_provider, "ca_cert"):
            ca_cert = self._auth_provider.ca_cert
        else:
            ca_cert = None

        self._mqtt_provider = MQTTProvider(client_id, hostname, username, ca_cert=ca_cert)

        self._mqtt_provider.on_mqtt_connected = self._on_provider_connect_complete
        self._mqtt_provider.on_mqtt_disconnected = self._on_provider_disconnect_complete
        self._mqtt_provider.on_mqtt_published = self._on_provider_publish_complete
        self._mqtt_provider.on_mqtt_subscribed = self._on_provider_subscribe_complete
        self._mqtt_provider.on_mqtt_unsubscribed = self._on_provider_unsubscribe_complete
        self._mqtt_provider.on_mqtt_message_received = self._on_provider_message_received_callback

    def _get_telemetry_topic(self):
        topic = "devices/" + self._auth_provider.device_id

        if self._auth_provider.module_id:
            topic += "/modules/" + self._auth_provider.module_id

        topic += "/messages/events/"
        return topic

    def _get_base_topic(self):
        if self._auth_provider.module_id:
            return (
                "devices/"
                + self._auth_provider.device_id
                + "/modules/"
                + self._auth_provider.module_id
            )
        else:
            return "devices/" + self._auth_provider.device_id

    def _get_c2d_topic(self):
        """
        :return: The topic for cloud to device messages.It is of the format
        "devices/<deviceid>/messages/devicebound/#"
        """
        return self._get_base_topic() + "/messages/devicebound/#"

    def _get_input_topic(self):
        """
        :return: The topic for input messages. It is of the format
        "devices/<deviceId>/modules/<moduleId>/messages/inputs/#"
        """
        return self._get_base_topic() + "/inputs/#"

    def connect(self, callback=None):
        logger.info("connect called")
        self._connect_callback = callback
        self._trig_connect()

    def disconnect(self, callback=None):
        logger.info("disconnect called")
        self._disconnect_callback = callback
        self._trig_disconnect()

    def send_event(self, message, callback=None):
        action = SendMessageAction(message, callback)
        self._trig_queue_action(action, self._action_queue)

    def send_output_event(self, message, callback=None):
        action = SendMessageAction(message, callback)
        self._trig_queue_action(action, self._action_queue)

    def _on_shared_access_string_updated(self):
        self._trig_on_shared_access_string_updated()

    def enable_feature(self, feature_name, callback=None, qos=1):
        logger.info("enable_feature %s called", feature_name)
        if feature_name == constant.INPUT_MSG:
            self._enable_input_messages(callback, qos)
        elif feature_name == constant.C2D_MSG:
            self._enable_c2d_messages(callback, qos)
        else:
            logger.error("Feature name {} is unknown".format(feature_name))
            raise ValueError("Invalid feature name")

    def disable_feature(self, feature_name, callback=None):
        logger.info("disable_feature %s called", feature_name)
        if feature_name == constant.INPUT_MSG:
            self._disable_input_messages(callback)
        elif feature_name == constant.C2D_MSG:
            self._disable_c2d_messages(callback)
        else:
            logger.error("Feature name {} is unknown".format(feature_name))
            raise ValueError("Invalid feature name")

    def _enable_input_messages(self, callback=None, qos=1):
        action = SubscribeAction(self._get_input_topic(), qos, callback)
        self._trig_queue_action(action)
        self.feature_enabled[constant.INPUT_MSG] = True

    def _disable_input_messages(self, callback=None):
        action = UnsubscribeAction(self._get_input_topic(), callback)
        self._trig_queue_action(action)
        self.feature_enabled[constant.INPUT_MSG] = False

    def _enable_c2d_messages(self, callback=None, qos=1):
        action = SubscribeAction(self._get_c2d_topic(), qos, callback)
        self._trig_queue_action(action)
        self.feature_enabled[constant.C2D_MSG] = True

    def _disable_c2d_messages(self, callback=None):
        action = UnsubscribeAction(self._get_c2d_topic(), callback)
        self._trig_queue_action(action)
        self.feature_enabled[constant.C2D_MSG] = False


def _is_c2d_topic(split_topic_str):
    """
    Topics for c2d message are of the following format:
    devices/<deviceId>/messages/devicebound
    :param split_topic_str: The already split received topic string
    """
    if "messages/devicebound" in split_topic_str and len(split_topic_str) > 4:
        return True
    return False


def _is_input_topic(split_topic_str):
    """
    Topics for inputs are of the following format:
    devices/<deviceId>/modules/<moduleId>/messages/inputs/<inputName>
    :param split_topic_str: The already split received topic string
    """
    if "inputs" in split_topic_str and len(split_topic_str) > 6:
        return True
    return False


def _extract_properties(properties, message_received):
    """
    Extract key=value pairs from custom properties and set the properties on the received message.
    :param properties: The properties string which is ampersand(&) delimited key=value pair.
    :param message_received: The message received with the payload in bytes
    """
    key_value_pairs = properties.split("&")

    for entry in key_value_pairs:
        pair = entry.split("=")
        key = urllib.parse.unquote_plus(pair[0])
        value = urllib.parse.unquote_plus(pair[1])

        if key == "$.mid":
            message_received.message_id = value
        elif key == "$.cid":
            message_received.correlation_id = value
        elif key == "$.uid":
            message_received.user_id = value
        elif key == "$.to":
            message_received.to = value
        elif key == "$.ct":
            message_received.content_type = value
        elif key == "$.ce":
            message_received.content_encoding = value
        else:
            message_received.custom_properties[key] = value


def _encode_properties(message_to_send, topic):
    """
    uri-encode the system properties of a message as key-value pairs on the topic with defined keys.
    Additionally if the message has user defined properties, the property keys and values shall be
    uri-encoded and appended at the end of the above topic with the following convention:
    '<key>=<value>&<key2>=<value2>&<key3>=<value3>(...)'
    :param message_to_send: The message to send
    :param topic: The topic which has not been encoded yet. For a device it looks like
    "devices/<deviceId>/messages/events/" and for a module it looks like
    "devices/<deviceId>/<moduleId>/messages/events/
    :return: The topic which has been uri-encoded
    """
    system_properties = {}
    if message_to_send.output_name:
        system_properties["$.on"] = message_to_send.output_name
    if message_to_send.message_id:
        system_properties["$.mid"] = message_to_send.message_id

    if message_to_send.correlation_id:
        system_properties["$.cid"] = message_to_send.correlation_id

    if message_to_send.user_id:
        system_properties["$.uid"] = message_to_send.user_id

    if message_to_send.to:
        system_properties["$.to"] = message_to_send.to

    if message_to_send.content_type:
        system_properties["$.ct"] = message_to_send.content_type

    if message_to_send.content_encoding:
        system_properties["$.ce"] = message_to_send.content_encoding

    if message_to_send.expiry_time_utc:
        system_properties["$.exp"] = (
            message_to_send.expiry_time_utc.isoformat()
            if isinstance(message_to_send.expiry_time_utc, date)
            else message_to_send.expiry_time_utc
        )

    system_properties_encoded = urllib.parse.urlencode(system_properties)
    topic += system_properties_encoded

    if message_to_send.custom_properties and len(message_to_send.custom_properties) > 0:
        topic += "&"
        user_properties_encoded = urllib.parse.urlencode(message_to_send.custom_properties)
        topic += user_properties_encoded

    return topic
