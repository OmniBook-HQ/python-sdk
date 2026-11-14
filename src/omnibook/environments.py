"""Where the exchange is: its REST host and its two WebSocket hosts."""

from __future__ import annotations

import warnings
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

# Retired: the demo hosts no longer answer. Kept so code that names it still imports and runs;
# reading ``DEMO`` or resolving ``"demo"`` warns. Test on SANDBOX instead.
_DEMO = Environment(
    name="demo",
    rest_url="https://demo-api.omnibook.xyz",
    ws_url="wss://demo-ws.omnibook.xyz/v1",
    ws_auth_url="wss://demo-ws-auth.omnibook.xyz/v1",
)

# The public API sandbox: mainnet's code with test money only, wiped every day at 00:00 UTC.
SANDBOX = Environment(
    name="sandbox",
    rest_url="https://test-api.omnibook.xyz",
    ws_url="wss://test-ws.omnibook.xyz/v1",
    ws_auth_url="wss://test-ws-auth.omnibook.xyz/v1",
)

ENVIRONMENTS = {env.name: env for env in (MAINNET, SANDBOX, _DEMO)}

DEMO_RETIRED = (
    "the demo environment is retired: demo-api., demo-ws. and demo-ws-auth.omnibook.xyz no longer answer. "
    'Test on the sandbox instead: environment="sandbox" (omnibook.SANDBOX). '
    "DEMO will be removed in a future major version."
)


def _demo(stacklevel: int) -> Environment:
    """``_DEMO``, with a DeprecationWarning. ``stacklevel`` as in ``warnings.warn`` (1 is this function)."""
    warnings.warn(DEMO_RETIRED, DeprecationWarning, stacklevel=stacklevel)
    return _DEMO


def __getattr__(name: str) -> Environment:
    if name == "DEMO":
        return _demo(stacklevel=3)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _resolve(env: Environment | str | None, stacklevel: int) -> Environment:
    if env is None:
        return MAINNET
    if isinstance(env, Environment):
        found = env
    else:
        try:
            found = ENVIRONMENTS[env.lower()]
        except KeyError:
            raise ValueError(f"unknown environment {env!r}: one of {sorted(ENVIRONMENTS)}") from None
    if found is _DEMO:
        _demo(stacklevel=stacklevel + 1)
    return found


def resolve(env: Environment | str | None) -> Environment:
    """The :class:`Environment` for a name (``"mainnet"``, ``"sandbox"``), an Environment, or None (mainnet)."""
    return _resolve(env, stacklevel=3)
