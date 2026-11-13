"""Add the Antam retail gold price (1 gram) to data/market.json under `local.antam`.

The official logammulia.com blocks automated requests, so this reads the
public daily table on emasantam.id (unofficial). If parsing fails, the previous
value is kept and marked ok=false, so the site never shows a broken number.
"""
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from html import unescape

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "market.json")
URL = "https://emasantam.id/harga-emas-antam-harian/"
PAT = re.compile(r"Harga Emas 1 gram\|\s*([^|]+?)\s*\|\s*Rp\.?\s*([\d.]+)\s*\|Harga Sebelumnya\|\s*([^|]+?)\s*\|\s*Rp\.?\s*([\d.]+)", re.I)


def parse(html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    txt = unescape(re.sub(r"<[^>]+>", "|", t))
    txt = re.sub(r"\s+", " ", re.sub(r"\|[\s|]*\|", "|", txt))
    m = PAT.search(txt)
    if not m:
        raise ValueError("pola harga tidak ditemukan")
    price, prev = int(m.group(2).replace(".", "")), int(m.group(4).replace(".", ""))
    if not (500_000 < price < 20_000_000 and 500_000 < prev < 20_000_000):
        raise ValueError(f"harga tidak masuk akal: {price}")
    return {"price": price, "prev": prev, "chg": round((price / prev - 1) * 100, 2), "date": m.group(1), "prevDate": m.group(3)}


def main():
    with open(OUT, encoding="utf-8") as f:
        market = json.load(f)
    old = (market.get("local") or {}).get("antam")
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = parse(r.read().decode("utf-8", "ignore"))
        data.update({"ok": True, "name": "Emas Antam 1 gram (harga beli)", "src": "emasantam.id", "url": URL,
                     "fetchedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    except Exception as e:  # noqa: BLE001
        print("antam: gagal,", e)
        if not old:
            return
        data = {**old, "ok": False}
    market.setdefault("local", {})["antam"] = data
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(market, f, ensure_ascii=False, indent=1)
    print(f"antam: Rp {data['price']:,} ({data['chg']:+}%)".replace(",", "."))


if __name__ == "__main__":
    main()
