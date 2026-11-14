"""Translate English headlines to Indonesian (Google Translate web endpoint, no key).

Used by fetch_events.py and fetch_news.py. Results are cached in
data/translations.json so each headline is translated only once. On any
failure the text is simply left untranslated.
"""
import json
import os
import re
import urllib.parse
import urllib.request

CACHE = os.path.join(os.path.dirname(__file__), "..", "data", "translations.json")
MAX_CACHE = 3000
URL = "https://translate.googleapis.com/translate_a/single?"
_cache = None


def _load():
    global _cache
    if _cache is None:
        try:
            with open(CACHE, encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception:  # noqa: BLE001
            _cache = {}
    return _cache


def save():
    c = _load()
    items = list(c.items())[-MAX_CACHE:]  # dicts keep insertion order: drop the oldest
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(dict(items), f, ensure_ascii=False, indent=0)


def _clean(s):
    return re.sub(r"\s+", " ", s.replace("\n", " ")).strip()


def _request(lines):
    q = "\n".join(lines)
    url = URL + urllib.parse.urlencode({"client": "gtx", "sl": "en", "tl": "id", "dt": "t", "q": q})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = "".join(seg[0] for seg in data[0] if seg and seg[0])
    parts = [p.strip() for p in out.split("\n")]
    if len(parts) != len(lines):
        raise ValueError("line count mismatch")
    return parts


def to_id(texts):
    """Return {english: indonesian} for the given texts (cached; best effort)."""
    c = _load()
    todo = list(dict.fromkeys(_clean(t) for t in texts if t and _clean(t) not in c))
    for i in range(0, len(todo), 15):
        chunk = todo[i:i + 15]
        try:
            res = _request(chunk)
        except Exception:  # noqa: BLE001 - fall back to one at a time
            res = []
            for t in chunk:
                try:
                    res.append(_request([t])[0])
                except Exception:  # noqa: BLE001
                    res.append(None)
        for src, dst in zip(chunk, res):
            if dst and dst.lower() != src.lower():
                c[src] = dst
    return {t: c.get(_clean(t)) for t in texts if t}
