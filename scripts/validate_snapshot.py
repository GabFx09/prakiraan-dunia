"""Reject a malformed snapshot before it reaches the public site."""
import json
import sys

REQUIRED = ["updatedAt", "risk", "regimeTitle", "regimeText", "riskNote", "readings", "history",
            "news", "drivers", "horizons", "assets", "model", "cycles", "milestones"]
HORIZONS = ["1b", "3b", "6b", "1t", "3t", "5t"]
MODEL_IDS = ["dep", "sbn", "gold", "usd", "idx", "glob", "btc"]
STANCES = {"add", "hold", "care", "cut"}


def fail(msg):
    print("TIDAK VALID:", msg)
    sys.exit(1)


def main(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        fail(f"bukan JSON: {e}")
    for k in REQUIRED:
        if k not in d:
            fail(f"kunci '{k}' hilang")
    if not (0 <= int(d["risk"]) <= 100):
        fail("risk di luar 0-100")
    if len(d["readings"]) < 5:
        fail("readings terlalu sedikit")
    ids = [h.get("id") for h in d["horizons"]]
    if ids != HORIZONS:
        fail(f"horizons harus {HORIZONS}, dapat {ids}")
    for h in d["horizons"]:
        sc = h.get("sc", [])
        if [s.get("k") for s in sc] != ["base", "bull", "bear"]:
            fail(f"skenario {h['id']} harus base/bull/bear")
        total = sum(int(s.get("p", 0)) for s in sc)
        if total != 100:
            fail(f"peluang {h['id']} berjumlah {total}, harus 100")
    for h in d["horizons"]:
        for t in h.get("targets", []) or []:
            if t.get("key") not in {"spx", "ihsg", "gold", "brent", "usdidr", "ust10", "btc"}:
                fail(f"target {h['id']} punya key tidak dikenal: {t.get('key')}")
            if not (float(t["low"]) < float(t["high"])):
                fail(f"target {h['id']}/{t['key']}: low harus < high")
    for p in d.get("riskParts", []) or []:
        if not (0 <= int(p.get("v", -1)) <= 100):
            fail(f"riskParts '{p.get('k')}' di luar 0-100")
    for a in d.get("alerts", []) or []:
        if not a.get("id") or not a.get("title") or a.get("level") not in ("kritis", "penting"):
            fail(f"alert tidak valid: {a}")
        if a.get("url") and not str(a["url"]).startswith("https://"):
            fail(f"alert url harus https: {a.get('id')}")
    b = d.get("brief")
    if b is not None and (not isinstance(b.get("points"), list) or not (1 <= len(b["points"]) <= 6)):
        fail("brief.points harus 1-6 butir")
    for e in d.get("calendar", []) or []:
        if not e.get("d") or not e.get("t") or e.get("imp", "sedang") not in ("tinggi", "sedang", "rendah"):
            fail(f"kalender tidak valid: {e}")
        if e.get("url") and not str(e["url"]).startswith("https://"):
            fail(f"kalender url harus https: {e.get('t')}")
    for a in d["assets"]:
        if len(a.get("s", [])) != 6 or not set(a["s"]) <= STANCES:
            fail(f"aset '{a.get('n')}' punya sikap tidak valid")
    mids = [a.get("id") for a in d["model"].get("assets", [])]
    if mids != MODEL_IDS:
        fail(f"model.assets harus {MODEL_IDS}")
    for a in d["model"]["assets"]:
        if len(a.get("mu", [])) != 3 or not all(-0.9 <= float(x) <= 1.5 for x in a["mu"]):
            fail(f"mu untuk {a['id']} tidak masuk akal")
        if not (0 <= float(a.get("sig", -1)) <= 1.5):
            fail(f"sig untuk {a['id']} tidak masuk akal")
    for c in d["cycles"]:
        if not (0 <= float(c.get("pos", -1)) <= 100) or len(c.get("phases", [])) < 2:
            fail(f"siklus '{c.get('id')}' tidak valid")
    for n in d["news"]:
        if not str(n.get("url", "")).startswith("https://"):
            fail(f"berita tanpa URL https: {n.get('t')}")
    if len(json.dumps(d)) > 400_000:
        fail("file terlalu besar")
    print("valid")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/snapshot.json")
