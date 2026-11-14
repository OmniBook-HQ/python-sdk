"""Official Python client for the Omnibook exchange trade API.

>>> from omnibook import Client, Signer
>>> client = Client(signer=Signer.from_file("<key id>", "omnibook-api-key.pem"))
>>> client.get_exchange_status()
"""

from . import environments as _environments
from ._base import Response
from ._endpoints import new_client_order_id
from ._signing import Signer, generate_key_pem, signing_text
from ._version import __version__
from .client import AsyncClient, Client
from .environments import MAINNET, SANDBOX, Environment
from .errors import (
    ApiError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    DuplicateClientOrderIdError,
    NoAnswerError,
    NotFoundError,
    OmnibookError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    WebSocketError,
)
from .orderbook import OrderBook
from .websocket import AsyncWebSocket, WebSocket

__all__ = [
    "DEMO",
    "MAINNET",
    "SANDBOX",
    "ApiError",
    "AsyncClient",
    "AsyncWebSocket",
    "AuthenticationError",
    "BadRequestError",
    "Client",
    "ConflictError",
    "DuplicateClientOrderIdError",
    "Environment",
    "NoAnswerError",
    "NotFoundError",
    "OmnibookError",
    "OrderBook",
    "PermissionDeniedError",
    "RateLimitError",
    "Response",
    "ServerError",
    "Signer",
    "WebSocket",
    "WebSocketError",
    "__version__",
    "generate_key_pem",
    "new_client_order_id",
    "signing_text",
]


def __getattr__(name: str):
    # DEMO is retired: still importable, with a DeprecationWarning (see environments.DEMO_RETIRED).
    if name == "DEMO":
        return _environments._demo(stacklevel=3)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
