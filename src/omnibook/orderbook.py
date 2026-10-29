"""Keep a market's book from the ``book_updates`` channel.

The book is the one YES book each market has. Bids are YES bids, asks are YES asks; a NO
price is 1 minus the YES price. The recipe (docs: Public channels):

1. Take the ``book_snapshot``: the book as of ``book_seq`` N.
2. Apply each ``book_update`` whose ``book_seq`` is the last plus 1. It is the level's new
   total, not a change; ``"0.00"`` empties the level.
3. A skipped ``book_seq`` is a gap: ask for a snapshot (or wait for the next one, at most
   5 s away) and drop any update at or below the snapshot's number.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any


class OrderBook:
    """One market's book. Feed it every ``book_snapshot`` and ``book_update`` for its ticker.

    >>> book = OrderBook("BTC-60S-26OCT01-0838")
    >>> for message in ws:
    ...     if message.get("ticker") == book.ticker and not book.apply(message):
    ...         ws.request_snapshot(book.ticker)   # a gap: the book waits for a snapshot
    ...     print(book.best_bid(), book.best_ask())
    """

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.book_seq: int | None = None  # None until a snapshot; also after a gap
        self.ts_ms: int | None = None

    @property
    def synced(self) -> bool:
        return self.book_seq is not None

    def apply(self, message: Mapping[str, Any]) -> bool:
        """Apply one message. Returns ``False`` when a gap was found (the book is then out
        of sync until the next snapshot); ``True`` otherwise, including for messages that
        are not about this book."""
        if message.get("ticker") != self.ticker:
            return True
        kind = message.get("type")
        if kind == "book_snapshot":
            self.bids = {Decimal(p): Decimal(c) for p, c in message.get("bids", [])}
            self.asks = {Decimal(p): Decimal(c) for p, c in message.get("asks", [])}
            self.book_seq = int(message["book_seq"])
            self.ts_ms = message.get("ts_ms")
            return True
        if kind == "book_unavailable":
            self.book_seq = None
            return True
        if kind != "book_update":
            return True
        if self.book_seq is None:
            return True  # waiting for a snapshot; an update alone is no book
        seq = int(message["book_seq"])
        if seq <= self.book_seq:
            return True  # already in the snapshot
        if seq != self.book_seq + 1:
            self.book_seq = None
            return False
        side = self.bids if message["side"] == "bid" else self.asks
        price, count = Decimal(message["price"]), Decimal(message["count"])
        if count == 0:
            side.pop(price, None)
        else:
            side[price] = count
        self.book_seq = seq
        self.ts_ms = message.get("ts_ms")
        return True

    def best_bid(self) -> tuple[Decimal, Decimal] | None:
        """Best (highest) YES bid as ``(price, count)``."""
        return max(self.bids.items()) if self.bids else None

    def best_ask(self) -> tuple[Decimal, Decimal] | None:
        """Best (lowest) YES ask as ``(price, count)``."""
        return min(self.asks.items()) if self.asks else None

    def levels(self, side: str, depth: int | None = None) -> list[tuple[Decimal, Decimal]]:
        """Levels best first: ``side`` is ``bid`` or ``ask``."""
        if side == "bid":
            rows = sorted(self.bids.items(), reverse=True)
        else:
            rows = sorted(self.asks.items())
        return rows if depth is None else rows[:depth]

    def __repr__(self) -> str:
        return f"OrderBook({self.ticker!r}, seq={self.book_seq}, bid={self.best_bid()}, ask={self.best_ask()})"
