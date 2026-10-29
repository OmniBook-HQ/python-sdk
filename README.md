# Omnibook Python SDK

The official Python client for the [Omnibook](https://omnibook.xyz) exchange trade API at
`trade-api.omnibook.xyz`. It covers every REST endpoint, sync and async, and the live
WebSocket feeds. API keys are Ed25519 or RSA, and the SDK signs every request for you.

```bash
pip install omnibook
```

> **Upgrading from 1.x?** Version 2 is for the new exchange (`trade-api.omnibook.xyz`,
> paths under `/trade-api/v2`, tickers, prices as YES dollars). Version 1 spoke to the testnet
> paper API (`api.omnibook.xyz/v1`, HMAC secrets, `market_id` and ticks) and is not compatible.
> Bots that still use the testnet API should pin `omnibook<2`. [CHANGELOG](CHANGELOG.md) has the details.

## Get an API key

1. Sign in at [trade.omnibook.xyz](https://trade.omnibook.xyz) and deposit.
2. Open **Settings → API keys** and create a key. The browser makes the key pair and saves the
   private half as a `.pem` file. Omnibook never sees that file.
3. Copy the **key ID** the page shows.

You can also make the pair yourself and register only the public half:

```python
from omnibook import generate_key_pem
private_pem, public_pem = generate_key_pem()   # paste public_pem into the web app
```

## Quick start

```python
from omnibook import Client, Signer

signer = Signer.from_file("<key id>", "~/omnibook-api-key.pem")

with Client(signer=signer) as client:
    print(client.get_exchange_status())

    markets = client.get_markets(series_ticker="BTC-60S", status="open")["markets"]
    ticker = markets[0]["ticker"]
    print(client.get_orderbook(ticker, depth=5))

    order = client.create_order(
        ticker=ticker,
        side="bid",            # bid buys YES; ask sells YES (buys NO at 1 - price)
        count=10,              # whole contracts
        price="0.4500",        # always the YES price, in dollars, as text
        time_in_force="good_till_canceled",
        post_only=True,
    )
    print(order["order_id"], order["client_order_id"])

    client.cancel_order(order["order_id"])
    print(client.get_balance()["balance_dollars"])
```

Public reads (`get_markets`, `get_orderbook`, `get_trades` and the rest) need no key.
`Client()` with no signer is enough for them.

`Signer.from_env()` reads `OMNIBOOK_API_KEY_ID`, and either `OMNIBOOK_PRIVATE_KEY_PATH` or
`OMNIBOOK_PRIVATE_KEY` (the PEM text itself).

## Environments

| | REST | Public feed | Private feed |
|---|---|---|---|
| `mainnet` (default) | `https://trade-api.omnibook.xyz` | `wss://trade-ws.omnibook.xyz/v1` | `wss://trade-ws-auth.omnibook.xyz/v1` |
| `demo` | `https://demo-api.omnibook.xyz` | `wss://demo-ws.omnibook.xyz/v1` | `wss://demo-ws-auth.omnibook.xyz/v1` |

```python
client = Client(signer=signer, environment="demo",
                headers={"CF-Access-Client-Id": "...", "CF-Access-Client-Secret": "..."})
client = Client(signer=signer, base_url="http://127.0.0.1:8080")   # your own host
```

The demo hosts sit behind Cloudflare Access, so send its service-token headers there.

## Numbers are text

Prices, counts and money go to the exchange as decimal strings and come back as strings. The SDK
accepts `str`, `int` or `Decimal`. It **refuses `float`**, because the exchange never rounds and
neither does the SDK. Read answers with `Decimal(order["fill_cost_dollars"])`.

## Retries are safe when you reuse the client order ID

`create_order` makes a UUID `client_order_id` when you pass none, and returns it in the answer.
A timeout is not a failure. If you get `NoAnswerError` (`504`) or the connection drops on a
write, the order may exist. Look it up and retry with the **same** ID:

```python
from omnibook import NoAnswerError, DuplicateClientOrderIdError, new_client_order_id

coid = new_client_order_id()
try:
    order = client.create_order(ticker=ticker, side="bid", count=1, price="0.40", client_order_id=coid)
except NoAnswerError:
    found = client.get_orders(client_order_id=coid)["orders"]
    order = found[0] if found else client.create_order(
        ticker=ticker, side="bid", count=1, price="0.40", client_order_id=coid)
except DuplicateClientOrderIdError as e:
    order = e.existing       # the first order, as it stands now
```

The client retries **reads** after a connection error or a `502`/`503` (`max_retries=2`). It
never retries a write on its own.

## Errors

A status of 400 or above raises an `ApiError` subclass. Each one carries `status`, `code` (the
exchange's reject code, such as `insufficient_funds`), `message`, `details`, `body` and
`headers`.

| Status | Exception |
|---|---|
| 400 | `BadRequestError` |
| 401 | `AuthenticationError` (`unauthenticated`, `timestamp_out_of_window`, `key_revoked`) |
| 403 | `PermissionDeniedError` |
| 404 | `NotFoundError` |
| 409 | `ConflictError`, and `DuplicateClientOrderIdError` for `duplicate_client_order_id` |
| 429 | `RateLimitError`, with `.retry_after_ms` |
| 5xx | `ServerError`, and `NoAnswerError` for `504` |

Your clock must be within 5 seconds of the exchange's, or every signed request fails with
`timestamp_out_of_window`.

## Responses

Each method returns a `Response`. It is a `dict` of the exchange's JSON, with `.status`,
`.headers` and `.event_seq` (`Omnibook-Event-Seq`, the last account event the answer includes).
Field names are the exchange's own, so the [API docs](https://docs.omnibook.xyz) read straight
across.

Lists are paged with `limit` and `cursor`. `paginate` walks every page:

```python
for fill in client.paginate(client.get_fills, "fills", ticker=ticker):
    print(fill["trade_id"], fill["count_fp"])
```

## Async

```python
import asyncio
from omnibook import AsyncClient, Signer

async def main():
    async with AsyncClient(signer=Signer.from_env()) as client:
        print(await client.get_balance())
        async for market in client.paginate(client.get_markets, "markets", status="open"):
            print(market["ticker"])

asyncio.run(main())
```

## WebSocket

```python
from omnibook import Client, OrderBook, Signer

client = Client(signer=Signer.from_env())
book = OrderBook(ticker)

with client.websocket() as ws:            # trade-ws-auth: public and private channels
    ws.subscribe("book_updates", tickers=[ticker])
    sub = ws.subscribe("private")         # orders, fills, balance, positions, ledger…
    for message in ws:
        if message["type"] in ("book_snapshot", "book_update") and not book.apply(message):
            ws.request_snapshot(ticker)   # a gap in book_seq: ask for a fresh book
        elif message["type"] == "fill":
            print("filled", message["count"], "at", message["price"])
```

- `client.websocket(private=False)` opens the public feed, which needs no key. `book`,
  `trades`, `markets` and `index` work there. `book_updates`, `snapshot` and the private
  channels are on `ws-auth` only.
- Market channels take `tickers` or `series_tickers`. A series subscription also covers each
  new market as it opens.
- `index` takes `codes`, for example `["BTC"]`.
- The private feed has no snapshot. After every connect, read open orders, balance and positions
  over REST, then apply the feed. A REST answer whose `event_seq` is at least the `seq` of the
  private `subscribed` misses nothing.
- After any reconnect, subscribe again. The close codes are in `omnibook.websocket`'s docstring.

The async version is `async with async_client.websocket() as ws:` / `async for message in ws:`.

## Browser-only endpoints

Withdrawals, transfers between sub-accounts and vault deposits and redemptions refuse API keys
(`403 not_permitted`). They take the 15-minute browser session token: `Client(token=...)`.

## Development

```bash
uv venv && uv pip install -e ".[dev]"
pytest
ruff check .
```

The live check reads public data only, unless you also set a key:

```bash
OMNIBOOK_LIVE=1 python examples/smoke.py
```

## License

MIT
