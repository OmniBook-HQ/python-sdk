"""The REST clients: :class:`Client` (blocking) and :class:`AsyncClient` (asyncio)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import httpx

from ._base import BaseClient, Call, Response, items_of
from ._endpoints import Endpoints

_BACKOFF_S = 0.25


class Client(Endpoints, BaseClient):
    """Blocking client for the Omnibook trade API.

    >>> from omnibook import Client, Signer
    >>> client = Client(signer=Signer.from_file("<key id>", "~/omnibook-api-key.pem"))
    >>> client.get_balance()["balance_dollars"]

    Every method returns a :class:`~omnibook.Response`, a ``dict`` of the exchange's JSON
    with ``.status``, ``.headers`` and ``.event_seq``. A status of 400 or above raises an
    :class:`~omnibook.errors.ApiError` subclass.
    """

    def __init__(self, *args: Any, http_client: httpx.Client | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._http = http_client or httpx.Client(base_url=self.base_url, timeout=self.timeout)
        self._owns_http = http_client is None

    def _send(self, call: Call) -> Any:
        attempt = 0
        while True:
            # Signed afresh on each attempt: the timestamp must be within 5 s of the server's.
            kwargs = self._request_kwargs(call)
            try:
                resp = self._http.request(call.method, call.full_path, **kwargs)
            except httpx.TransportError:
                if not self._should_retry(call, attempt, self.max_retries, None):
                    raise
            else:
                if not self._should_retry(call, attempt, self.max_retries, resp.status_code):
                    return self._read(call, resp)
            attempt += 1
            time.sleep(_BACKOFF_S * 2 ** (attempt - 1))

    def paginate(self, method: Callable[..., Response], items: str, **kwargs: Any) -> Iterator[Any]:
        """Every item of a list endpoint, following ``cursor`` to the last page.

        >>> for fill in client.paginate(client.get_fills, "fills", ticker="BTC-60S-26OCT01-0838"):
        ...     print(fill["trade_id"])
        """
        cursor = kwargs.pop("cursor", None)
        while True:
            page = method(cursor=cursor, **kwargs)
            yield from items_of(page, items)
            cursor = page.get("cursor")
            if not cursor:
                return

    def websocket(self, *, private: bool | None = None, **kwargs: Any):
        """A blocking :class:`~omnibook.websocket.WebSocket` on this client's environment.

        ``private`` picks ``ws-auth`` (public and private channels; needs the signer) or the
        public host. By default it is private when the client has a signer.
        """
        from .websocket import WebSocket

        return WebSocket(**self._ws_args(private), **kwargs)

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncClient(Endpoints, BaseClient):
    """The same API as :class:`Client`, for asyncio: ``await client.get_balance()``."""

    def __init__(self, *args: Any, http_client: httpx.AsyncClient | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._http = http_client or httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        self._owns_http = http_client is None

    async def _send(self, call: Call) -> Any:
        attempt = 0
        while True:
            kwargs = self._request_kwargs(call)
            try:
                resp = await self._http.request(call.method, call.full_path, **kwargs)
            except httpx.TransportError:
                if not self._should_retry(call, attempt, self.max_retries, None):
                    raise
            else:
                if not self._should_retry(call, attempt, self.max_retries, resp.status_code):
                    return self._read(call, resp)
            attempt += 1
            await asyncio.sleep(_BACKOFF_S * 2 ** (attempt - 1))

    async def paginate(self, method: Callable[..., Any], items: str, **kwargs: Any) -> AsyncIterator[Any]:
        """``async for`` every item of a list endpoint, following ``cursor``."""
        cursor = kwargs.pop("cursor", None)
        while True:
            page = await method(cursor=cursor, **kwargs)
            for item in items_of(page, items):
                yield item
            cursor = page.get("cursor")
            if not cursor:
                return

    def websocket(self, *, private: bool | None = None, **kwargs: Any):
        """An :class:`~omnibook.websocket.AsyncWebSocket`: ``async with client.websocket() as ws``."""
        from .websocket import AsyncWebSocket

        return AsyncWebSocket(**self._ws_args(private), **kwargs)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
