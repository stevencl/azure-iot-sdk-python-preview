# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------

import uuid
import logging
import six.moves.queue as queue
import six.moves.urllib as urllib
from transitions import Machine
from .device_provisioning_constant import (
    USER_AGENT,
    API_VERSION,
    SUBSCRIBE_TOPIC_PROVISIONING,
    PUBLISH_TOPIC_REGISTRATION,
)
from azure.iot.hub.devicesdk.transport.mqtt.mqtt_provider import MQTTProvider
from . import transport_action
from .symmetric_key_transport import SymmetricKeyTransport

logger = logging.getLogger(__name__)


class MQTTTransport(object):
    def __init__(self, provisioning_host, security_client):
        self._security_client = security_client
        self._provisioning_host = provisioning_host

        # Event Handlers - Will be set by Client after instantiation of Transport
        self.on_transport_connected = None
        self.on_transport_disconnected = None

        self._pending_action_queue = queue.Queue()
        self._in_progress_actions = {}
        self._responses_with_unknown_mid = {}

        self._connect_callback = None
        self._disconnect_callback = None

        self._create_mqtt_provider()

        states = ["disconnected", "connecting", "connected", "disconnecting"]

        transitions = [
            # {
            #     "trigger": "_trig_connect",
            #     "source": "disconnected",
            #     "dest": "connecting",
            #     "after": "_call_provider_connect",
            # },
            # {
            #     "trigger": "_trig_connect",
            #     "source": ["connecting", "connected"],
            #     "dest": None
            # },
            {
                "trigger": "_trig_send_registration_request",
                "source": "disconnected",
                "before": "_add_action_to_queue",
                "dest": "connecting",
                "after": "_call_provider_connect",
            },
            {
                "trigger": "_trig_send_registration_request",
                "source": "connecting",
                "before": "_add_action_to_queue",
                "dest": None,
            },
            {
                "trigger": "_trig_send_registration_request",
                "source": "connected",
                "dest": None,
                "after": "_execute_actions_in_queue",
            },
            {
                "trigger": "_trig_provider_connect_complete",
                "source": "connecting",
                "dest": "connected",
                "after": "_execute_actions_in_queue",
            },
            {"trigger": "_trig_provider_connect_complete", "source": "connected", "dest": None},
            {
                "trigger": "_trig_disconnect",
                "source": "connected",
                "before": "_execute_unsubscribe",
                "dest": "disconnecting",
                "after": "_call_provider_disconnect",
            },
            {
                "trigger": "_trig_disconnect",
                "source": ["disconnecting", "disconnected"],
                "dest": None,
            },
            {
                "trigger": "_trig_provider_disconnect_complete",
                "source": "disconnecting",
                "dest": "disconnected",
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
            send_event=True,  # Use event_data structures to pass transition arguments
            finalize_event=_on_transition_complete,
            queued=True,
        )

        self._state_machine.on_enter_disconnecting("_execute_actions_in_queue")

    def send_registration_request(self, callback_subscribe=None, callback_request=None):
        logger.info("Sending registration request")
        subscribe_action = transport_action.SubscribeAction(
            subscribe_topic=SUBSCRIBE_TOPIC_PROVISIONING, qos=1, callback=callback_subscribe
        )
        rid = uuid.uuid4()
        request_action = transport_action.SendRegistrationAction(
            publish_topic=PUBLISH_TOPIC_REGISTRATION + str(rid),
            request=" ",
            callback=callback_request,
        )
        actions = [subscribe_action, request_action]
        self._trig_send_registration_request(actions)

    def query_operation_status(self):
        pass

    # def connect(self, callback=None):
    #     """
    #     Connect to the service.
    #
    #     :param callback: callback which is called when the connection to the service is complete.
    #     """
    #     logger.info("connect called")
    #     self._connect_callback = callback
    #     self._trig_connect()

    def disconnect(self, callback_disconnect=None, callback_unsubscribe=None):
        """
        Disconnect from the service.

        :param callback_disconnect: callback which is called when the connection to the service has been disconnected
        """
        logger.info("disconnect called")
        self._disconnect_callback = callback_disconnect
        action = transport_action.UnsubscribeAction(
            SUBSCRIBE_TOPIC_PROVISIONING, callback=callback_unsubscribe
        )
        self._trig_disconnect(action)

    def _call_provider_connect(self, event_data):
        logger.info("Calling provider connect")
        password = self._get_current_sas_token()
        self._mqtt_provider.connect(password)

    def _call_provider_disconnect(self, event_data):
        """
        Call into the provider to disconnect the transport.

        This is called by the state machine as part of a state transition

        :param EventData event_data:  Object created by the Transitions library with information about the state transition
        """
        logger.info("Calling provider disconnect")
        self._mqtt_provider.disconnect()

    def _execute_unsubscribe(self, event_data):
        action = event_data.args[0]
        self._execute_action(action)

    def _add_action_to_queue(self, event_data):
        """
        Queue an action for running later.  All actions that need to run while connected end up in
        this queue, even if they're going to be run immediately.

        This is called by the state machine as part of a state transition

        :param EventData event_data:  Object created by the Transitions library with information about the state transition
        """
        for action in event_data.args[0]:
            self._pending_action_queue.put_nowait(action)

    def _execute_actions_in_queue(self, event_data):
        """
        Execute any actions that are waiting in the action queue.
        This is called by the state machine as part of a state transition.
        This function actually calls down into the provider to perform the necessary operations.

        :param EventData event_data:  Object created by the Transitions library with information about the state transition
        """
        logger.info("checking _pending_action_queue")
        while True:
            try:
                action = self._pending_action_queue.get_nowait()
            except queue.Empty:
                logger.info("done checking queue")
                return

            self._execute_action(action)

    def _execute_action(self, action):
        """
        Execute an action from the action queue.  This is called when the transport is connected and the
        state machine is able to execute individual actions.

        :param TransportAction action: object containing the details of the action to be executed
        """
        if isinstance(action, transport_action.SendRegistrationAction):
            logger.info("running SendRegistrationAction")
            mid = self._mqtt_provider.publish(action.publish_topic, action.request)
            if mid in self._responses_with_unknown_mid:
                del self._responses_with_unknown_mid[mid]
                action.callback()
            else:
                self._in_progress_actions[mid] = action.callback

        elif isinstance(action, transport_action.SubscribeAction):
            logger.info(
                "running SubscribeAction topic=%s qos=%s", action.subscribe_topic, action.qos
            )
            mid = self._mqtt_provider.subscribe(action.subscribe_topic, action.qos)
            logger.info("subscribe mid = %s", mid)
            if mid in self._responses_with_unknown_mid:
                del self._responses_with_unknown_mid[mid]
                action.callback()
            else:
                self._in_progress_actions[mid] = action.callback

        elif isinstance(action, transport_action.UnsubscribeAction):
            logger.info("running UnsubscribeAction")
            mid = self._mqtt_provider.unsubscribe(action.topic)
            if mid in self._responses_with_unknown_mid:
                del self._responses_with_unknown_mid[mid]
                action.callback()
            else:
                self._in_progress_actions[mid] = action.callback

        else:
            logger.info("Execute not called for unknown action type from queue.")

    def _create_mqtt_provider(self):
        client_id = self._security_client.registration_id

        username = (
            self._security_client.id_scope
            + "/registrations/"
            + self._security_client.registration_id
            + "/api-version="
            + API_VERSION
            + "&ClientVersion="
            + urllib.parse.quote_plus(USER_AGENT)
        )

        hostname = self._provisioning_host

        self._mqtt_provider = MQTTProvider(client_id, hostname, username, ca_cert=None)

        self._mqtt_provider.on_mqtt_connected = self._on_provider_connect_complete
        self._mqtt_provider.on_mqtt_disconnected = self._on_provider_disconnect_complete
        self._mqtt_provider.on_mqtt_published = self._on_provider_publish_complete
        self._mqtt_provider.on_mqtt_subscribed = self._on_provider_subscribe_complete
        self._mqtt_provider.on_mqtt_unsubscribed = self._on_provider_unsubscribe_complete
        self._mqtt_provider.on_mqtt_message_received = self._on_provider_message_received_callback

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
        Callback that is called by the provider when it receives a PUBACK from the service

        :param mid: message id that was returned by the provider when `publish` was called.  This is used to tie the
            PUBLISH to the PUBACK.
        """
        logger.info("_on_provider_publish_complete")
        if mid in self._in_progress_actions:
            callback = self._in_progress_actions[mid]
            del self._in_progress_actions[mid]
            callback()
        else:
            logger.warning("PUBACK received with unknown MID: %s", str(mid))
            self._responses_with_unknown_mid[
                mid
            ] = mid  # storing MID for now.  will probably store result code later.

    def _on_provider_subscribe_complete(self, mid):
        """
        Callback that is called by the provider when it receives a SUBACK from the service

        :param mid: message id that was returned by the provider when `subscribe` was called.  This is used to tie the
            SUBSCRIBE to the SUBACK.
        """
        logger.info("_on_provider_subscribe_complete")
        if mid in self._in_progress_actions:
            callback = self._in_progress_actions[mid]
            del self._in_progress_actions[mid]
            callback()
        else:
            logger.warning("SUBACK received with unknown MID: %s", str(mid))
            self._responses_with_unknown_mid[
                mid
            ] = mid  # storing MID for now.  will probably store result code later.

    def _on_provider_unsubscribe_complete(self, mid):
        """
        Callback that is called by the provider when it receives an UNSUBACK from the service

        :param mid: message id that was returned by the provider when `unsubscribe` was called.  This is used to tie the
            UNSUBSCRIBE to the UNSUBACK.
        """
        logger.info("_on_provider_unsubscribe_complete")
        if mid in self._in_progress_actions:
            callback = self._in_progress_actions[mid]
            del self._in_progress_actions[mid]
            callback()
        else:
            logger.warning("UNSUBACK received with unknown MID: %s", str(mid))
            self._responses_with_unknown_mid[
                mid
            ] = mid  # storing MID for now.  will probably store result code later.

    def _on_provider_message_received_callback(self, topic, payload):
        logger.info("Message received on topic %s", topic)
        logger.info("Message has been received")
        self.on_transport_registration_complete(topic, payload)

    def _get_current_sas_token(self):
        """
        Set the current Shared Access Signature Token string.
        """
        return self._security_client.create_shared_access_signature()
