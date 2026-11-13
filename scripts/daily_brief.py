"""Send the morning brief to the Kabar app once a day (after 08:10 WIB).

Runs inside the market workflow every ~15 minutes; it only sends when today's
brief has not been sent yet. State lives in data/kabar-state.json.
Needs KABAR_TOKEN (and KABAR_VAPID for push). BRIEF_FORCE=1 sends right away.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..", "data")
SITE = "https://gabfx09.github.io/prakiraan-dunia/"
CHANNEL = os.environ.get("KABAR_SALURAN", "Prakiraan Dunia")
KABAR_LIB = os.environ.get("KABAR_LIB", os.path.join(os.path.dirname(__file__), "..", ".kabar"))
WIB = timezone(timedelta(hours=7))
SEND_AFTER = (8, 10)  # WIB, after the 07:57 WIB deep-revision agent run
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


def load(name, default):
    try:
        with open(os.path.join(ROOT, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def nf(x, d=0):
    return f"{x:,.{d}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def price_line(market):
    fmt = {"ihsg": ("IHSG", lambda p: nf(p)), "spx": ("S&P 500", lambda p: nf(p)), "gold": ("Emas", lambda p: "$" + nf(p)),
           "brent": ("Brent", lambda p: "$" + nf(p, 2)), "btc": ("BTC", lambda p: "$" + nf(p)), "usdidr": ("USD/IDR", lambda p: nf(p))}
    out = []
    for k, (n, f) in fmt.items():
        q = market.get("quotes", {}).get(k)
        if not q:
            continue
        c = q.get("chg")
        out.append(f"{n} {f(q['price'])}" + (f" ({'+' if c >= 0 else '−'}{nf(abs(c), 1)}%)" if c is not None else ""))
    return " · ".join(out)


def agenda(snap, today):
    days = {today: "Hari ini", today + timedelta(days=1): "Besok"}
    rows = []
    items = (snap.get("calendar") or []) + [{"d": m["d"], "t": m["t"]} for m in snap.get("milestones") or []]
    seen = set()
    for e in sorted(items, key=lambda x: (x.get("d", ""), x.get("time", ""))):
        try:
            d = datetime.strptime(e["d"], "%Y-%m-%d").date()
        except Exception:  # noqa: BLE001
            continue
        if d in days and e["t"] not in seen:
            seen.add(e["t"])
            rows.append(f"• {days[d]}{' ' + e['time'] if e.get('time') else ''}: {e['t']}")
    return rows


def main():
    now = datetime.now(timezone.utc).astimezone(WIB)
    today = now.date()
    state = load("kabar-state.json", {})
    force = os.environ.get("BRIEF_FORCE") == "1"
    if not force and (state.get("lastBrief") == str(today) or (now.hour, now.minute) < SEND_AFTER):
        print("brief: not due")
        return
    if not os.environ.get("KABAR_TOKEN"):
        print("brief: KABAR_TOKEN not set")
        return
    snap, market, alerts = load("snapshot.json", {}), load("market.json", {}), load("alerts.json", {"items": []})
    lines = [f"**Risiko global {snap.get('risk', '?')}/100** · {snap.get('regimeTitle', '')}", ""]
    lines += [f"• {p}" for p in (snap.get("brief") or {}).get("points", [])]
    lines += ["", "**Harga**", price_line(market)]
    ag = agenda(snap, today)
    if ag:
        lines += ["", "**Agenda**"] + ag
    recent = [a for a in alerts.get("items", []) if a.get("time", "") >= (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")]
    if recent:
        lines += ["", f"**{len(recent)} peringatan dalam 24 jam:**"] + [f"• {a['title']}" for a in recent[:4]]
    lines += ["", "_Bukan nasihat keuangan._"]
    sys.path.insert(0, KABAR_LIB)
    import kabar  # noqa: PLC0415
    kabar.kirim(f"☀️ Ringkasan pagi · {HARI[now.weekday()]}, {now.day} {BULAN[now.month - 1]}", "\n".join(lines),
                saluran=CHANNEL, url=SITE)
    state["lastBrief"] = str(today)
    with open(os.path.join(ROOT, "kabar-state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    print("brief: sent")


if __name__ == "__main__":
    main()
