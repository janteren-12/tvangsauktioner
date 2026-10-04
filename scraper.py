"""Henter aktuelle tvangsauktioner fra tvangsauktioner.dk og gemmer fakta i data/auctions.json.

Kørsel:
    python scraper.py              # hent alt nyt
    python scraper.py --limit 5    # test: hent kun detaljer for 5 nye auktioner
"""
import argparse
import html as htmllib
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://www.tvangsauktioner.dk"
AJAX = BASE + "/wp-admin/admin-ajax.php"
UA = "TvangsauktionerOverblik/0.1 (privat hobbyprojekt; kontakt: https://github.com/janteren-12/tvangsauktioner)"
DELAY = 2.0  # sekunder mellem kald
DATA = Path(__file__).parent / "data"
OUT = DATA / "auctions.json"

session = requests.Session()
session.headers["User-Agent"] = UA
_last = [0.0]


def polite(method, url, **kw):
    wait = DELAY - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    r = session.request(method, url, timeout=30, **kw)
    _last[0] = time.time()
    r.raise_for_status()
    return r


def num(s):
    """'1.376.000' / 'Kr. 51.230 DKK' / '55 m²' -> int (eller None)."""
    if s is None:
        return None
    m = re.search(r"\d[\d.]*", str(s))
    return int(m.group(0).replace(".", "")) if m else None


def parse_dt(s):
    """'29.10.2026, 14.00' -> '2026-10-29T14:00'"""
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})(?:,?\s*(\d{1,2})\.(\d{2}))?", s or "")
    if not m:
        return None
    d, mo, y, h, mi = m.groups()
    return f"{y}-{mo}-{d}T{int(h or 0):02d}:{mi or '00'}"


def fetch_list():
    r = polite("POST", AJAX, data={"action": "get_all_posts_ajax"})
    return r.json()["data"]["response"]


def split_address(title):
    """'Sabroesvej 17E 1 tv, 3000 Helsingør' -> (adresse, postnr, by)"""
    title = htmllib.unescape(title).strip()
    m = re.match(r"(.*?),\s*(\d{4})\s+(.+?)(?:\s+[–-]\s+.*)?$", title)
    return (m.group(1), m.group(2), m.group(3)) if m else (title, None, None)


def from_list(item):
    c = item["content"]
    auction_no = c.get("auction")
    addr, zipc, city = split_address(item["title"])
    return {
        "id": int(re.search(r"/tvangsauktion/(\d+)/", item["property_link"]).group(1)),
        "url": item["property_link"],
        "adresse": addr,
        "postnr": zipc,
        "by": city,
        "kategori": ", ".join(t["name"] for t in item["type"]),
        "status": item["status"],  # active / canceled / rescheduled
        "auktion_nr": int(auction_no) if str(auction_no).isdigit() else None,
        "auktionsdato": parse_dt(c.get("start_date")),
        "ejendomsvaerdi": num(c.get("value")),
        "areal_bolig": num(c.get("residence")),
        "areal_erhverv": num(c.get("profession")),
        "areal_grund": num(c.get("reason")),
        "lat": float(item["lat"]) if item.get("lat") else None,
        "lng": float(item["lng"]) if item.get("lng") else None,
        "billede": c.get("image"),  # kun link til originalen
    }


def parse_detail(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = {}
    for row in soup.select(".row"):
        t, v = row.select_one(".title"), row.select_one(".value")
        if t and v:
            rows.setdefault(t.get_text(" ", strip=True), v.get_text(" ", strip=True))

    def get(*keys):
        for k in keys:
            for name, val in rows.items():
                if name.lower().startswith(k.lower()):
                    return val
        return None

    out = {
        "kommune": get("Kommune"),
        "matrikel": get("Matrikelnr"),
        "grundvaerdi": num(get("Grundv")),
        "offentliggjort": parse_dt(get("Offentlig")),
        "as_nr": get("AS-nr"),
        "retskreds": get("Retskreds"),
        "sagsnr": get("Sags nr"),
        "stoerstebeloeb": num(get("Størstebel", "Stoerstebel")),
        "sikkerhedsstillelse": num(get("Sikkerhedsstillelse")),
        "vejareal": None,
        "statstidende_dato": parse_dt(get("Annonceret i statstidende")),
    }
    # vejareal: "Vej: 0 m²"
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Vej:\s*([\d.]+)\s*m", text)
    if m:
        out["vejareal"] = num(m.group(1))

    # kontaktkort: rekvirent (advokat) og fogedret
    for card in soup.select(".card-wrapper"):
        h2 = card.select_one("h2")
        h3 = card.select_one(".main-details h3")
        addr = card.select_one(".main-details .address")
        crow = {}
        for r_ in card.select(".contact-details .row"):
            tt, vv = r_.select_one(".title"), r_.select_one(".value, p:not(.title)")
            if tt and vv:
                crow[tt.get_text(strip=True)] = vv.get_text(" ", strip=True)
        if h2 and h2.get_text(strip=True) == "Fogedret":
            out["fogedret_adresse"] = addr.get_text(" ", strip=True) if addr else None
            out["fogedret_navn"] = h3.get_text(" ", strip=True) if h3 else None
        elif h2 and h2.get_text(strip=True).lower().startswith("kontakt"):
            out["rekvirent_navn"] = h3.get_text(" ", strip=True) if h3 else None
            out["rekvirent_tlf"] = crow.get("Tlf")
    return out


LANDSDELE = {299: "Hovedstaden", 74: "Midtjylland", 78: "Syddanmark", 82: "Nordjylland", 95: "Sjælland"}


def fetch_landsdele():
    """Sidens egne landsdels-filtre: 5 kald giver {auktions-id: landsdel}."""
    out = {}
    for tid, navn in LANDSDELE.items():
        r = polite("POST", AJAX, data={"action": "get_all_posts_ajax", "territory": tid})
        for it in r.json()["data"]["response"]:
            m = re.search(r"/tvangsauktion/(\d+)/", it["property_link"])
            if m:
                out[int(m.group(1))] = navn
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="max antal nye detaljesider")
    args = ap.parse_args()

    DATA.mkdir(exist_ok=True)
    old = {a["id"]: a for a in json.loads(OUT.read_text(encoding="utf-8"))} if OUT.exists() else {}
    today = date.today().isoformat()

    print("Henter listen ...")
    items = fetch_list()
    print(f"  {len(items)} auktioner på sitet, {len(old)} kendt fra før")

    current_ids = set()
    new_ids = []
    merged = dict(old)
    for it in items:
        rec = from_list(it)
        current_ids.add(rec["id"])
        if rec["id"] in old:
            merged[rec["id"]] = {**old[rec["id"]], **rec}  # opdater listefelter, behold detaljer
        else:
            rec["foerst_set"] = today
            merged[rec["id"]] = rec
            new_ids.append(rec["id"])

    # med --limit: spring de ekstra nye over (de tages med næste kørsel)
    if args.limit is not None:
        for skipped in new_ids[args.limit:]:
            merged.pop(skipped, None)
            current_ids.discard(skipped)
        new_ids = new_ids[: args.limit]

    # hent detaljesider for nye, plus gamle uden detaljer
    todo = new_ids + [i for i, a in merged.items() if i in current_ids and i not in new_ids and "fogedret_navn" not in a]
    if args.limit is not None:
        todo = todo[: args.limit]
    for n, i in enumerate(todo, 1):
        print(f"  [{n}/{len(todo)}] detaljeside {i}")
        try:
            html = polite("GET", merged[i]["url"]).text
            merged[i].update(parse_detail(html))
        except Exception as e:  # noqa: BLE001
            print(f"    fejlede: {e}", file=sys.stderr)
            continue

    # landsdel for alle (opdateres hver gang, billigt: 5 kald)
    landsdele = fetch_landsdele()
    for i, a in merged.items():
        if i in landsdele:
            a["landsdel"] = landsdele[i]

    # huller i kildens data: retskreds = fogedret; landsdel/kommune udledes fra andre auktioner
    kendt_ld, kendt_km = {}, {}
    for a in merged.values():
        if a.get("retskreds") and a.get("landsdel"):
            kendt_ld[a["retskreds"]] = a["landsdel"]
        if a.get("postnr") and a.get("kommune"):
            kendt_km[a["postnr"]] = a["kommune"]
    for a in merged.values():
        if not a.get("retskreds") and a.get("fogedret_navn"):
            a["retskreds"] = a["fogedret_navn"]
        if not a.get("landsdel") and a.get("retskreds") in kendt_ld:
            a["landsdel"] = kendt_ld[a["retskreds"]]
        if not a.get("kommune") and a.get("postnr") in kendt_km:
            a["kommune"] = kendt_km[a["postnr"]]

    # auktioner der ikke længere er på sitet: marker som væk (behold historik)
    for i, a in merged.items():
        a["paa_sitet"] = i in current_ids
        a["sidst_set"] = today if i in current_ids else a.get("sidst_set", today)

    result = sorted(merged.values(), key=lambda a: a.get("auktionsdato") or "9999")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    meta = {"opdateret": datetime.now().isoformat(timespec="minutes"), "antal": len(result)}
    (DATA / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    print(f"Færdig: {len(result)} auktioner gemt i {OUT}")


if __name__ == "__main__":
    main()
