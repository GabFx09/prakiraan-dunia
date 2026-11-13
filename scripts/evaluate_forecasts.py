"""Score Prakiraan Dunia's forecasts against real closing prices.

1. Every open forecast whose due date has passed is scored with the last
   closing price on or before the due date from data/market.json:
   "hit" if inside [low, high], otherwise "miss".
2. New forecasts are registered from the base-case `targets` in
   data/snapshot.json (horizons 1b and 3b), at most once per 7 days per
   asset and horizon, so the record grows steadily without flooding.
"""
import json
import os
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..", "data")
DAYS = {"1b": 30, "3b": 92}
MAX_ITEMS = 500


def load(name, default):
    try:
        with open(os.path.join(ROOT, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def close_on_or_before(series, day):
    best = None
    for d, c in series:
        if d <= day:
            best = c
        else:
            break
    return best


def main():
    market = load("market.json", {"quotes": {}})
    snap = load("snapshot.json", {})
    fc = load("forecasts.json", {"items": []})
    items = fc.setdefault("items", [])
    today = datetime.now(timezone.utc).date()
    changed = False

    for it in items:
        if it.get("status") != "open" or it["due"] > str(today):
            continue
        q = market.get("quotes", {}).get(it["key"])
        if not q or not q.get("series"):
            continue
        actual = close_on_or_before(q["series"], it["due"])
        if actual is None:
            continue
        it["actual"] = actual
        it["status"] = "hit" if it["low"] <= actual <= it["high"] else "miss"
        it["checked"] = str(today)
        changed = True

    for h in snap.get("horizons", []):
        if h.get("id") not in DAYS:
            continue
        for t in h.get("targets", []) or []:
            key, lo, hi = t.get("key"), t.get("low"), t.get("high")
            if key not in market.get("quotes", {}) or lo is None or hi is None or lo >= hi:
                continue
            recent = [i for i in items if i["key"] == key and i["h"] == h["id"]
                      and date.fromisoformat(i["made"]) > today - timedelta(days=7)]
            if recent:
                continue
            items.append({
                "id": f"{today}-{h['id']}-{key}", "made": str(today),
                "due": str(today + timedelta(days=DAYS[h["id"]])), "h": h["id"], "key": key,
                "low": lo, "high": hi, "status": "open", "actual": None,
            })
            changed = True

    if changed:
        items.sort(key=lambda i: (i["made"], i["id"]))
        fc["items"] = items[-MAX_ITEMS:]
        fc["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(os.path.join(ROOT, "forecasts.json"), "w", encoding="utf-8") as f:
            json.dump(fc, f, ensure_ascii=False, indent=1)
    done = [i for i in items if i["status"] != "open"]
    hits = sum(1 for i in done if i["status"] == "hit")
    print(f"forecasts: {len(items)} total, {len(done)} scored, {hits} hit, changed={changed}")


if __name__ == "__main__":
    main()
