"""Errors the client raises.

Every failed request (status 400 or above) has the body
``{"code": "...", "message": "...", "details": "..."}``; ``code`` is the exchange's
lower-case reject code. :class:`ApiError` carries all of it, and its subclasses let you
catch by status.
"""

from __future__ import annotations

from typing import Any

import httpx


class OmnibookError(Exception):
    """Base class for every error this package raises."""


class ApiError(OmnibookError):
    """The exchange answered with a status of 400 or above."""

    def __init__(self, status: int, body: dict[str, Any], headers: httpx.Headers | None = None):
        self.status = status
        self.body = body
        self.headers = headers or httpx.Headers()
        self.code: str = str(body.get("code") or "")
        self.message: str = str(body.get("message") or "")
        self.details: str = str(body.get("details") or "")
        text = f"{status} {self.code or 'error'}"
        if self.message:
            text += f": {self.message}"
        if self.details:
            text += f" ({self.details})"
        super().__init__(text)

    @property
    def retry_after_ms(self) -> int | None:
        """``Omnibook-Retry-After-Ms``, sent with a write ``429`` and with ``409 order_held``."""
        value = self.headers.get("Omnibook-Retry-After-Ms")
        return int(value) if value and value.isdigit() else None


class BadRequestError(ApiError):
    """400: the request is malformed or refused (``invalid_number``, ``insufficient_funds``…)."""


class AuthenticationError(ApiError):
    """401: ``unauthenticated``, ``timestamp_out_of_window``, ``key_revoked``, ``token_expired``…"""


class PermissionDeniedError(ApiError):
    """403: ``not_permitted`` (a key on a browser-only path), ``account_suspended``…"""


class NotFoundError(ApiError):
    """404: ``not_found``, ``unknown_market``, ``unknown_order``, ``order_not_on_book``."""


class ConflictError(ApiError):
    """409: ``market_halted``, ``post_only_cross``, ``order_held``, ``duplicate_client_order_id``…"""


class DuplicateClientOrderIdError(ConflictError):
    """409 ``duplicate_client_order_id``: the ID was used in the last 10 minutes.

    Nothing new happened. The first order (or withdrawal) as it stands now is in
    :attr:`existing`.
    """

    @property
    def existing(self) -> dict[str, Any] | None:
        return self.body.get("order") or self.body.get("withdrawal")


class RateLimitError(ApiError):
    """429: the account's Read or Write bucket cannot take this request."""


class ServerError(ApiError):
    """5xx: ``exchange_busy``, ``matching_unavailable``, ``book_full``…"""


class NoAnswerError(ServerError):
    """504 ``no_answer``: the write was not confirmed within 5 seconds. **It may have landed.**

    Look it up (``get_orders(client_order_id=...)``), then retry with the *same* client ID.
    The body names the request: ``client_order_id``, ``order_id``, ``client_withdrawal_id``,
    ``client_transfer_id`` or ``orders``.
    """


class WebSocketError(OmnibookError):
    """A WebSocket command was refused: ``{"type": "error", "code": ..., "message": ...}``."""

    def __init__(self, message: dict[str, Any]):
        self.body = message
        self.code: str = str(message.get("code") or "")
        self.message: str = str(message.get("message") or "")
        super().__init__(f"{self.code}: {self.message}" if self.message else self.code)


_BY_STATUS: dict[int, type[ApiError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    429: RateLimitError,
}


def error_for(status: int, body: dict[str, Any], headers: httpx.Headers | None = None) -> ApiError:
    code = body.get("code")
    if code == "duplicate_client_order_id":
        return DuplicateClientOrderIdError(status, body, headers)
    if status == 504 or code == "no_answer":
        return NoAnswerError(status, body, headers)
    cls = _BY_STATUS.get(status) or (ServerError if status >= 500 else ApiError)
    return cls(status, body, headers)
