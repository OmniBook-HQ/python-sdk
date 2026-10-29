import asyncio
import base64
import json
import threading

import pytest
from websockets.asyncio.server import serve

from omnibook import AsyncWebSocket, WebSocket, WebSocketError


class FakeFeed:
    """A tiny server speaking the exchange's commands, in a thread of its own."""

    def __init__(self):
        self.upgrade_headers = None
        self.commands = []
        self.ready = threading.Event()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)

    async def handler(self, conn):
        self.upgrade_headers = conn.request.headers
        async for raw in conn:
            cmd = json.loads(raw)
            self.commands.append(cmd)
            if cmd["op"] == "subscribe" and cmd["channel"] == "nope":
                await conn.send(json.dumps({"id": cmd["id"], "type": "error", "code": "malformed_request",
                                            "message": "unknown channel"}))
            elif cmd["op"] == "subscribe":
                # data first, then the answer: the client must keep the data for later
                await conn.send(json.dumps({"type": "trade", "ticker": "T", "price": "0.4500"}))
                await conn.send(json.dumps({"id": cmd["id"], "type": "subscribed", "channel": cmd["channel"],
                                            "seq": 88119}))
            elif cmd["op"] == "auth":
                await conn.send(json.dumps({"id": cmd["id"], "type": "authed", "exp": 1790844720}))
            elif cmd["op"] == "ping":
                await conn.send(json.dumps({"id": cmd["id"], "type": "pong"}))

    def _run(self):
        asyncio.set_event_loop(self.loop)

        async def main():
            async with serve(self.handler, "127.0.0.1", 0) as server:
                self.port = server.sockets[0].getsockname()[1]
                self.ready.set()
                await asyncio.Future()

        self.loop.run_until_complete(main())

    def start(self):
        self.thread.start()
        self.ready.wait(5)
        return f"ws://127.0.0.1:{self.port}/v1"


@pytest.fixture
def feed():
    return FakeFeed()


def test_signed_upgrade_subscribe_and_buffering(feed, signer, ed_key):
    url = feed.start()
    with WebSocket(url, signer=signer) as ws:
        reply = ws.subscribe("trades", series_tickers=["BTC-60S"])
        assert reply["type"] == "subscribed" and reply["seq"] == 88119
        assert ws.recv(timeout=2) == {"type": "trade", "ticker": "T", "price": "0.4500"}
        assert ws.ping()["type"] == "pong"
        with pytest.raises(WebSocketError) as caught:
            ws.subscribe("nope")
        assert caught.value.code == "malformed_request"
    headers = feed.upgrade_headers
    ts = headers["OMNIBOOK-TIMESTAMP"]
    ed_key.public_key().verify(base64.b64decode(headers["OMNIBOOK-ACCESS-SIGNATURE"]), f"{ts}GET/v1".encode())
    assert feed.commands[0] == {"id": 1, "op": "subscribe", "channel": "trades", "series_tickers": ["BTC-60S"]}


def test_browser_token_sends_auth_first(feed):
    url = feed.start()
    with WebSocket(url, token="tok"):
        pass
    assert feed.commands[0]["op"] == "auth" and feed.commands[0]["token"] == "tok"
    assert "OMNIBOOK-ACCESS-KEY" not in feed.upgrade_headers


async def test_async_websocket(feed, signer):
    url = feed.start()
    async with AsyncWebSocket(url, signer=signer) as ws:
        reply = await ws.subscribe("private")
        assert reply["seq"] == 88119
        message = await ws.recv(timeout=2)
        assert message["type"] == "trade"
        await ws.request_snapshot("T")
        assert (await ws.ping())["type"] == "pong"
    assert feed.commands[1] == {"id": 2, "op": "snapshot", "ticker": "T"}
