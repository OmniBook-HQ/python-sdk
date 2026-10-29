from decimal import Decimal

from omnibook import OrderBook

T = "BTC-60S-26OCT01-0838"
SNAPSHOT = {
    "type": "book_snapshot", "ticker": T, "book_seq": 5230, "ts_ms": 1,
    "bids": [["0.4500", "1200.00"], ["0.4400", "300.00"]],
    "asks": [["0.4600", "800.00"], ["0.4700", "150.00"]],
}


def update(seq, side, price, count):
    return {"type": "book_update", "ticker": T, "book_seq": seq, "side": side, "price": price, "count": count}


def test_snapshot_then_updates():
    book = OrderBook(T)
    assert not book.synced
    assert book.apply(update(5231, "bid", "0.45", "1.00"))  # before a snapshot: ignored
    assert book.apply(SNAPSHOT) and book.synced
    assert book.best_bid() == (Decimal("0.4500"), Decimal("1200.00"))
    assert book.apply(update(5230, "bid", "0.4500", "1.00"))  # already in the snapshot
    assert book.best_bid()[1] == Decimal("1200.00")
    assert book.apply(update(5231, "bid", "0.4500", "1100.00"))
    assert book.apply(update(5232, "ask", "0.4600", "0.00"))
    assert book.best_ask() == (Decimal("0.4700"), Decimal("150.00"))
    assert book.levels("bid") == [(Decimal("0.45"), Decimal("1100")), (Decimal("0.44"), Decimal("300"))]


def test_gap_unsyncs_until_next_snapshot():
    book = OrderBook(T)
    book.apply(SNAPSHOT)
    assert book.apply(update(5232, "bid", "0.4500", "1.00")) is False
    assert not book.synced
    book.apply({**SNAPSHOT, "book_seq": 5240})
    assert book.synced and book.book_seq == 5240


def test_other_tickers_are_ignored():
    book = OrderBook(T)
    assert book.apply({**SNAPSHOT, "ticker": "OTHER"})
    assert not book.synced
