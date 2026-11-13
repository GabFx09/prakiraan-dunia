"""System health monitor: tell the owner in Kabar when something stops working.

Checks (every ~15 minutes, inside the market workflow):
  - agen:   Claude analysis (data/snapshot.json) older than 7 hours
            (usually the Claude usage limit, or the routine failed)
  - harga:  market prices that could not be refreshed (Yahoo down, no backup)
  - berita: headlines older than 3 hours
  - antam:  Antam gold price failing for more than a day

A new problem is reported once, repeated every 12 hours while it lasts, and a
"pulih" (recovered) message is sent when it clears. State lives in
data/kabar-state.json under "health". Needs KABAR_TOKEN.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..", "data")
SITE = "https://gabfx09.github.io/prakiraan-dunia/"
CHANNEL = os.environ.get("KABAR_SALURAN", "Prakiraan Dunia")
KABAR_LIB = os.environ.get("KABAR_LIB", os.path.join(os.path.dirname(__file__), "..", ".kabar"))
REPEAT = timedelta(hours=12)
ROUTINES = "https://claude.ai/code/routines"
ACTIONS = "https://github.com/GabFx09/prakiraan-dunia/actions"


def load(name, default):
    try:
        with open(os.path.join(ROOT, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def ts(s):
    try:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def hours(td):
    return f"{td.total_seconds() / 3600:.0f} jam".replace(".", ",")


def problems(now):
    out = {}
    snap, market, heads = load("snapshot.json", {}), load("market.json", {}), load("headlines.json", {})
    t = ts(snap.get("updatedAt", ""))
    if not t or now - t > timedelta(hours=7):
        age = hours(now - t) if t else "lama"
        out["agen"] = (f"Analisis agen Claude belum diperbarui {age}",
                       f"Biasanya karena kuota Claude habis atau agen gagal. Harga, berita, dan peringatan harga tetap berjalan. Cek: {ROUTINES}")
    stale = [q.get("name", k) for k, q in (market.get("quotes") or {}).items() if q.get("ok") is False]
    if stale:
        out["harga"] = (f"{len(stale)} harga pasar gagal diperbarui",
                        f"{', '.join(stale)}: memakai nilai terakhir. Kemungkinan Yahoo Finance sedang bermasalah. Cek: {ACTIONS}")
    t = ts(heads.get("updatedAt", ""))
    if not t or now - t > timedelta(hours=3):
        out["berita"] = ("Arus berita berhenti diperbarui", f"Google News tidak bisa diambil sejak {hours(now - t) if t else 'lama'} lalu. Cek: {ACTIONS}")
    an = (market.get("local") or {}).get("antam") or {}
    t = ts(an.get("fetchedAt", ""))
    if an and an.get("ok") is False and (not t or now - t > timedelta(hours=24)):
        out["antam"] = ("Harga emas Antam gagal diambil lebih dari sehari", "Sumber emasantam.id mungkin berubah format. Situs menampilkan harga terakhir.")
    return out


def main():
    now = datetime.now(timezone.utc)
    state = load("kabar-state.json", {})
    hs = state.setdefault("health", {})
    found = problems(now)
    msgs = []
    for key, (title, body) in found.items():
        rec = hs.get(key) or {}
        last = ts(rec.get("notified", ""))
        if not last or now - last > REPEAT:
            msgs.append({"judul": f"⚠️ {title}", "isi": body + f"\n\n_Pemantau sistem · {SITE}_", "url": SITE, "prioritas": "normal"})
            hs[key] = {"since": rec.get("since") or now.strftime("%Y-%m-%dT%H:%M:%SZ"), "notified": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    for key in [k for k in hs if k not in found]:
        since = ts(hs[key].get("since", ""))
        msgs.append({"judul": "✅ Pulih: " + {"agen": "analisis agen Claude", "harga": "harga pasar", "berita": "arus berita", "antam": "harga emas Antam"}.get(key, key),
                     "isi": f"Kembali normal{' setelah ' + hours(now - since) if since else ''}.", "url": SITE, "prioritas": "normal"})
        del hs[key]
    print("health:", ", ".join(found) or "sehat", f"· {len(msgs)} pesan")
    if not msgs:
        return
    if not os.environ.get("KABAR_TOKEN"):
        print("health: KABAR_TOKEN not set")
        return
    sys.path.insert(0, KABAR_LIB)
    import kabar  # noqa: PLC0415
    kabar.kirim_banyak(msgs, saluran=CHANNEL)
    with open(os.path.join(ROOT, "kabar-state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
