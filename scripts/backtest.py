"""Historical check of the volatility-range method, plus today's baseline ranges.

For each asset in data/market.json: at every past day with enough history, build
a range price * exp(±Z * sigma * sqrt(n)) from the trailing 30-day volatility,
and check whether the price n trading days later landed inside. Z = 0.755 gives
a ~55% central interval, the same confidence as the base scenario. A well
calibrated method should land inside ~55% of the time.

Writes data/backtest.json with the hit rates and today's baseline ranges; the
Claude agent uses those ranges as a starting point for its public targets.
"""
import json
import math
import os
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..", "data")
Z = 0.755
WINDOW = 30
HORIZON = {"1b": 21, "3b": 63}          # trading days ahead
HORIZON_24_7 = {"1b": 30, "3b": 92}     # calendar days for assets that trade every day


def sd(xs):
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1))


def main():
    with open(os.path.join(ROOT, "market.json"), encoding="utf-8") as f:
        market = json.load(f)
    cov, bands = {}, {}
    for k, q in market.get("quotes", {}).items():
        a = [c for _, c in q.get("series", []) if c and c > 0]
        if len(a) < WINDOW + 25:
            continue
        hz = HORIZON_24_7 if k == "btc" else HORIZON
        cov[k], bands[k] = {}, {}
        for hid, n in hz.items():
            hits = tot = 0
            for i in range(WINDOW, len(a) - n):
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
        "method": "rentang volatilitas 55% (z=0,755, volatilitas 30 hari terakhir)",
        "target": 0.55, "coverage": cov, "bands": bands,
    }
    with open(os.path.join(ROOT, "backtest.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("backtest:", {k: {h: v["rate"] for h, v in c.items()} for k, c in cov.items()})


if __name__ == "__main__":
    main()
