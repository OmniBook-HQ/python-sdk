# Changelog

## 2.1.0 (2026-11-14)

Added:

- `SANDBOX`, the public API sandbox: `Client(environment="sandbox")` or `environment=omnibook.SANDBOX`.
  REST on `https://test-api.omnibook.xyz`, feeds on `wss://test-ws.omnibook.xyz/v1` and
  `wss://test-ws-auth.omnibook.xyz/v1`. Same API as mainnet with test money only; everything,
  API keys included, resets every day at 00:00 UTC and at any other restart of the sandbox.
  The default stays `mainnet`.
  On 2.0.0, pass the same hosts as `Environment(name="sandbox", ...)` (README, "Testing on the sandbox").

Deprecated:

- `DEMO` / `environment="demo"`: the demo hosts (`demo-api.`, `demo-ws.`, `demo-ws-auth.omnibook.xyz`)
  are retired and no longer answer. Reading `omnibook.DEMO` (or `omnibook.environments.DEMO`) and
  resolving `"demo"` still work but emit a `DeprecationWarning` pointing at the caller; use
  `"sandbox"`. `DEMO` will be removed in a future major version. Importing `omnibook` does not warn.
  `DEMO` is no longer in `omnibook.__all__`, so `from omnibook import *` neither warns nor brings it in,
  and the error for an unknown environment names only `mainnet` and `sandbox`.

## 2.0.0 (2026-10-28)

A new client for the new Omnibook exchange at `trade-api.omnibook.xyz`. It supersedes 1.x, which
was written for the testnet paper API and lived in `OmniBook-HQ/python-sdk-v1`.

**Breaking: nothing from 1.x carries over unchanged.**

| | 1.x | 2.0 |
|---|---|---|
| Host | `api.omnibook.xyz/v1` (testnet) | `trade-api.omnibook.xyz/trade-api/v2` (mainnet), `demo-api.` (demo) |
| Credentials | `api_key` + HMAC `api_secret` | `Signer`: key ID + Ed25519 or RSA private key (`.pem` from the web app) |
| Markets | `market_id`, rounds, `tick` | `ticker`, series and events, `price` as YES dollars (`"0.4500"`) |
| Orders | `place_order(side="buy", outcome="yes", tick=…)` | `create_order(side="bid", price="0.45", count=…)` |
| WebSocket | `wss://api.omnibook.xyz/v1/ws`, `cmd`/`params` | `trade-ws` and `trade-ws-auth`, `op` commands, `book` / `book_updates` / private channels |

Added:

- Every trade-API endpoint, in `Client` and `AsyncClient`: public reads, orders (place, cancel,
  decrease, batches, cancel-all), private reads, reports, withdrawals, transfers and the vault.
- Request signing (`Signer`, `signing_text`, `generate_key_pem`).
- Typed errors per status, with `NoAnswerError` and `DuplicateClientOrderIdError` for safe retries.
- `Response.event_seq`, `paginate`, and retries of reads after a `502`/`503`.
- `WebSocket` and `AsyncWebSocket`, with signed upgrades, command replies and buffering.
- `OrderBook`, which keeps a book from `book_updates` and detects gaps.

Testnet bots should pin `omnibook<2`.
