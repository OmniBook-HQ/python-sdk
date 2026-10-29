"""Where the exchange is: its REST host and its two WebSocket hosts."""

from __future__ import annotations

from dataclasses import dataclass

API_PREFIX = "/trade-api/v2"


@dataclass(frozen=True)
class Environment:
    """One exchange deployment.

    ``rest_url`` is the host only, with no path: trading paths go under ``/trade-api/v2``
    and the account service's under ``/auth``, ``/keys`` and ``/profile`` on the same host.
    """

    name: str
    rest_url: str
    ws_url: str
    ws_auth_url: str

    @property
    def api_base(self) -> str:
        return self.rest_url.rstrip("/") + API_PREFIX


MAINNET = Environment(
    name="mainnet",
    rest_url="https://trade-api.omnibook.xyz",
    ws_url="wss://trade-ws.omnibook.xyz/v1",
    ws_auth_url="wss://trade-ws-auth.omnibook.xyz/v1",
)

DEMO = Environment(
    name="demo",
    rest_url="https://demo-api.omnibook.xyz",
    ws_url="wss://demo-ws.omnibook.xyz/v1",
    ws_auth_url="wss://demo-ws-auth.omnibook.xyz/v1",
)

ENVIRONMENTS = {env.name: env for env in (MAINNET, DEMO)}


def resolve(env: Environment | str | None) -> Environment:
    if env is None:
        return MAINNET
    if isinstance(env, Environment):
        return env
    try:
        return ENVIRONMENTS[env.lower()]
    except KeyError:
        raise ValueError(f"unknown environment {env!r}: one of {sorted(ENVIRONMENTS)}") from None
