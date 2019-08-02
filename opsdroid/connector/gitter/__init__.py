"""A connector for Gitter."""
import logging
import aiohttp
import asyncio
import json
import urllib

from opsdroid.connector import Connector, register_event
from opsdroid.events import Message

_LOGGER = logging.getLogger(__name__)
GITTER_STREAM_API = "https://stream.gitter.im/v1/rooms"
GITTER_MESSAGE_BASE_API = "https://api.gitter.im/v1/rooms"


class ConnectorGitter(Connector):
    """A connector for Gitter."""

    def __init__(self, config, opsdroid=None):
        """Create the connector."""
        super().__init__(config, opsdroid=opsdroid)
        _LOGGER.debug("Starting Gitter connector")
        self.name = "gitter"
        self.session = None
        self.response = None
        self.bot_name = self.config.get("bot-name", 'opsdroid')
        self.room_id = self.config.get("room-id")
        self.access_token = self.config.get("access-token")
        self.update_interval = 1
        self.opsdroid = opsdroid
        self.listening = True

    async def connect(self):
        """Create the connection."""

        # Create connection object with chat library
        _LOGGER.debug("Connecting with gitter stream")
        self.session = aiohttp.ClientSession()
        gitter_url = self.build_url(GITTER_STREAM_API, self.room_id, "chatMessages", access_token=self.access_token)
        self.response = await self.session.get(gitter_url, timeout=None)

    def build_url(self, base_url, *res, **params):
        """Build the url. args ex:(base_url,p1,p2=1,p2=2)."""

        url = base_url
        for r in res:
            url = '{}/{}'.format(url, r)
        if params:
            url = '{}?{}'.format(url, urllib.parse.urlencode(params))
        return url

    async def listen(self):
        """Keep listing to the gitter channel."""
        _LOGGER.debug("Listening with gitter stream")
        while self.listening:
            try:
                await self._get_messages()
            except AttributeError:
                break

    async def _get_messages(self):
        """Message listener."""
        await asyncio.sleep(self.update_interval)
        async for data in self.response.content.iter_chunked(1024):
            message = await self.parse_message(data)
            if message is not None:
                await self.opsdroid.parse(message)

    async def parse_message(self, message):
        """Parse response from gitter to send message."""
        message = message.decode('utf-8').rstrip("\r\n")
        if len(message) > 1:
            message = json.loads(message)
            _LOGGER.debug(message)
            try:
                return Message(
                    message["text"],
                    message["fromUser"]["username"],
                    self.room_id,
                    self)
            except KeyError as err:
                _LOGGER.error("Unable to parse message %s", message)
                _LOGGER.debug(err.with_traceback())

    @register_event(Message)
    async def send_message(self, message):
        """Recived parsed message and send it back to gitter room."""
        # Send message.text back to the chat service
        url = self.build_url(GITTER_MESSAGE_BASE_API, message.target, "chatMessages")
        headers = {'Authorization': 'Bearer ' + self.access_token, 'Content-Type': 'application/json',
                   'Accept': 'application/json'}
        payload = {'text': message.text}
        resp = await self.session.post(url, json=payload, headers=headers)
        if resp.status == 200:
            _LOGGER.info("Successfully responded")
        else:
            _LOGGER.error("Unable to respond.")

    async def disconnect(self):
        """Disconnect the gitter."""
        # Disconnect from the chat service
        self.listening = False
        await self.session.close()
