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
    an = (market.get("local") or {}).get("antam")
    if an and an.get("price"):
        out.append(f"Antam 1 gr Rp {nf(an['price'])}" + (f" ({'+' if an['chg'] >= 0 else '−'}{nf(abs(an['chg']), 1)}%)" if an.get("chg") is not None else ""))
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
    save(state)
    print("brief: sent")


def save(state):
    with open(os.path.join(ROOT, "kabar-state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


NAMES = {"ihsg": "IHSG", "spx": "S&P 500", "gold": "Emas", "brent": "Brent", "usdidr": "USD/IDR", "btc": "Bitcoin"}


def week_change(q, days):
    s = q.get("series") or []
    if len(s) <= days:
        return None
    p, base = q.get("price") or s[-1][1], s[-1 - days][1]
    return (p / base - 1) * 100 if base else None


def weekly():
    """Sunday-evening recap (after 19:00 WIB), once per ISO week."""
    now = datetime.now(timezone.utc).astimezone(WIB)
    week = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
    state = load("kabar-state.json", {})
    force = os.environ.get("WEEKLY_FORCE") == "1"
    if not force and (now.weekday() != 6 or now.hour < 19 or state.get("lastWeekly") == week):
        print("weekly: not due")
        return
    if not os.environ.get("KABAR_TOKEN"):
        print("weekly: KABAR_TOKEN not set")
        return
    snap, market = load("snapshot.json", {}), load("market.json", {})
    fc, alerts = load("forecasts.json", {"items": []}), load("alerts.json", {"items": []})
    lines = []
    hist = snap.get("history") or []
    cut = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    old = next((h for h in hist if h.get("t", "") >= cut), hist[0] if hist else None)
    if old and snap.get("risk") is not None:
        d = snap["risk"] - old.get("risk", snap["risk"])
        lines.append(f"**Indeks risiko {snap['risk']}/100** ({'+' if d >= 0 else '−'}{abs(d)} dalam seminggu) · {snap.get('regimeTitle', '')}")
    moves = []
    for k, n in NAMES.items():
        q = (market.get("quotes") or {}).get(k)
        c = week_change(q, 7 if k == "btc" else 5) if q else None
        if c is not None:
            moves.append(f"{n} {'+' if c >= 0 else '−'}{nf(abs(c), 1)}%")
    if moves:
        lines += ["", "**Seminggu terakhir**", " · ".join(moves)]
    st = [(q.get("name", s), week_change(q, 5)) for s, q in (market.get("stocks") or {}).items()]
    st = sorted([x for x in st if x[1] is not None], key=lambda x: x[1])
    if len(st) >= 2:
        lines.append(f"Saham pantauan terbaik: {st[-1][0]} {'+' if st[-1][1] >= 0 else '−'}{nf(abs(st[-1][1]), 1)}% · terlemah: {st[0][0]} {'+' if st[0][1] >= 0 else '−'}{nf(abs(st[0][1]), 1)}%")
    wk_alerts = [a for a in alerts.get("items", []) if a.get("time", "") >= cut]
    if wk_alerts:
        lines += ["", f"**{len(wk_alerts)} peringatan minggu ini**"] + [f"• {a['title']}" for a in wk_alerts[:5]]
    today = now.date()
    scored = [i for i in fc.get("items", []) if i.get("checked") and i["checked"] >= str(today - timedelta(days=7))]
    due = [i for i in fc.get("items", []) if i.get("status") == "open" and str(today) <= i["due"] <= str(today + timedelta(days=14))]
    if scored or due:
        lines += ["", "**Rapor akurasi**"]
        if scored:
            lines.append(f"Dinilai minggu ini: {sum(i['status'] == 'hit' for i in scored)} kena dari {len(scored)}")
        if due:
            lines.append(f"{len(due)} prakiraan jatuh tempo dalam 2 minggu")
    nxt = sorted([e for e in snap.get("calendar") or [] if str(today) < e.get("d", "") <= str(today + timedelta(days=7))],
                 key=lambda e: (e["d"], e.get("time", "")))
    if nxt:
        lines += ["", "**Agenda minggu depan**"]
        for e in nxt[:8]:
            d = datetime.strptime(e["d"], "%Y-%m-%d")
            lines.append(f"• {HARI[d.weekday()]} {d.day}/{d.month}{' ' + e['time'] if e.get('time') else ''}: {e['t']}" + (" ‼️" if e.get("imp") == "tinggi" else ""))
    lines += ["", "_Bukan nasihat keuangan._"]
    sys.path.insert(0, KABAR_LIB)
    import kabar  # noqa: PLC0415
    kabar.kirim(f"📊 Rekap mingguan · {now.day} {BULAN[now.month - 1]}", "\n".join(lines), saluran=CHANNEL, url=SITE)
    state = load("kabar-state.json", {})
    state["lastWeekly"] = week
    save(state)
    print("weekly: sent")


if __name__ == "__main__":
    main()
    weekly()
