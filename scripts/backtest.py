"""Historical check of the volatility-range method, plus today's baseline ranges.

For each asset in data/market.json: at every past day with enough history, build
a range price * exp(±Z * sigma * sqrt(n)) from the trailing 30-day volatility,
and check whether the price n trading days later landed inside. Z = 0.755 gives
a ~55% central interval, the same confidence as the base scenario. A well
calibrated method should land inside ~55% of the time.

Uses 5 years of daily closes from Yahoo Finance (refreshed at most once every
12 hours; otherwise the previous result is kept). Windows are sampled every 5
trading days to limit overlap.

Writes data/backtest.json with the hit rates and today's baseline ranges; the
Claude agent uses those ranges as a starting point for its public targets.
"""
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from fetch_market import HOSTS, SYMBOLS, UA, drop_spikes  # noqa: E402
import urllib.request  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..", "data")
Z = 0.755
WINDOW = 30
HORIZON = {"1b": 21, "3b": 63}          # trading days ahead
HORIZON_24_7 = {"1b": 30, "3b": 92}     # calendar days for assets that trade every day
STEP = 5
REFRESH = timedelta(hours=12)


def history(symbol):
    q = urllib.request.quote(symbol, safe="")
    for host in HOSTS:
        try:
            req = urllib.request.Request(f"{host}/v8/finance/chart/{q}?range=5y&interval=1d", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r)["chart"]["result"][0]
            ts, cl = res.get("timestamp") or [], res["indicators"]["quote"][0].get("close") or []
            ser = [(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"), c) for t, c in zip(ts, cl) if c]
            return [c for _, c in drop_spikes(ser, 0.02 if symbol == "IDR=X" else 0.15)]
        except Exception:  # noqa: BLE001
            continue
    return []


def sd(xs):
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1))


def main():
    with open(os.path.join(ROOT, "market.json"), encoding="utf-8") as f:
        market = json.load(f)
    try:
        with open(os.path.join(ROOT, "backtest.json"), encoding="utf-8") as f:
            old = json.load(f)
        fresh = datetime.now(timezone.utc) - datetime.strptime(old.get("historyAt", "2000-01-01T00:00:00Z"), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) < REFRESH
    except Exception:  # noqa: BLE001
        old, fresh = {}, False
    if fresh and old.get("years") == 5 and os.environ.get("BACKTEST_FORCE") != "1":
        print("backtest: history still fresh, keeping previous result")
        return
    cov, bands, years = {}, {}, {}
    for k, q in market.get("quotes", {}).items():
        a = [c for c in history(SYMBOLS[k][0]) if c and c > 0]
        if len(a) < 300:
            a = [c for _, c in q.get("series", []) if c and c > 0]
        years[k] = round(len(a) / (365 if k == "btc" else 252), 1)
        if len(a) < WINDOW + 25:
            continue
        hz = HORIZON_24_7 if k == "btc" else HORIZON
        cov[k], bands[k] = {}, {}
        for hid, n in hz.items():
            hits = tot = 0
            for i in range(WINDOW, len(a) - n, STEP):
                s = sd([math.log(a[j] / a[j - 1]) for j in range(i - WINDOW + 1, i + 1)])
                lo, hi = a[i] * math.exp(-Z * s * math.sqrt(n)), a[i] * math.exp(Z * s * math.sqrt(n))
                hits += lo <= a[i + n] <= hi
                tot += 1
            cov[k][hid] = {"hit": hits, "total": tot, "rate": round(hits / tot, 3) if tot else None}
            s_now = sd([math.log(a[j] / a[j - 1]) for j in range(len(a) - WINDOW, len(a))])
            p = q.get("price") or a[-1]
            d = 2 if p < 100 else 0
            bands[k][hid] = [round(p * math.exp(-Z * s_now * math.sqrt(n)), d), round(p * math.exp(Z * s_now * math.sqrt(n)), d)]
    out = {
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "historyAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "years": 5, "span": years,
        "method": "rentang volatilitas 55% (z=0,755, volatilitas 30 hari terakhir), diuji tiap 5 hari bursa selama ±5 tahun",
        "target": 0.55, "coverage": cov, "bands": bands,
    }
    with open(os.path.join(ROOT, "backtest.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("backtest:", {k: {h: v["rate"] for h, v in c.items()} for k, c in cov.items()})


if __name__ == "__main__":
    main()
