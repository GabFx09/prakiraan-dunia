"""Build data/alerts.json and push new important alerts to phones.

Sources, checked every run of the market workflow (~15 min):
  1. Price shocks from data/market.json (big daily moves).
  2. Major-news alerts written by the Claude agent in data/snapshot.json `alerts`.
  3. A jump of 8+ points in the agent's global risk index.

New alerts are published once to the public ntfy.sh topic (free push app,
no account) so subscribers get a phone notification even when the site is
closed. Set NTFY_TOPIC to change the topic, or NTFY_DRY=1 to skip sending.
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..", "data")
TOPIC = os.environ.get("NTFY_TOPIC", "prakiraan-dunia-gfx09")
DRY = os.environ.get("NTFY_DRY") == "1"
SITE = "https://gabfx09.github.io/prakiraan-dunia/"
MAX_ITEMS = 60
SEND_WINDOW = timedelta(hours=6)

# daily move (percent) that counts as a shock; double it = "kritis"
SHOCK = {"btc": 7, "spx": 3, "ihsg": 3, "brent": 5, "gold": 3, "usdidr": 1.5}
NAMES = {"btc": "Bitcoin", "spx": "S&P 500", "ihsg": "IHSG", "brent": "Minyak Brent", "gold": "Emas", "usdidr": "Dolar AS terhadap rupiah", "ust10": "Imbal hasil obligasi AS 10 thn"}


def load(name, default):
    try:
        with open(os.path.join(ROOT, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def nf(x, d=0):
    s = f"{x:,.{d}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def price_alerts(market, now):
    out = []
    day = now.strftime("%Y%m%d")
    for k, th in SHOCK.items():
        q = market.get("quotes", {}).get(k)
        if not q or q.get("chg") is None or not q.get("ok", True):
            continue
        chg = float(q["chg"])
        if abs(chg) < th:
            continue
        up = chg > 0
        if k == "usdidr":
            title = f"Rupiah {'melemah' if up else 'menguat'} tajam: USD/IDR {nf(q['price'])} ({'+' if up else '−'}{nf(abs(chg), 2)}%)"
        else:
            title = f"{NAMES[k]} {'melonjak' if up else 'anjlok'} {nf(abs(chg), 1)}% dalam sehari"
        out.append({
            "id": f"px-{k}-{day}-{'up' if up else 'down'}", "time": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": "kritis" if abs(chg) >= 2 * th else "penting", "kind": "harga", "key": k,
            "title": title,
            "body": f"Harga terakhir {nf(q['price'], 2 if k in ('brent',) else 0)}. Pergerakan sebesar ini jarang terjadi; cek panel sinyal dan prakiraan sebelum mengambil keputusan.",
            "url": SITE + "#" + k,
        })
    q = market.get("quotes", {}).get("ust10")
    if q and q.get("prev") is not None:
        bps = round((q["price"] - q["prev"]) * 100)
        if abs(bps) >= 20:
            out.append({
                "id": f"px-ust10-{day}-{'up' if bps > 0 else 'down'}", "time": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "level": "kritis" if abs(bps) >= 35 else "penting", "kind": "harga", "key": "ust10",
                "title": f"Imbal hasil obligasi AS 10 thn {'naik' if bps > 0 else 'turun'} {abs(bps)} bps ke {nf(q['price'], 2)}%",
                "body": "Pergerakan yield sebesar ini biasanya menggerakkan saham, emas, dan rupiah.", "url": SITE + "#ust10",
            })
    return out


def risk_alert(snap):
    h = snap.get("history") or []
    if len(h) < 2:
        return []
    a, b = h[-2].get("risk"), h[-1].get("risk")
    if a is None or b is None or abs(b - a) < 8:
        return []
    return [{
        "id": f"risk-{h[-1]['t']}", "time": h[-1]["t"], "level": "kritis" if abs(b - a) >= 12 else "penting", "kind": "risiko",
        "title": f"Indeks risiko global {'naik' if b > a else 'turun'} {abs(b - a)} poin ke {b}/100",
        "body": snap.get("riskNote") or snap.get("regimeTitle") or "", "url": SITE + "#kondisi",
    }]


def agent_alerts(snap):
    out = []
    for a in snap.get("alerts") or []:
        if not a.get("id") or not a.get("title"):
            continue
        out.append({"id": "news-" + str(a["id"]).removeprefix("news-"), "time": a.get("time") or snap.get("updatedAt"),
                    "level": a.get("level") if a.get("level") in ("kritis", "penting") else "penting", "kind": "berita",
                    "title": a["title"][:120], "body": (a.get("body") or "")[:300],
                    "url": a["url"] if str(a.get("url", "")).startswith("https://") else SITE + "#peringatan"})
    return out


def send(a):
    payload = {
        "topic": TOPIC, "title": ("🔴 " if a["level"] == "kritis" else "🟠 ") + a["title"], "message": a["body"] or a["title"],
        "priority": 5 if a["level"] == "kritis" else 4, "tags": ["chart_with_downwards_trend" if a["kind"] == "harga" else "newspaper"],
        "click": a["url"], "actions": [{"action": "view", "label": "Buka Prakiraan Dunia", "url": SITE + "#peringatan"}],
    }
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def main():
    now = datetime.now(timezone.utc)
    market, snap = load("market.json", {}), load("snapshot.json", {})
    state = load("alerts.json", {"items": [], "sent": []})
    items = {i["id"]: i for i in state.get("items", [])}
    fresh = price_alerts(market, now) + risk_alert(snap) + agent_alerts(snap)
    added = [a for a in fresh if a["id"] not in items]
    for a in added:
        items[a["id"]] = a
    sent = set(state.get("sent", []))
    pushed = []
    for a in sorted(items.values(), key=lambda x: x["time"]):
        if a["id"] in sent:
            continue
        try:
            t = datetime.strptime(a["time"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            t = now
        if now - t > SEND_WINDOW:
            sent.add(a["id"])  # too old to notify; just record it
            continue
        if DRY:
            pushed.append(a["id"]); sent.add(a["id"]); continue
        try:
            send(a)
            pushed.append(a["id"]); sent.add(a["id"])
        except Exception as e:  # noqa: BLE001
            print("send failed:", a["id"], e)
    ordered = sorted(items.values(), key=lambda x: x["time"], reverse=True)[:MAX_ITEMS]
    keep_ids = {i["id"] for i in ordered}
    out = {"updatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "topic": TOPIC, "items": ordered, "sent": sorted(s for s in sent if s in keep_ids)}
    if added or pushed or not os.path.exists(os.path.join(ROOT, "alerts.json")):
        with open(os.path.join(ROOT, "alerts.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"alerts: {len(ordered)} total, {len(added)} new, {len(pushed)} pushed{' (dry)' if DRY else ''}")


if __name__ == "__main__":
    main()
