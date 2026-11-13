"""Collect fresh market headlines into data/headlines.json.

Runs in GitHub Actions. Uses Google News RSS search (last 24-48 hours) for a
handful of topics that move the Prakiraan Dunia scenarios. The Claude agent
reads this file each hour, so its news panel is based on real, recent,
linkable articles instead of whatever a web search happens to surface.
"""
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "headlines.json")
UA = "Mozilla/5.0"
TOPICS = [
    ("geopolitik", "Strait of Hormuz OR Iran oil", "en"),
    ("bank-sentral", "Federal Reserve interest rate", "en"),
    ("saham-as", "Wall Street stocks S&P 500", "en"),
    ("ai-teknologi", "AI stocks Nvidia selloff OR rally", "en"),
    ("kripto", "bitcoin price", "en"),
    ("emas", "gold price", "en"),
    ("china", "China economy trade tariffs", "en"),
    ("indonesia", "IHSG", "id"),
    ("indonesia", "rupiah Bank Indonesia", "id"),
    ("indonesia", "BI-Rate OR inflasi Indonesia", "id"),
]
MAX_AGE = timedelta(hours=48)
MAX_ITEMS = 60


def rss_url(q, lang):
    if lang == "id":
        return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q + " when:2d", "hl": "id", "gl": "ID", "ceid": "ID:id"})
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q + " when:2d", "hl": "en-US", "gl": "US", "ceid": "US:en"})


def fetch(topic, q, lang):
    req = urllib.request.Request(rss_url(q, lang), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src_el = it.find("source")
        src = (src_el.text or "").strip() if src_el is not None else ""
        try:
            t = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            continue
        if src and title.endswith(" - " + src):
            title = title[: -len(" - " + src)]
        if title and link.startswith("https://"):
            out.append({"topic": topic, "lang": lang, "t": title, "src": src, "url": link,
                        "time": t.strftime("%Y-%m-%dT%H:%M:%SZ")})
    return out


def main():
    now = datetime.now(timezone.utc)
    items, errors = [], []
    for topic, q, lang in TOPICS:
        try:
            items += fetch(topic, q, lang)[:8]
        except Exception as e:  # noqa: BLE001
            errors.append(f"{q}: {e}")
        time.sleep(1)
    seen, keep = set(), []
    for it in sorted(items, key=lambda x: x["time"], reverse=True):
        key = it["t"].lower()[:70]
        if key in seen:
            continue
        if now - datetime.strptime(it["time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) > MAX_AGE:
            continue
        seen.add(key)
        keep.append(it)
    if not keep:
        print("no headlines fetched; keeping previous file", *errors, sep="\n")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "Google News RSS",
                   "items": keep[:MAX_ITEMS], "errors": errors}, f, ensure_ascii=False, indent=1)
    print(f"headlines: {len(keep[:MAX_ITEMS])}", *errors, sep="\n")


if __name__ == "__main__":
    main()
