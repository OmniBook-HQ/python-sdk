"""Every trade-API endpoint, written once for both clients.

Each method builds a :class:`Call` and hands it to ``self._send``. The sync client sends it
and returns the answer; the async client returns a coroutine. Paths, fields and query names
are the exchange's own (docs.omnibook.xyz, the trade API), so the docs read straight across.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal
from urllib.parse import quote

from ._base import Call, Number, body, cancel_all_result, num, query

Side = Literal["bid", "ask"]
TimeInForce = Literal["good_till_canceled", "immediate_or_cancel", "fill_or_kill"]


def _seg(value: str | int) -> str:
    return quote(str(value), safe="")


def new_client_order_id() -> str:
    """A fresh client order ID (a UUID4, 36 characters)."""
    return str(uuid.uuid4())


def order_body(
    *,
    ticker: str,
    side: Side,
    count: Number,
    price: Number,
    time_in_force: TimeInForce = "good_till_canceled",
    client_order_id: str | None = None,
    post_only: bool | None = None,
    cancel_order_on_pause: bool | None = None,
    subaccount: int | None = None,
) -> dict[str, Any]:
    """The JSON of one new order, as :meth:`create_order` and batches send it.

    ``price`` is always the YES price in dollars (``"0.4500"``); an ``ask`` sells YES at that
    price, which is buying NO at 1 minus it. ``count`` is whole contracts.
    """
    if side not in ("bid", "ask"):
        raise ValueError("side is 'bid' (buy YES) or 'ask' (sell YES, buy NO)")
    return body(
        {
            "ticker": ticker,
            "client_order_id": client_order_id or new_client_order_id(),
            "side": side,
            "count": num(count, "count"),
            "price": num(price, "price"),
            "time_in_force": time_in_force,
            "post_only": post_only,
            "cancel_order_on_pause": cancel_order_on_pause,
            "subaccount": subaccount,
        }
    )


class Endpoints:
    def _send(self, call: Call) -> Any:  # implemented by each client
        raise NotImplementedError

    # ── Public reads: no credentials ────────────────────────────────────────────────────

    def get_exchange_status(self):
        """``GET /exchange/status``: ``exchange_active``, ``trading_active``."""
        return self._send(Call("GET", "/exchange/status", auth=False))

    def get_series_list(
        self, *, category: str | None = None, tags: str | Sequence[str] | None = None,
        include_volume: bool | None = None,
    ):
        """``GET /series`` → ``{"series": [...]}``."""
        params = query({"category": category, "tags": tags, "include_volume": include_volume})
        return self._send(Call("GET", "/series", params, auth=False))

    def get_series(self, series_ticker: str):
        """``GET /series/{series_ticker}`` → ``{"series": {...}}``."""
        return self._send(Call("GET", f"/series/{_seg(series_ticker)}", auth=False))

    def get_events(
        self, *, series_ticker: str | None = None, status: str | None = None,
        tickers: str | Sequence[str] | None = None, with_nested_markets: bool | None = None,
        min_close_ts: int | None = None, limit: int | None = None, cursor: str | None = None,
    ):
        """``GET /events`` → ``{"events": [...], "cursor": ...}``."""
        params = query({
            "series_ticker": series_ticker, "status": status, "tickers": tickers,
            "with_nested_markets": with_nested_markets, "min_close_ts": min_close_ts,
            "limit": limit, "cursor": cursor,
        })
        return self._send(Call("GET", "/events", params, auth=False))

    def get_event(self, event_ticker: str):
        """``GET /events/{event_ticker}`` → ``{"event": {...}, "markets": [...]}``."""
        return self._send(Call("GET", f"/events/{_seg(event_ticker)}", auth=False))

    def get_markets(
        self, *, series_ticker: str | None = None, event_ticker: str | None = None,
        tickers: str | Sequence[str] | None = None, status: str | None = None,
        min_close_ts: int | None = None, max_close_ts: int | None = None,
        limit: int | None = None, cursor: str | None = None,
    ):
        """``GET /markets`` → ``{"markets": [...], "cursor": ...}``. ``status`` is e.g. ``open``."""
        params = query({
            "series_ticker": series_ticker, "event_ticker": event_ticker, "tickers": tickers,
            "status": status, "min_close_ts": min_close_ts, "max_close_ts": max_close_ts,
            "limit": limit, "cursor": cursor,
        })
        return self._send(Call("GET", "/markets", params, auth=False))

    def get_market(self, ticker: str):
        """``GET /markets/{ticker}`` → ``{"market": {...}}``."""
        return self._send(Call("GET", f"/markets/{_seg(ticker)}", auth=False))

    def get_trades(
        self, *, ticker: str | None = None, min_ts: int | None = None, max_ts: int | None = None,
        limit: int | None = None, cursor: str | None = None,
    ):
        """``GET /markets/trades`` → ``{"trades": [...], "cursor": ...}``. Public trades, 30 days."""
        params = query({"ticker": ticker, "min_ts": min_ts, "max_ts": max_ts, "limit": limit, "cursor": cursor})
        return self._send(Call("GET", "/markets/trades", params, auth=False))

    def get_trade_files(self, date: str):
        """``GET /markets/trades/files?date=YYYY-MM-DD``: that UTC day's trade files."""
        return self._send(Call("GET", "/markets/trades/files", query({"date": date}), auth=False))

    def get_orderbook(self, ticker: str, *, depth: int | None = None):
        """``GET /markets/{ticker}/orderbook``. ``depth`` 0–100; 0 is every level."""
        return self._send(Call("GET", f"/markets/{_seg(ticker)}/orderbook", query({"depth": depth}), auth=False))

    def get_candlesticks(
        self, series_ticker: str, ticker: str, *, start_ts: int, end_ts: int,
        period_interval: Literal[1, 5, 60, 1440],
    ):
        """``GET /series/{series_ticker}/markets/{ticker}/candlesticks``. Minutes: 1, 5, 60, 1440."""
        params = query({"start_ts": start_ts, "end_ts": end_ts, "period_interval": period_interval})
        path = f"/series/{_seg(series_ticker)}/markets/{_seg(ticker)}/candlesticks"
        return self._send(Call("GET", path, params, auth=False))

    def get_indices(self):
        """``GET /indices``: the latest value of every index (BTC, XAU, WTI)."""
        return self._send(Call("GET", "/indices", auth=False))

    def get_index_values(
        self, code: str, *, start_ts: int | None = None, end_ts: int | None = None,
        limit: int | None = None, cursor: str | None = None,
    ):
        """``GET /indices/{code}/values``. ``start_ts``/``end_ts`` are Unix seconds; each value's
        ``ts`` is Unix milliseconds on a 250 ms grid."""
        params = query({"start_ts": start_ts, "end_ts": end_ts, "limit": limit, "cursor": cursor})
        return self._send(Call("GET", f"/indices/{_seg(code)}/values", params, auth=False))

    # ── Orders ──────────────────────────────────────────────────────────────────────────

    def create_order(
        self, *, ticker: str, side: Side, count: Number, price: Number,
        time_in_force: TimeInForce = "good_till_canceled", client_order_id: str | None = None,
        post_only: bool | None = None, cancel_order_on_pause: bool | None = None,
        subaccount: int | None = None,
    ):
        """``POST /portfolio/events/orders``: place one order (``201``).

        ``client_order_id`` is required by the exchange; when omitted a UUID is made for you
        and is in the answer. Reuse the same ID to retry after a ``504``: a repeat is never a
        second order. A "market" order is a limit at your worst price with
        ``immediate_or_cancel`` or ``fill_or_kill``.
        """
        payload = order_body(
            ticker=ticker, side=side, count=count, price=price, time_in_force=time_in_force,
            client_order_id=client_order_id, post_only=post_only,
            cancel_order_on_pause=cancel_order_on_pause, subaccount=subaccount,
        )
        return self._send(Call("POST", "/portfolio/events/orders", json=payload))

    def cancel_order(self, order_id: str | int, *, subaccount: int | None = None):
        """``DELETE /portfolio/events/orders/{order_id}``. ``reduced_by`` ``"0.00"`` means it
        had already finished, which is still a success."""
        path = f"/portfolio/events/orders/{_seg(order_id)}"
        return self._send(Call("DELETE", path, query({"subaccount": subaccount})))

    def cancel_order_by_client_order_id(self, client_order_id: str, *, subaccount: int | None = None):
        """``DELETE /portfolio/events/orders/by_client_order_id/{client_order_id}``."""
        path = f"/portfolio/events/orders/by_client_order_id/{_seg(client_order_id)}"
        return self._send(Call("DELETE", path, query({"subaccount": subaccount})))

    def decrease_order(
        self, order_id: str | int, *, reduce_by: Number | None = None, reduce_to: Number | None = None,
    ):
        """``POST /portfolio/events/orders/{order_id}/decrease``. Give exactly one of
        ``reduce_by`` or ``reduce_to``; ``reduce_to`` is the one that is safe to repeat."""
        if (reduce_by is None) == (reduce_to is None):
            raise ValueError("give exactly one of reduce_by or reduce_to")
        payload = (
            {"reduce_by": num(reduce_by, "reduce_by")} if reduce_by is not None
            else {"reduce_to": num(reduce_to, "reduce_to")}  # type: ignore[arg-type]
        )
        return self._send(Call("POST", f"/portfolio/events/orders/{_seg(order_id)}/decrease", json=payload))

    def batch_create_orders(self, orders: Iterable[Mapping[str, Any]]):
        """``POST /portfolio/events/orders/batched``: 1 to 20 orders (10 on Basic).

        Each element is a dict of :meth:`create_order`'s fields (``ticker``, ``side``,
        ``count``, ``price``…); a missing ``client_order_id`` is filled in. The answer has one
        entry per order, in order; a refused one carries ``error`` and the rest still run.
        """
        built = [order_body(**dict(o)) for o in orders]
        if not 1 <= len(built) <= 20:
            raise ValueError("a batch holds 1 to 20 orders")
        return self._send(Call("POST", "/portfolio/events/orders/batched", json={"orders": built}))

    def batch_cancel_orders(
        self, *, order_ids: Iterable[str | int] = (), client_order_ids: Iterable[str] = (),
    ):
        """``DELETE /portfolio/events/orders/batched``: 1 to 20 cancels, by either kind of ID."""
        entries: list[dict[str, str]] = [{"order_id": str(i)} for i in order_ids]
        entries += [{"client_order_id": str(i)} for i in client_order_ids]
        if not 1 <= len(entries) <= 20:
            raise ValueError("a batch cancel holds 1 to 20 orders")
        return self._send(Call("DELETE", "/portfolio/events/orders/batched", json={"orders": entries}))

    def cancel_all_orders(
        self, *, ticker: str | None = None, series_ticker: str | None = None,
        subaccount: int | None = None,
    ):
        """``DELETE /portfolio/events/orders``: every open order, or one market's or series'.

        Answers once the exchange has recorded it, with ``orders_targeted``; each cancel then
        arrives on the private feed.
        """
        if ticker is not None and series_ticker is not None:
            raise ValueError("filter by ticker or by series_ticker, not both")
        params = query({"ticker": ticker, "series_ticker": series_ticker, "subaccount": subaccount})
        return self._send(Call("DELETE", "/portfolio/events/orders", params, transform=cancel_all_result))

    # ── Private reads ───────────────────────────────────────────────────────────────────

    def get_balance(self, *, subaccount: int | None = None):
        """``GET /portfolio/balance``: ``balance`` (cents), ``balance_dollars``, ``cash_dollars``…"""
        return self._send(Call("GET", "/portfolio/balance", query({"subaccount": subaccount})))

    def get_positions(
        self, *, ticker: str | None = None, event_ticker: str | None = None,
        settlement_status: Literal["unsettled", "settled", "all"] | None = None,
        count_filter: str | Sequence[str] | None = None, subaccount: int | None = None,
        limit: int | None = None, cursor: str | None = None,
    ):
        """``GET /portfolio/positions`` → ``market_positions``, ``event_positions``, ``cursor``."""
        params = query({
            "ticker": ticker, "event_ticker": event_ticker, "settlement_status": settlement_status,
            "count_filter": count_filter, "subaccount": subaccount, "limit": limit, "cursor": cursor,
        })
        return self._send(Call("GET", "/portfolio/positions", params))

    def get_orders(
        self, *, ticker: str | None = None, event_ticker: str | Sequence[str] | None = None,
        status: Literal["resting", "canceled", "executed"] | None = None,
        min_ts: int | None = None, max_ts: int | None = None, client_order_id: str | None = None,
        subaccount: int | None = None, limit: int | None = None, cursor: str | None = None,
    ):
        """``GET /portfolio/orders``. ``client_order_id`` finds one order: the lookup after a 504."""
        params = query({
            "ticker": ticker, "event_ticker": event_ticker, "status": status, "min_ts": min_ts,
            "max_ts": max_ts, "client_order_id": client_order_id, "subaccount": subaccount,
            "limit": limit, "cursor": cursor,
        })
        return self._send(Call("GET", "/portfolio/orders", params))

    def get_order(self, order_id: str | int, *, subaccount: int | None = None):
        """``GET /portfolio/orders/{order_id}`` → ``{"order": {...}}``."""
        return self._send(Call("GET", f"/portfolio/orders/{_seg(order_id)}", query({"subaccount": subaccount})))

    def get_fills(
        self, *, ticker: str | Sequence[str] | None = None, order_id: str | int | None = None,
        min_ts: int | None = None, max_ts: int | None = None, subaccount: int | None = None,
        limit: int | None = None, cursor: str | None = None,
    ):
        """``GET /portfolio/fills`` → ``{"fills": [...], "cursor": ...}``."""
        params = query({
            "ticker": ticker, "order_id": order_id, "min_ts": min_ts, "max_ts": max_ts,
            "subaccount": subaccount, "limit": limit, "cursor": cursor,
        })
        return self._send(Call("GET", "/portfolio/fills", params))

    def get_settlements(
        self, *, ticker: str | None = None, event_ticker: str | None = None,
        min_ts: int | None = None, max_ts: int | None = None, subaccount: int | None = None,
        limit: int | None = None, cursor: str | None = None,
    ):
        """``GET /portfolio/settlements`` → ``{"settlements": [...], "cursor": ...}``."""
        params = query({
            "ticker": ticker, "event_ticker": event_ticker, "min_ts": min_ts, "max_ts": max_ts,
            "subaccount": subaccount, "limit": limit, "cursor": cursor,
        })
        return self._send(Call("GET", "/portfolio/settlements", params))

    def get_deposits(self, *, subaccount: int | None = None, limit: int | None = None, cursor: str | None = None):
        """``GET /portfolio/deposits``."""
        params = query({"subaccount": subaccount, "limit": limit, "cursor": cursor})
        return self._send(Call("GET", "/portfolio/deposits", params))

    def get_withdrawals(self, *, subaccount: int | None = None, limit: int | None = None, cursor: str | None = None):
        """``GET /portfolio/withdrawals``."""
        params = query({"subaccount": subaccount, "limit": limit, "cursor": cursor})
        return self._send(Call("GET", "/portfolio/withdrawals", params))

    def get_ledger(
        self, *, kind: str | None = None, ticker: str | None = None, min_ts: int | None = None,
        max_ts: int | None = None, subaccount: int | None = None, limit: int | None = None,
        cursor: str | None = None,
    ):
        """``GET /portfolio/ledger`` → ``{"entries": [...], "cursor": ...}``: every cash change."""
        params = query({
            "kind": kind, "ticker": ticker, "min_ts": min_ts, "max_ts": max_ts,
            "subaccount": subaccount, "limit": limit, "cursor": cursor,
        })
        return self._send(Call("GET", "/portfolio/ledger", params))

    def get_vault(self, *, subaccount: int | None = None):
        """``GET /portfolio/vault`` → ``{"vaults": [...]}``: your vault share lots."""
        return self._send(Call("GET", "/portfolio/vault", query({"subaccount": subaccount})))

    def get_limits(self, *, subaccount: int | None = None):
        """``GET /account/limits``: the rate tier and the Read and Write buckets."""
        return self._send(Call("GET", "/account/limits", query({"subaccount": subaccount})))

    def create_report(self, *, type: Literal["fills", "ledger", "orders"], from_date: str, to_date: str):
        """``POST /reports`` (``202``) → ``{"report_id": ...}``. Dates are ``YYYY-MM-DD``."""
        return self._send(Call("POST", "/reports", json={"type": type, "from": from_date, "to": to_date}))

    def get_report(self, report_id: str):
        """``GET /reports/{report_id}``: ``status`` ``pending``, ``ready`` (with ``download_url``)
        or ``failed``."""
        return self._send(Call("GET", f"/reports/{_seg(report_id)}"))

    # ── Money: a browser token only (an API key gets 403 not_permitted) ──────────────────

    def create_withdrawal(
        self, *, destination_id: str, amount_dollars: Number, client_withdrawal_id: str | None = None,
        subaccount: int | None = None,
    ):
        """``POST /portfolio/withdrawals`` (``201``). Browser token only."""
        payload = body({
            "client_withdrawal_id": client_withdrawal_id or new_client_order_id(),
            "destination_id": destination_id,
            "amount_dollars": num(amount_dollars, "amount_dollars"),
            "subaccount": subaccount,
        })
        return self._send(Call("POST", "/portfolio/withdrawals", json=payload))

    def transfer_between_subaccounts(
        self, *, from_subaccount: int, to_subaccount: int, amount_dollars: Number | None = None,
        amount_cents: int | None = None, client_transfer_id: str | None = None,
    ):
        """``POST /portfolio/subaccounts/transfer``. Give one of ``amount_dollars`` or
        ``amount_cents``. Browser token only."""
        if (amount_dollars is None) == (amount_cents is None):
            raise ValueError("give exactly one of amount_dollars or amount_cents")
        payload = body({
            "client_transfer_id": client_transfer_id or new_client_order_id(),
            "from_subaccount": from_subaccount,
            "to_subaccount": to_subaccount,
            "amount_dollars": None if amount_dollars is None else num(amount_dollars, "amount_dollars"),
            "amount_cents": amount_cents,
        })
        return self._send(Call("POST", "/portfolio/subaccounts/transfer", json=payload))

    def vault_deposit(self, *, vault_id: int, amount_dollars: Number, client_request_id: str | None = None):
        """``POST /portfolio/vault/deposit``: at least $100. Browser token only."""
        payload = {
            "client_request_id": client_request_id or new_client_order_id(),
            "vault_id": vault_id,
            "amount_dollars": num(amount_dollars, "amount_dollars"),
        }
        return self._send(Call("POST", "/portfolio/vault/deposit", json=payload))

    def vault_redeem(self, *, vault_id: int, amount_dollars: Number, client_request_id: str | None = None):
        """``POST /portfolio/vault/redeem``. Browser token only."""
        payload = {
            "client_request_id": client_request_id or new_client_order_id(),
            "vault_id": vault_id,
            "amount_dollars": num(amount_dollars, "amount_dollars"),
        }
        return self._send(Call("POST", "/portfolio/vault/redeem", json=payload))
