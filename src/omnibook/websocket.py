"""The live feeds: ``trade-ws`` (public) and ``trade-ws-auth`` (public and private).

Orders are never sent here; the socket only carries data. Commands are JSON objects with
``op`` and an ``id`` that the answer repeats. Messages are JSON objects with ``type``; ignore
a ``type`` or a field you do not know, as the exchange only ever adds them.

Close codes (``ConnectionClosed.rcvd.code``): 1001 reconnect (and read REST on ws-auth),
4001 bad login, 4002 token expired, 4003 key revoked or session ended (stop), 4008 slow
consumer (reconnect and read REST), 4009 too many connections. After any reconnect,
subscribe again: the server keeps nothing about a closed connection.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import time
from collections import deque
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

from websockets.asyncio.client import ClientConnection as AsyncConnection
from websockets.asyncio.client import connect as async_connect
from websockets.sync.client import ClientConnection, connect

from ._signing import Signer
from .errors import OmnibookError, WebSocketError

PUBLIC_CHANNELS = ("book", "book_updates", "trades", "markets", "index")
PRIVATE_CHANNELS = (
    "orders", "fills", "balance", "positions", "ledger", "withdrawals", "settlements", "account", "private",
)

_REPLIES = {"subscribe": "subscribed", "unsubscribe": "unsubscribed", "auth": "authed", "ping": "pong"}


def _subscription(
    channel: str, tickers: Sequence[str] | None, series_tickers: Sequence[str] | None,
    codes: Sequence[str] | None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {"channel": channel}
    if tickers is not None:
        fields["tickers"] = list(tickers)
    if series_tickers is not None:
        fields["series_tickers"] = list(series_tickers)
    if codes is not None:
        fields["codes"] = list(codes)
    return fields


class _Base:
    def __init__(
        self,
        url: str,
        *,
        signer: Signer | None = None,
        token: str | None = None,
        headers: Mapping[str, str] | None = None,
        open_timeout: float = 10.0,
        reply_timeout: float = 10.0,
        **connect_kwargs: Any,
    ):
        self.url = url
        self.signer = signer
        self.token = token
        self.open_timeout = open_timeout
        self.reply_timeout = reply_timeout
        self._headers = dict(headers or {})
        self._connect_kwargs = connect_kwargs
        self._ids = itertools.count(1)
        self._pending: deque[dict[str, Any]] = deque()

    def _upgrade_headers(self) -> dict[str, str]:
        headers = dict(self._headers)
        if self.signer is not None:
            headers.update(self.signer.headers("GET", urlsplit(self.url).path or "/"))
        return headers

    def _command(self, op: str, fields: Mapping[str, Any]) -> tuple[int, str]:
        cid = next(self._ids)
        return cid, json.dumps({"id": cid, "op": op, **fields}, separators=(",", ":"))

    @staticmethod
    def _parse(raw: str | bytes) -> dict[str, Any]:
        message = json.loads(raw)
        return message if isinstance(message, dict) else {"type": "unknown", "data": message}

    @staticmethod
    def _is_reply(message: dict[str, Any], cid: int, op: str) -> bool:
        if message.get("id") != cid:
            return False
        if message.get("type") == "error":
            raise WebSocketError(message)
        return message.get("type") == _REPLIES.get(op, message.get("type"))


class WebSocket(_Base):
    """A blocking WebSocket connection.

    >>> with client.websocket() as ws:
    ...     ws.subscribe("book_updates", series_tickers=["BTC-60S"])
    ...     ws.subscribe("private")
    ...     for message in ws:
    ...         print(message["type"])
    """

    _conn: ClientConnection | None = None

    def connect(self) -> WebSocket:
        self._conn = connect(
            self.url, additional_headers=self._upgrade_headers(), open_timeout=self.open_timeout,
            **self._connect_kwargs,
        )
        if self.token and self.signer is None:
            self.auth(self.token)
        return self

    def __enter__(self) -> WebSocket:
        return self.connect()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()

    @property
    def connection(self) -> ClientConnection:
        if self._conn is None:
            raise OmnibookError("not connected: use `with client.websocket() as ws` or call connect()")
        return self._conn

    def send(self, op: str, **fields: Any) -> dict[str, Any]:
        """Send a command and wait for its answer. Data that arrives first is kept for
        :meth:`recv`. A refused command raises :class:`~omnibook.errors.WebSocketError`."""
        cid, text = self._command(op, fields)
        self.connection.send(text)
        deadline = time.monotonic() + self.reply_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"no answer to {op} (id {cid}) within {self.reply_timeout} s")
            message = self._parse(self.connection.recv(timeout=remaining))
            if self._is_reply(message, cid, op):
                return message
            self._pending.append(message)

    def subscribe(
        self, channel: str, *, tickers: Sequence[str] | None = None,
        series_tickers: Sequence[str] | None = None, codes: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Start a channel. Market channels take ``tickers`` or ``series_tickers``; ``index``
        takes ``codes``. A private ``subscribed`` carries ``seq``: a REST read whose
        ``event_seq`` is at least that misses nothing."""
        return self.send("subscribe", **_subscription(channel, tickers, series_tickers, codes))

    def unsubscribe(
        self, channel: str, *, tickers: Sequence[str] | None = None,
        series_tickers: Sequence[str] | None = None, codes: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        return self.send("unsubscribe", **_subscription(channel, tickers, series_tickers, codes))

    def request_snapshot(self, ticker: str) -> None:
        """Ask for a full ``book_snapshot`` on ``book_updates`` after a gap (ws-auth only).
        The snapshot arrives as an ordinary message."""
        _, text = self._command("snapshot", {"ticker": ticker})
        self.connection.send(text)

    def auth(self, token: str) -> dict[str, Any]:
        """A browser token: the first command on ws-auth, and again after each renewal."""
        self.token = token
        return self.send("auth", token=token)

    def ping(self) -> dict[str, Any]:
        return self.send("ping")

    def recv(self, timeout: float | None = None) -> dict[str, Any]:
        """The next message. Raises ``TimeoutError`` after ``timeout`` seconds, and
        ``websockets.ConnectionClosed`` when the server closes the connection."""
        if self._pending:
            return self._pending.popleft()
        return self._parse(self.connection.recv(timeout=timeout))

    def __iter__(self) -> Iterator[dict[str, Any]]:
        while True:
            yield self.recv()


class AsyncWebSocket(_Base):
    """The asyncio connection: ``async with client.websocket() as ws: async for m in ws``."""

    _conn: AsyncConnection | None = None

    async def connect(self) -> AsyncWebSocket:
        self._conn = await async_connect(
            self.url, additional_headers=self._upgrade_headers(), open_timeout=self.open_timeout,
            **self._connect_kwargs,
        )
        if self.token and self.signer is None:
            await self.auth(self.token)
        return self

    async def __aenter__(self) -> AsyncWebSocket:
        return await self.connect()

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()

    @property
    def connection(self) -> AsyncConnection:
        if self._conn is None:
            raise OmnibookError("not connected: use `async with client.websocket() as ws`")
        return self._conn

    async def send(self, op: str, **fields: Any) -> dict[str, Any]:
        cid, text = self._command(op, fields)
        await self.connection.send(text)

        async def answer() -> dict[str, Any]:
            while True:
                message = self._parse(await self.connection.recv())
                if self._is_reply(message, cid, op):
                    return message
                self._pending.append(message)

        try:
            return await asyncio.wait_for(answer(), self.reply_timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"no answer to {op} (id {cid}) within {self.reply_timeout} s") from None

    async def subscribe(
        self, channel: str, *, tickers: Sequence[str] | None = None,
        series_tickers: Sequence[str] | None = None, codes: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        return await self.send("subscribe", **_subscription(channel, tickers, series_tickers, codes))

    async def unsubscribe(
        self, channel: str, *, tickers: Sequence[str] | None = None,
        series_tickers: Sequence[str] | None = None, codes: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        return await self.send("unsubscribe", **_subscription(channel, tickers, series_tickers, codes))

    async def request_snapshot(self, ticker: str) -> None:
        _, text = self._command("snapshot", {"ticker": ticker})
        await self.connection.send(text)

    async def auth(self, token: str) -> dict[str, Any]:
        self.token = token
        return await self.send("auth", token=token)

    async def ping(self) -> dict[str, Any]:
        return await self.send("ping")

    async def recv(self, timeout: float | None = None) -> dict[str, Any]:
        if self._pending:
            return self._pending.popleft()
        if timeout is None:
            return self._parse(await self.connection.recv())
        try:
            return self._parse(await asyncio.wait_for(self.connection.recv(), timeout))
        except asyncio.TimeoutError:
            raise TimeoutError(f"no message within {timeout} s") from None

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        return self._messages()

    async def _messages(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            yield await self.recv()
