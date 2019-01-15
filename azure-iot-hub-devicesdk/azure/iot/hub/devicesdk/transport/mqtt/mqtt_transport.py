# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import logging
from datetime import date
import six.moves.urllib as urllib
import six.moves.queue as queue
from .mqtt_provider import MQTTProvider
from transitions.extensions import LockedMachine as Machine
from azure.iot.hub.devicesdk.transport.abstract_transport import AbstractTransport
from azure.iot.hub.devicesdk.message import Message


"""
The below import is for generating the state machine graph.
"""
# from transitions.extensions import LockedGraphMachine as Machine

logger = logging.getLogger(__name__)

METHOD_QOS = 0
METHOD_TOPIC = "$iothub/methods/POST/#"


class QueuedAction:
    pass


class QueuedTelemetryAction(QueuedAction):
    def __init__(self, message, callback):
        self.message = message
        self.callback = callback


class QueuedSubscribeAction(QueuedAction):
    def __init__(self, topic, qos, callback):
        self.topic = topic
        self.qos = qos
        self.callback = callback


class QueuedUnsubscribeAction(QueuedAction):
    def __init__(self, topic, callback):
        self.topic = topic
        self.callback = callback


class QueuedMethodReponseAction(QueuedAction):
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
        self.on_event_sent = None
        self._action_queue = queue.LifoQueue()
        self._action_callback_map = {}
        self._method_callback_map = {}
        self._connect_callback = None
        self._disconnect_callback = None

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
        if self.on_event_sent:
            self.on_event_sent()
        if mid in self._action_callback_map:
            callback = self._action_callback_map[mid]
            del self._action_callback_map[mid]
            callback()
        else:
            # TODO: tests for unkonwn MID cases
            logger.warning("PUBACK received with unknown MID: %s", str(mid))

    def _on_provider_subscribe_complete(self, mid):
        if mid in self._action_callback_map:
            callback = self._action_callback_map[mid]
            del self._action_callback_map[mid]
            callback()
        else:
            # TODO: tests for unkonwn MID cases
            logger.warning("SUBACK received with unknown MID: %s", str(mid))

    def _on_provider_unsubscribe_complete(self, mid):
        if mid in self._action_callback_map:
            callback = self._action_callback_map[mid]
            del self._action_callback_map[mid]
            callback()
        else:
            # TODO: tests for unkonwn MID cases
            logger.warning("UNSUBACK received with unknown MID: %s", str(mid))

    def _on_provider_message(mid, topic, message):
        pass

    def _add_action_to_queue(self, event_data):
        """
        Queue an action for running later.  All actions that need to run while connected end up in
        this queue, even if they're going to be run immediately.
        """
        logger.info("Adding action to queue for running sending")
        if isinstance(event_data.args[0], QueuedAction):
            # TODO: some actions are more important than others, so maybe we need a priority queue of some sort.
            # for example, if we have a subscribe action and a get-twin action, we want to do the subscribe first
            # even if we're not subcribing for a twin-related topic, it can't hurt to do the subscribe first.
            self._action_queue.put_nowait(event_data.args[0])
        else:
            assert False
            logger.error("trying to queue invalid action.  ignoring")

    def _do_actions_in_queue(self, event_data):
        """
        Publish any events that are waiting in the event queue.  This function
        actually calls down into the provider to publish the events.  For each
        event that is published, it saves the message id (mid) and the callback
        that needs to be called when the result of the publish operation is i
        available.
        """
        logger.info("checking event queue")
        while True:
            try:
                action = self._action_queue.get_nowait()
            except queue.Empty:
                logger.info("done checking queue")
                return

            if isinstance(action, QueuedTelemetryAction):
                logger.info("running QueuedTelemetryAction")
                message_to_send = action.message
                base_topic = self._get_telemetry_topic()

                if isinstance(message_to_send, Message):
                    encoded_topic = self._encode_properties(message_to_send, base_topic)
                else:
                    encoded_topic = base_topic
                    message_to_send = Message(message_to_send)

                mid = self._mqtt_provider.publish(encoded_topic, message_to_send.data)
                # todo rename callback to completion_callback?  rename action_callback_map simililary
                self._action_callback_map[mid] = action.callback

            elif isinstance(action, QueuedSubscribeAction):
                # todo: do something to verify that a subscription action will survive a reconnection.  Is this what the session flag is for?
                logger.info("running QueuedSubscribeAction")
                mid = self._mqtt_provider.subscribe(action.topic, action.qos)
                self._action_callback_map[mid] = action.callback

            elif isinstance(action, QueuedUnsubscribeAction):
                logger.info("running QueuedUnsubscribeAction")
                mid = self._mqtt_provider.unsubscribe(action.topic)
                self._action_callback_map[mid] = action.callback

            elif isinstance(action, QueuedMethodReponseAction):
                logger.info("running QueuedUnsubscribeAction")
                topic = "TODO"
                mid = self._mqtt_provider.publish(topic, action.method_response)
                # todo rename callback to completion_callback?  rename action_callback_map simililary
                self._action_callback_map[mid] = action.callback

            else:
                logger.error("Removed unknown action type from queue.")

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
        self._mqtt_provider.on_mqtt_message = self._on_provider_message

    def _get_telemetry_topic(self):
        topic = "devices/" + self._auth_provider.device_id

        if self._auth_provider.module_id is not None:
            topic += "/modules/" + self._auth_provider.module_id

        topic += "/messages/events/"
        return topic

    def _encode_properties(self, message_to_send, topic):
        system_properties = dict()
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

    def connect(self, callback=None):
        self._connect_callback = callback
        self._trig_connect()

    def disconnect(self, callback=None):
        self._disconnect_callback = callback
        self._trig_disconnect()

    def send_event(self, message, callback=None):
        action = QueuedTelemetryAction(message, callback)
        self._trig_queue_action(action)

    # TODO: some wierd actions to consider:
    # how stingy should be be with sending SUBSCRIBE packets?  It doesn't hurt, and it could be more robust in case the transport isn't subscribed when it thinks it should be.
    # what if we're not connected and we call add_method_callback, but there are other method callbacks in the array.  Should this connect the transport?  If so, being stingy with SUBSCRIBE packets gets harder because we don't subscribe until later

    def add_method_callback(self, method_name, method_callback, completion_callback):
        self._method_callback_map[method_name] = method_callback
        if len(self._method_callback_map) == 1:
            action = QueuedSubscribeAction(METHOD_TOPIC, METHOD_QOS, completion_callback)
            self._trig_queue_action(action)
        else:
            completion_callback()

    def remove_method_callback(self, method_name, completion_callback):
        del self._method_callback_map[method_name]
        if len(self._method_callback_map) == 0:
            action = QueuedUnsubscribeAction(METHOD_TOPIC, completion_callback)
            self._trig_queue_action(action)
        else:
            completion_callback()

    def _on_shared_access_string_updated(self):
        self._trig_on_shared_access_string_updated()
