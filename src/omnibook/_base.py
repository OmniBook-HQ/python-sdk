"""What the sync and async clients share: building requests and reading answers."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from ._signing import Signer
from ._version import __version__
from .environments import API_PREFIX, Environment, resolve
from .errors import OmnibookError, error_for

DEFAULT_TIMEOUT = 10.0  # the gateway waits up to 5 s for the OMS; a client must wait longer
RETRY_STATUSES = frozenset({502, 503})

Number = str | int | Decimal


class Response(dict):
    """A JSON object from the exchange, plus the response's status and headers.

    It is a plain ``dict`` for every other purpose.
    """

    status: int
    headers: httpx.Headers

    def __init__(self, data: Mapping[str, Any] | None, status: int, headers: httpx.Headers):
        super().__init__(data or {})
        self.status = status
        self.headers = headers

    @property
    def event_seq(self) -> int | None:
        """``Omnibook-Event-Seq``: the last account event this answer includes.

        Sent on every successful write and every private read. Compare it with the ``seq``
        of a private WebSocket ``subscribed`` to know the read missed nothing.
        """
        value = self.headers.get("Omnibook-Event-Seq")
        return int(value) if value and value.isdigit() else None


def num(value: Number, field_name: str) -> str:
    """A price, count or money field as the exact text the exchange wants.

    Floats are refused: the exchange never rounds, so neither does this client.
    """
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{field_name}: pass a str, int or Decimal, not {type(value).__name__}")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"{field_name}: {value} is not a finite number")
        return format(value, "f")
    if isinstance(value, str):
        try:
            parsed = Decimal(value.strip())
        except InvalidOperation:
            raise ValueError(f"{field_name}: {value!r} is not a decimal number") from None
        if not parsed.is_finite():
            raise ValueError(f"{field_name}: {value!r} is not a finite number")
        return value.strip()
    raise TypeError(f"{field_name}: pass a str, int or Decimal, not {type(value).__name__}")


def query(params: Mapping[str, Any]) -> dict[str, str]:
    """Drop ``None``; lists become comma-separated; booleans ``true``/``false``."""
    out: dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        elif isinstance(value, (list, tuple, set, frozenset)):
            out[key] = ",".join(str(v) for v in value)
        else:
            out[key] = str(value)
    return out


def body(fields: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in fields.items() if v is not None}


@dataclass
class Call:
    """One HTTP request, before it is sent."""

    method: str
    path: str  # under the API prefix, unless `raw_path` is set
    params: dict[str, str] = field(default_factory=dict)
    json: Any = None
    auth: bool = True
    raw_path: bool = False  # the account service's /auth, /keys, /profile
    transform: Callable[[Response], Any] | None = None

    @property
    def full_path(self) -> str:
        return self.path if self.raw_path else API_PREFIX + self.path


class BaseClient:
    def __init__(
        self,
        *,
        signer: Signer | None = None,
        token: str | None = None,
        environment: Environment | str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 2,
        headers: Mapping[str, str] | None = None,
    ):
        """
        :param signer: a bot's API key (:class:`Signer`). Signs every private request.
        :param token: a browser session token instead, sent as ``Authorization: Bearer``.
            Needed for the paths a key may not use: withdrawals, transfers and the vault.
        :param environment: ``"mainnet"`` (the default, ``trade-api.omnibook.xyz``),
            ``"demo"``, or an :class:`Environment`.
        :param base_url: the REST host, overriding the environment's (no path).
        :param timeout: seconds per request. Keep it above 5: the exchange waits up to 5 s for
            a write before it answers ``504 no_answer``.
        :param max_retries: retries of a *read* after a connection error or a 502/503.
            Writes are never retried by the client: see :class:`~omnibook.errors.NoAnswerError`.
        :param headers: extra headers on every request, such as Cloudflare Access's
            ``CF-Access-Client-Id`` and ``CF-Access-Client-Secret`` for the demo hosts.
        """
        self.environment = resolve(environment)
        self.base_url = (base_url or self.environment.rest_url).rstrip("/")
        self.signer = signer
        self.token = token
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self._headers = {"User-Agent": f"omnibook-python/{__version__}", "Accept": "application/json"}
        self._headers.update(headers or {})

    def _ws_args(self, private: bool | None) -> dict[str, Any]:
        use_private = self.signer is not None if private is None else private
        return {
            "url": self.environment.ws_auth_url if use_private else self.environment.ws_url,
            "signer": self.signer if use_private else None,
            "token": self.token if use_private else None,
            "headers": {k: v for k, v in self._headers.items() if k != "Accept"},
        }

    def _auth_headers(self, call: Call) -> dict[str, str]:
        if not call.auth:
            return {}
        if self.signer is not None:
            return self.signer.headers(call.method, call.full_path)
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        raise OmnibookError(
            f"{call.method} {call.full_path} needs credentials: pass signer= (an API key) or token="
        )

    def _request_kwargs(self, call: Call) -> dict[str, Any]:
        headers = dict(self._headers)
        headers.update(self._auth_headers(call))
        kwargs: dict[str, Any] = {"headers": headers, "params": call.params or None}
        if call.json is not None:
            headers["Content-Type"] = "application/json"
            kwargs["content"] = json.dumps(call.json, separators=(",", ":"))
        return kwargs

    @staticmethod
    def _should_retry(call: Call, attempt: int, max_retries: int, status: int | None) -> bool:
        if call.method != "GET" or attempt >= max_retries:
            return False
        return status is None or status in RETRY_STATUSES

    @staticmethod
    def _read(call: Call, resp: httpx.Response) -> Any:
        data: Any
        if resp.content:
            try:
                data = resp.json()
            except ValueError:
                data = {"code": "", "message": resp.text[:500]}
        else:
            data = {}
        if resp.status_code >= 400:
            raise error_for(resp.status_code, data if isinstance(data, dict) else {}, resp.headers)
        result = Response(data if isinstance(data, dict) else {"data": data}, resp.status_code, resp.headers)
        return call.transform(result) if call.transform else result


def cancel_all_result(resp: Response) -> Response:
    """``204`` with ``Omnibook-Orders-Targeted``: how many open orders the cancel covers."""
    value = resp.headers.get("Omnibook-Orders-Targeted")
    resp["orders_targeted"] = int(value) if value and value.isdigit() else None
    return resp


def items_of(page: Mapping[str, Any], key: str) -> Iterable[Any]:
    return page.get(key) or []
