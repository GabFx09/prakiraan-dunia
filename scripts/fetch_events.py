"""Detect big world events (riots, CEO exits, nationwide flight stops, disasters...)
from Google News RSS and write data/events.json.

Runs in GitHub Actions every ~15 minutes. For each category it searches the
last 24 hours, keeps headlines that contain strong "big event" words, and
groups headlines about the same story. A story reported by many different
outlets is treated as big; the more outlets, the higher its score. The Claude
agent reads this file to write the Indonesian explanation (snapshot `events`),
and scripts/alerts.py sends the very biggest ones to Kabar.
"""
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "events.json")
UA = "Mozilla/5.0"
MAX_AGE = timedelta(hours=36)

# (category id, label, query, lang, keyword regex that a headline must match, assets usually affected)
CATS = [
    ("kerusuhan", "Kerusuhan & protes besar", "riots OR unrest OR mass protests OR curfew OR state of emergency", "en",
     r"\briot|unrest|mass protest|protesters|curfew|state of emergency|martial law|clashes|looting", "Mata uang lokal, saham negara terkait, emas"),
    ("perang", "Perang & serangan militer", "airstrikes OR missile attack OR invasion OR military escalation OR drone attack", "en",
     r"airstrike|air strike|missile|invasion|invade|troops|drone attack|war\b|warship|bombard|shelling|ceasefire|retaliat", "Minyak, emas, dolar AS, saham pertahanan"),
    ("politik", "Guncangan politik", "coup OR resigns OR impeachment OR government collapses OR snap election OR assassination", "en",
     r"\bcoup|resign|impeach|government collapse|no-confidence|snap election|assassinat|ousted|arrested president|toppled", "Mata uang & obligasi negara terkait"),
    ("korporat", "Guncangan perusahaan besar", "CEO steps down OR CEO resigns OR CEO ousted OR files for bankruptcy OR mass layoffs OR accounting scandal", "en",
     r"\bceo\b.*(step|resign|ousted|fired|exit|depart|leav|replac)|(step|resign|ousted|fired).*\bceo\b|bankruptcy|chapter 11|layoffs|job cuts|scandal|fraud probe|delist", "Saham perusahaan & sektornya"),
    ("transportasi", "Gangguan penerbangan & transportasi", "ground stop OR flights grounded OR flight cancellations OR airport closed OR air traffic control outage OR rail strike", "en",
     r"ground stop|grounded|flight(s)? (cancel|delay)|cancell?ations|delays? (across|nationwide)|airport(s)? (closed|shut)|air traffic control|faa|port (closed|strike)|rail strike|shipping halt", "Saham maskapai & pariwisata, minyak"),
    ("bencana", "Bencana alam besar", "earthquake magnitude OR tsunami OR hurricane landfall OR typhoon OR volcano erupts OR deadly floods", "en",
     r"earthquake|quake|tsunami|hurricane|typhoon|cyclone|eruption|erupts|volcano|deadly flood|wildfire", "Saham asuransi, komoditas, mata uang negara terdampak"),
    ("siber", "Serangan siber & gangguan sistem", "cyberattack OR global outage OR ransomware attack OR systems down nationwide OR internet outage", "en",
     r"cyber ?attack|ransomware|hack(ed|ers)|outage|systems? down|went down|blackout|power cut", "Saham teknologi & perusahaan terdampak"),
    ("keuangan", "Guncangan keuangan", "bank collapse OR bank run OR debt default OR trading halted OR market crash OR emergency rate cut", "en",
     r"bank (collapse|run|failure)|default|trading halt|circuit breaker|crash|plunge|emergency (rate|meeting)|bailout|downgrade", "Saham bank, obligasi, emas, Bitcoin"),
    ("kesehatan", "Wabah & darurat kesehatan", "outbreak OR pandemic OR WHO emergency OR new virus", "en",
     r"outbreak|pandemic|epidemic|health emergency|new virus|bird flu|lockdown", "Saham farmasi, maskapai, pasar luas"),
    ("energi", "Gangguan energi & pasokan", "pipeline explosion OR refinery fire OR oil supply disruption OR OPEC emergency OR gas supply cut", "en",
     r"pipeline|refinery|oil supply|opec|gas supply|tanker|strait of hormuz|export ban|embargo|sanction", "Minyak, gas, rupiah, inflasi"),
    ("indonesia", "Peristiwa besar Indonesia", "kerusuhan OR demo besar OR gempa OR banjir OR mundur OR reshuffle OR darurat", "id",
     r"kerusuhan|ricuh|demo|unjuk rasa|gempa|tsunami|banjir|longsor|erupsi|mundur|reshuffle|darurat|ditangkap|kpk|gagal bayar|bangkrut|phk", "IHSG, rupiah, SBN"),
]

STOP = set("""a an the of to in on for and or as at by with from is are was were be been it its this that after over into amid
new says say said after more than about up down out off will would could may might has have had not no us u.s. how why what who
de di ke dan yang dari untuk dengan ini itu akan pada dalam oleh atau juga sebagai karena saat usai jadi bisa""".split())


def rss(q, lang):
    hl = {"q": q + " when:1d", "hl": "id", "gl": "ID", "ceid": "ID:id"} if lang == "id" else {"q": q + " when:1d", "hl": "en-US", "gl": "US", "ceid": "US:en"}
    req = urllib.request.Request("https://news.google.com/rss/search?" + urllib.parse.urlencode(hl), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        el = it.find("source")
        src = (el.text or "").strip() if el is not None else ""
        try:
            t = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            continue
        if src and title.endswith(" - " + src):
            title = title[: -len(" - " + src)]
        if title and link.startswith("https://"):
            out.append({"t": title, "src": src, "url": link, "time": t})
    return out


def tokens(title):
    words = re.findall(r"[a-z0-9][a-z0-9'\-]+", title.lower())
    return {w.strip("'-").removesuffix("'s") for w in words if len(w) > 2 and w not in STOP}


def cluster(items, rx):
    """Group headlines about the same story: a headline joins a group when it
    shares enough distinctive words with at least one headline already in it
    (single-link, so follow-up stories about the same event join too)."""
    groups = []
    for it in sorted(items, key=lambda x: x["time"]):
        tk = tokens(it["t"]) - GENERIC
        it["_tk"] = tk
        best, best_sim = None, 0.0
        for g in groups:
            for o in g["items"]:
                common = len(tk & o["_tk"])
                sim = common / max(1, min(len(tk), len(o["_tk"])))
                if (common >= 3 and sim >= 0.3 or common >= 2 and sim >= 0.5) and sim > best_sim:
                    best, best_sim = g, sim
        if best:
            best["items"].append(it)
        else:
            groups.append({"items": [it]})
    return groups


GENERIC = set("""news live update updates latest report reports breaking today video watch photos world global nationwide
amid after over people says report least dozens hundreds thousands killed dead deaths more first week day days hours
berita terkini hari ini terbaru warga orang polisi""".split())


def main():
    now = datetime.now(timezone.utc)
    events, errors = [], []
    for cid, label, q, lang, kw, assets in CATS:
        try:
            raw = rss(q, lang)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{cid}: {e}")
            continue
        rx = re.compile(kw, re.I)
        items = [i for i in raw if now - i["time"] <= MAX_AGE and rx.search(i["t"])]
        for g in cluster(items, re.compile(kw, re.I)):
            srcs = {i["src"] for i in g["items"] if i["src"]}
            if len(srcs) < 2:
                continue
            its = sorted(g["items"], key=lambda x: x["time"])
            recent = sum(1 for i in its if now - i["time"] <= timedelta(hours=6))
            # headline: most common phrasing is hard; take the earliest item from a well-known source if present
            lead = next((i for i in reversed(its) if i["src"] in BIG_SOURCES), its[-1])
            score = len(srcs) + 0.5 * recent
            events.append({
                "id": f"{cid}-{its[0]['time'].strftime('%Y%m%d%H%M')}-{hashlib.md5(lead['t'].encode()).hexdigest()[:4]}",
                "cat": cid, "label": label, "lang": lang, "title": lead["t"], "src": lead["src"], "url": lead["url"],
                "sources": len(srcs), "recent6h": recent, "score": round(score, 1),
                "level": "besar" if len(srcs) >= 6 else "sedang" if len(srcs) >= 3 else "kecil",
                "first": its[0]["time"].strftime("%Y-%m-%dT%H:%M:%SZ"), "last": its[-1]["time"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "assets": assets,
                "more": [{"t": i["t"], "src": i["src"], "url": i["url"]} for i in reversed(its) if i is not lead][:4],
            })
        time.sleep(1)
    events.sort(key=lambda e: (e["score"], e["last"]), reverse=True)
    # same story caught by two categories: keep the higher-scored one
    keep = []
    for e in events:
        tk = tokens(e["title"])
        if any(len(tk & tokens(k["title"])) >= 4 for k in keep):
            continue
        keep.append(e)
    if not keep and errors:
        print("no events fetched; keeping previous file", *errors, sep="\n")
        return
    prev = {}
    try:
        with open(OUT, encoding="utf-8") as f:
            prev = {e["id"]: e for e in json.load(f).get("items", [])}
    except Exception:  # noqa: BLE001
        pass
    for e in keep:  # stable ids: reuse a previous id for the same story
        tk = tokens(e["title"])
        for p in prev.values():
            if p["cat"] == e["cat"] and len(tk & tokens(p["title"])) >= 3:
                e["id"] = p["id"]
                e["first"] = min(e["first"], p.get("first", e["first"]))
                break
    keep = keep[:30]
    try:  # Indonesian translation of English headlines (best effort, cached)
        import translate  # noqa: PLC0415
        en = [e for e in keep if e["lang"] == "en"]
        tr = translate.to_id([e["title"] for e in en] + [m["t"] for e in en for m in e["more"]])
        for e in en:
            if tr.get(e["title"]):
                e["title_id"] = tr[e["title"]]
            for m in e["more"]:
                if tr.get(m["t"]):
                    m["t_id"] = tr[m["t"]]
        translate.save()
    except Exception as ex:  # noqa: BLE001
        errors.append(f"translate: {ex}")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "Google News RSS (deteksi otomatis)",
                   "items": keep, "errors": errors}, f, ensure_ascii=False, indent=1)
    print(f"events: {len(keep)} ({sum(e['level'] == 'besar' for e in keep)} besar)", *errors, sep="\n")


BIG_SOURCES = {"Reuters", "Associated Press", "AP News", "BBC", "BBC News", "CNN", "Bloomberg", "Bloomberg.com", "The New York Times",
               "The Wall Street Journal", "Financial Times", "CNBC", "Al Jazeera", "The Guardian", "NBC News", "ABC News", "CBS News",
               "Kompas.com", "CNN Indonesia", "detikNews", "Tempo.co", "ANTARA News", "CNBC Indonesia"}

if __name__ == "__main__":
    main()
