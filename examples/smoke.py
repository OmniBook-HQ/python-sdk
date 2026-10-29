"""A live check against the exchange. Reads only; it never places an order.

    OMNIBOOK_LIVE=1 python examples/smoke.py

With OMNIBOOK_API_KEY_ID and OMNIBOOK_PRIVATE_KEY_PATH set it also reads the account and
opens the private feed.
"""

import os
import sys

from omnibook import Client, Signer


def main() -> None:
    if not os.environ.get("OMNIBOOK_LIVE"):
        sys.exit("set OMNIBOOK_LIVE=1 to call the live exchange")
    signer = Signer.from_env() if os.environ.get("OMNIBOOK_API_KEY_ID") else None
    env = os.environ.get("OMNIBOOK_ENV", "mainnet")

    with Client(signer=signer, environment=env) as client:
        print("status   ", dict(client.get_exchange_status()))
        series = client.get_series_list()["series"]
        print("series   ", [s["ticker"] for s in series])
        markets = client.get_markets(status="open", limit=5)["markets"]
        print("markets  ", [m["ticker"] for m in markets])
        print("indices  ", [(i["code"], i["value"]) for i in client.get_indices()["indices"]])
        if markets:
            m = markets[0]
            book = client.get_orderbook(m["ticker"], depth=3)
            print("orderbook", m["ticker"], dict(book))
            print("trades   ", len(client.get_trades(ticker=m["ticker"], limit=5)["trades"]))

        with client.websocket(private=False) as ws:
            print("ws public", ws.subscribe("index", codes=["BTC"]))
            print("ws first ", ws.recv(timeout=10))

        if signer:
            balance = client.get_balance()
            print("balance  ", balance["balance_dollars"], "event_seq", balance.event_seq)
            print("orders   ", len(client.get_orders(status="resting")["orders"]))
            with client.websocket() as ws:
                print("ws private", ws.subscribe("private"))


if __name__ == "__main__":
    main()
