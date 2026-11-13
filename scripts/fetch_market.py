"""Fetch market prices for Prakiraan Dunia and write data/market.json.

Runs in GitHub Actions every 15 minutes. Uses Yahoo Finance's public chart
endpoint. If a symbol fails, the previous value is kept so the site never
shows an empty reading.
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "market.json")

SYMBOLS = {
    "spx": ("^GSPC", "S&P 500"),
    "ihsg": ("^JKSE", "IHSG"),
    "gold": ("GC=F", "Emas (futures)"),
    "brent": ("BZ=F", "Minyak Brent"),
    "usdidr": ("IDR=X", "USD/IDR"),
    "ust10": ("^TNX", "Obligasi AS 10 thn"),
    "btc": ("BTC-USD", "Bitcoin"),
}
# Watchlist: large, liquid stocks (data only, not recommendations). Edit freely.
STOCKS = {
    "BBCA.JK": "Bank Central Asia", "BBRI.JK": "Bank Rakyat Indonesia", "BMRI.JK": "Bank Mandiri",
    "TLKM.JK": "Telkom Indonesia", "ASII.JK": "Astra International", "ANTM.JK": "Aneka Tambang",
    "NVDA": "Nvidia", "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
}
HOSTS = ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"]
UA = "Mozilla/5.0"


# Yahoo's FX feed sometimes prints bad ticks; drop points this far from their neighbours.
SPIKE = {"IDR=X": 0.02}


def drop_spikes(series, limit):
    out = []
    for i, (d, c) in enumerate(series):
        nb = [x[1] for x in series[max(0, i - 3):i] + series[i + 1:i + 4]]
        if nb:
            nb.sort()
            med = nb[len(nb) // 2]
            if med and abs(c / med - 1) > limit:
                continue
        out.append((d, c))
    return out


def fetch(symbol):
    q = urllib.request.quote(symbol, safe="")
    last_err = None
    for attempt in range(3):
        for host in HOSTS:
            url = f"{host}/v8/finance/chart/{q}?range=6mo&interval=1d"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = json.load(r)
                res = data["chart"]["result"][0]
                meta = res["meta"]
                ts = res.get("timestamp") or []
                closes = res["indicators"]["quote"][0].get("close") or []
                series = [
                    (datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"), round(c, 4))
                    for t, c in zip(ts, closes)
                    if c is not None
                ]
                series = drop_spikes(series, SPIKE.get(symbol, 0.15))
                price = meta.get("regularMarketPrice")
                if price is None and series:
                    price = series[-1][1]
                prev = series[-2][1] if len(series) >= 2 else meta.get("chartPreviousClose")
                return {
                    "price": round(float(price), 4),
                    "prev": round(float(prev), 4) if prev else None,
                    "chg": round((price / prev - 1) * 100, 2) if prev else None,
                    "time": datetime.fromtimestamp(meta.get("regularMarketTime", time.time()), timezone.utc).isoformat().replace("+00:00", "Z"),
                    "series": series[-130:],
                    "currency": meta.get("currency"),
                }
            except Exception as e:  # noqa: BLE001 - keep trying other hosts
                last_err = e
        time.sleep(2 + attempt * 3)
    raise RuntimeError(f"{symbol}: {last_err}")


def main():
    try:
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f)
    except Exception:  # noqa: BLE001
        old = {"quotes": {}}

    quotes, errors = {}, []
    for key, (sym, name) in SYMBOLS.items():
        try:
            q = fetch(sym)
            q.update({"symbol": sym, "name": name, "ok": True})
            quotes[key] = q
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
            prev = old.get("quotes", {}).get(key)
            if prev:
                prev["ok"] = False
                quotes[key] = prev

    if not quotes:
        raise SystemExit("No market data fetched: " + "; ".join(errors))

    stocks = {}
    for sym, name in STOCKS.items():
        try:
            q = fetch(sym)
            q.update({"symbol": sym, "name": name, "ok": True})
            stocks[sym] = q
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
            prev = old.get("stocks", {}).get(sym)
            if prev:
                prev["ok"] = False
                stocks[sym] = prev

    out = {
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Yahoo Finance (data dapat tertunda hingga 15 menit)",
        "quotes": quotes,
        "stocks": stocks,
        "errors": errors,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"ok: {len(quotes) + len(stocks) - len(errors)}/{len(SYMBOLS) + len(STOCKS)} fresh", *errors, sep="\n")


if __name__ == "__main__":
    main()
