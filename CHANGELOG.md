# Changelog

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
