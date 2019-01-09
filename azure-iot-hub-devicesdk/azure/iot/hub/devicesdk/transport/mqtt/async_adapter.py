import logging
from .mqtt_transport import MQTTTransport
from azure.iot.common import asyncio_compat

logger = logging.getLogger(__name__)


class MQTTAsyncTransport(MQTTTransport):
    """
    Asynchronous implementation of MQTTTransport for communication via MQTT protocol.
    """

    async def connect(self, callback=None):
        logger.info("async connecting to transport")
        connect_async = asyncio_compat.emulate_async(super(MQTTAsyncTransport, self).connect)

        def sync_callback():
            logger.info("async connect finished")

        callback = asyncio_compat.AwaitableCallback(sync_callback)

        await connect_async(callback)
        await callback.completion()

    async def disconnect(self, callback=None):
        logger.info("async disconnecting from transport")
        disconnect_async = asyncio_compat.emulate_async(super(MQTTAsyncTransport, self).disconnect)

        def sync_callback():
            logger.info("async disconnect finished")

        callback = asyncio_compat.AwaitableCallback(sync_callback)

        await disconnect_async(callback)
        await callback.completion()

    async def send_event(self, message):
        logger.info("async sending event")
        send_event_async = asyncio_compat.emulate_async(super(MQTTAsyncTransport, self).send_event)

        def sync_callback():
            logger.info("async sending finished")

        callback = asyncio_compat.AwaitableCallback(sync_callback)

        await send_event_async(message, callback)
        await callback.completion()
