import base64
import json

import httpx
import pytest

from omnibook import (
    AsyncClient,
    AuthenticationError,
    Client,
    DuplicateClientOrderIdError,
    NoAnswerError,
    OmnibookError,
    RateLimitError,
)

BASE = "https://trade-api.omnibook.xyz"


def make(handler, **kwargs):
    http = httpx.Client(base_url=BASE, transport=httpx.MockTransport(handler))
    return Client(http_client=http, **kwargs)


def make_async(handler, **kwargs):
    http = httpx.AsyncClient(base_url=BASE, transport=httpx.MockTransport(handler))
    return AsyncClient(http_client=http, **kwargs)


def test_default_environment_is_trade_api():
    client = Client()
    assert client.base_url == BASE
    assert client.environment.ws_auth_url == "wss://trade-ws-auth.omnibook.xyz/v1"
    assert Client(environment="demo").base_url == "https://demo-api.omnibook.xyz"


def test_public_read_sends_no_credentials(signer):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        return httpx.Response(200, json={"exchange_active": True, "trading_active": True})

    status = make(handler, signer=signer).get_exchange_status()
    assert status["trading_active"] is True
    assert seen["url"] == BASE + "/trade-api/v2/exchange/status"
    assert "OMNIBOOK-ACCESS-KEY" not in seen["headers"]


def test_private_read_is_signed_over_the_path_without_query(signer, ed_key):
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(200, json={"orders": [], "cursor": ""}, headers={"Omnibook-Event-Seq": "88119"})

    page = make(handler, signer=signer).get_orders(status="resting", limit=10, event_ticker=["A", "B"])
    request = seen["request"]
    assert request.url.path == "/trade-api/v2/portfolio/orders"
    assert dict(request.url.params) == {"status": "resting", "limit": "10", "event_ticker": "A,B"}
    ts = request.headers["OMNIBOOK-TIMESTAMP"]
    ed_key.public_key().verify(
        base64.b64decode(request.headers["OMNIBOOK-ACCESS-SIGNATURE"]),
        f"{ts}GET/trade-api/v2/portfolio/orders".encode(),
    )
    assert page.event_seq == 88119
    assert page.status == 200


def test_create_order_sends_text_numbers_and_a_client_order_id(signer):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["method"] = request.method
        return httpx.Response(201, json={"order_id": "7781", **seen["body"]})

    order = make(handler, signer=signer).create_order(
        ticker="BTC-60S-26OCT01-0838", side="bid", count=10, price="0.4500", post_only=True
    )
    body = seen["body"]
    assert seen["method"] == "POST"
    assert body["count"] == "10" and body["price"] == "0.4500"
    assert body["time_in_force"] == "good_till_canceled"
    assert len(body["client_order_id"]) == 36
    assert "cancel_order_on_pause" not in body
    assert order.status == 201


def test_create_order_refuses_a_float(signer):
    client = make(lambda r: httpx.Response(500), signer=signer)
    with pytest.raises(TypeError):
        client.create_order(ticker="X", side="bid", count=1, price=0.45)


def test_duplicate_client_order_id_carries_the_first_order(signer):
    first = {"order_id": "7781", "client_order_id": "q-1"}

    def handler(request):
        return httpx.Response(
            409, json={"code": "duplicate_client_order_id", "message": "duplicate", "details": "", "order": first}
        )

    with pytest.raises(DuplicateClientOrderIdError) as caught:
        make(handler, signer=signer).create_order(
            ticker="X", side="ask", count="1", price="0.5", client_order_id="q-1"
        )
    assert caught.value.existing == first
    assert caught.value.status == 409


def test_no_answer_is_raised_and_writes_are_not_retried(signer):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(504, json={"code": "no_answer", "message": "no answer", "client_order_id": "q-9"})

    with pytest.raises(NoAnswerError) as caught:
        make(handler, signer=signer).create_order(
            ticker="X", side="bid", count="1", price="0.5", client_order_id="q-9"
        )
    assert caught.value.body["client_order_id"] == "q-9"
    assert len(calls) == 1


def test_reads_are_retried_on_503(signer, monkeypatch):
    monkeypatch.setattr("omnibook.client._BACKOFF_S", 0)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(503, json={"code": "exchange_busy"})
        return httpx.Response(200, json={"balance": 100})

    assert make(handler, signer=signer).get_balance()["balance"] == 100
    assert len(calls) == 3
    # each attempt is signed afresh
    assert all("OMNIBOOK-ACCESS-SIGNATURE" in c.headers for c in calls)


def test_rate_limit_retry_after(signer):
    def handler(request):
        return httpx.Response(
            429, json={"code": "rate_limited", "message": "rate limited"}, headers={"Omnibook-Retry-After-Ms": "40"}
        )

    with pytest.raises(RateLimitError) as caught:
        make(handler, signer=signer).cancel_order("7781")
    assert caught.value.retry_after_ms == 40


def test_401_maps_to_authentication_error(signer):
    def handler(request):
        return httpx.Response(401, json={"code": "timestamp_out_of_window", "message": "", "details": ""})

    with pytest.raises(AuthenticationError) as caught:
        make(handler, signer=signer).get_balance()
    assert caught.value.code == "timestamp_out_of_window"


def test_cancel_all_reads_orders_targeted(signer):
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(204, headers={"Omnibook-Orders-Targeted": "7"})

    result = make(handler, signer=signer).cancel_all_orders(series_ticker="BTC-60S")
    assert result["orders_targeted"] == 7
    assert seen["request"].method == "DELETE"
    assert dict(seen["request"].url.params) == {"series_ticker": "BTC-60S"}


def test_cancel_all_refuses_two_filters(signer):
    with pytest.raises(ValueError):
        make(lambda r: httpx.Response(204), signer=signer).cancel_all_orders(ticker="A", series_ticker="B")


def test_batches(signer):
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(201, json={"orders": []})

    client = make(handler, signer=signer)
    client.batch_create_orders([
        {"ticker": "X", "side": "bid", "count": 1, "price": "0.40"},
        {"ticker": "X", "side": "ask", "count": 2, "price": "0.60", "client_order_id": "q-2"},
    ])
    client.batch_cancel_orders(order_ids=["7782"], client_order_ids=["q-3"])
    (m1, p1, b1), (m2, p2, b2) = seen
    assert (m1, p1) == ("POST", "/trade-api/v2/portfolio/events/orders/batched")
    assert b1["orders"][1]["client_order_id"] == "q-2" and b1["orders"][0]["count"] == "1"
    assert (m2, b2) == ("DELETE", {"orders": [{"order_id": "7782"}, {"client_order_id": "q-3"}]})
    with pytest.raises(ValueError):
        client.batch_create_orders([])


def test_decrease_needs_exactly_one(signer):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    client = make(handler, signer=signer)
    client.decrease_order("7781", reduce_to=0)
    assert seen["body"] == {"reduce_to": "0"}
    with pytest.raises(ValueError):
        client.decrease_order("7781")


def test_paginate_follows_cursor(signer):
    pages = {None: (["a", "b"], "c1"), "c1": (["c"], "")}

    def handler(request):
        items, cursor = pages[request.url.params.get("cursor")]
        return httpx.Response(200, json={"fills": items, "cursor": cursor})

    client = make(handler, signer=signer)
    assert list(client.paginate(client.get_fills, "fills", ticker="X")) == ["a", "b", "c"]


def test_token_auth_and_missing_credentials():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(201, json={"withdrawal_id": "1", "status": "processing"})

    make(handler, token="tok").create_withdrawal(destination_id="d-1", amount_dollars="25.00")
    assert seen["auth"] == "Bearer tok"
    with pytest.raises(OmnibookError):
        make(handler).get_balance()


def test_path_segments_are_escaped(signer):
    seen = {}

    def handler(request):
        seen["path"] = request.url.raw_path
        return httpx.Response(200, json={})

    make(handler, signer=signer).cancel_order_by_client_order_id("a/b?c")
    assert seen["path"] == b"/trade-api/v2/portfolio/events/orders/by_client_order_id/a%2Fb%3Fc"


async def test_async_client(signer):
    def handler(request):
        if request.url.path.endswith("/markets"):
            cursor = request.url.params.get("cursor")
            return httpx.Response(
                200, json={"markets": [{"ticker": cursor or "first"}], "cursor": "" if cursor else "next"}
            )
        return httpx.Response(200, json={"balance": 5}, headers={"Omnibook-Event-Seq": "3"})

    async with make_async(handler, signer=signer) as client:
        balance = await client.get_balance()
        assert balance["balance"] == 5 and balance.event_seq == 3
        tickers = [m["ticker"] async for m in client.paginate(client.get_markets, "markets", status="open")]
        assert tickers == ["first", "next"]
