"""Build data/alerts.json and push new important alerts to phones.

Sources, checked every run of the market workflow (~15 min):
  1. Price shocks from data/market.json (big daily moves).
  2. Major-news alerts written by the Claude agent in data/snapshot.json `alerts`.
  3. A jump of 8+ points in the agent's global risk index.

New alerts are sent once to the owner's Kabar app (https://gabfx09.github.io/kabar/),
channel "Prakiraan Dunia", using kabar.py from the GabFx09/kabar repo. Needs the
KABAR_TOKEN (gist scope) and KABAR_VAPID secrets; without KABAR_TOKEN nothing is
sent and alerts stay pending (recent ones go out once the secret is added).
KABAR_DRY=1 marks alerts as sent without sending.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..", "data")
CHANNEL = os.environ.get("KABAR_SALURAN", "Prakiraan Dunia")
DRY = os.environ.get("KABAR_DRY") == "1"
KABAR_LIB = os.environ.get("KABAR_LIB", os.path.join(os.path.dirname(__file__), "..", ".kabar"))
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


def send_kabar(batch):
    """Send alerts to Kabar in one write (one combined push notification)."""
    sys.path.insert(0, KABAR_LIB)
    import kabar  # noqa: PLC0415 - provided by the workflow checkout of GabFx09/kabar
    msgs = []
    for a in batch:
        icon = "🔴" if a["level"] == "kritis" else "🟠"
        isi = (a.get("body") or "").strip()
        isi += ("\n\n" if isi else "") + f"_{a['level'].upper()} · {a['kind']}_ · Buka: {SITE}#peringatan"
        msgs.append({"judul": f"{icon} {a['title']}", "isi": isi, "url": a.get("url") or SITE,
                     "prioritas": "tinggi" if a["level"] == "kritis" else "normal"})
    kabar.kirim_banyak(msgs, saluran=CHANNEL)


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
    pushed, batch = [], []
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
        batch.append(a)
    if batch and DRY:
        pushed = [a["id"] for a in batch]
    elif batch and os.environ.get("KABAR_TOKEN"):
        try:
            send_kabar(batch)
            pushed = [a["id"] for a in batch]
        except Exception as e:  # noqa: BLE001
            print("kabar send failed:", e)
    elif batch:
        print(f"{len(batch)} alert(s) pending: KABAR_TOKEN not set")
    sent.update(pushed)
    ordered = sorted(items.values(), key=lambda x: x["time"], reverse=True)[:MAX_ITEMS]
    keep_ids = {i["id"] for i in ordered}
    out = {"updatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "channel": CHANNEL, "items": ordered, "sent": sorted(s for s in sent if s in keep_ids)}
    if added or pushed or not os.path.exists(os.path.join(ROOT, "alerts.json")):
        with open(os.path.join(ROOT, "alerts.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"alerts: {len(ordered)} total, {len(added)} new, {len(pushed)} pushed{' (dry)' if DRY else ''} to Kabar '{CHANNEL}'")


if __name__ == "__main__":
    main()
