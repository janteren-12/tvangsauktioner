"""Henter kommunale ejendomme og grunde til salg fra kommunernes egne hjemmesider (Sjælland).

Hver kommune har en eller flere "salgs-hubs" (sider der lister salg). Scraperen følger
kun links der ligger UNDER hubbens adresse; en underside uden egne undersider er ét salg.
Hubs tjekkes hver gang; salgssider hentes kun første gang vi ser dem.

Kørsel:
    python kommuner.py               # alle kommuner
    python kommuner.py --only Køge   # kun én kommune (test)
"""
import argparse
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

UA = "TvangsauktionerOverblik/0.1 (privat hobbyprojekt; kontakt: https://github.com/janteren-12/tvangsauktioner)"
DELAY = 2.0  # sekunder mellem kald til samme kommune
DATA = Path(__file__).parent / "data"
OUT = DATA / "kommunale.json"

H, S = "Hovedstaden", "Sjælland"
KOMMUNER = {
    "Glostrup": (H, ["https://www.glostrup.dk/borger/bolig-og-byggeri/find-bolig-og-ejendomssalg/ejendomme-og-grunde-til-salg"]),
    "Hvidovre": (H, ["https://www.hvidovre.dk/om-kommunen/ejendomme-til-salg-og-forpagtninger-i-udbud",
                     "https://www.hvidovre.dk/erhverv/byggeri-og-erhvervsomraader/ledige-erhvervsgrunde-bygninger-og-lokaler"]),
    "Høje-Taastrup": (H, ["https://www.htk.dk/erhvervsliv/vaekst-og-erhverv/grunde-og-ejendomme-til-salg"]),
    "Lyngby-Taarbæk": (H, ["https://www.ltk.dk/erhverv/byggeri-og-ejendomme/ejendomme-til-salg"]),
    "Fredensborg": (H, ["https://fredensborg.dk/kommunen/kommunen-i-udvikling/byggegrunde"]),
    "Gribskov": (H, ["https://gribskov.dk/erhverv/salg-af-grunde-og-ejendomme"]),
    "Halsnæs": (H, ["https://halsnaes.dk/erhverv/grunde-og-erhvervslokaler/salg-af-grunde-og-bygninger"]),
    "Helsingør": (H, ["https://www.helsingor.dk/virksomhed/salg-af-grunde-og-ejendomme"]),
    "Faxe": (S, ["https://www.faxekommune.dk/da/erhverv/grunde-til-salg"]),
    "Greve": (S, ["https://greve.dk/erhverv/grunde-og-bygninger"]),
    "Guldborgsund": (S, ["https://www.guldborgsund.dk/borger/flytte-bo-og-bygge/byggegrunde-og-andre-grunde"]),
    "Holbæk": (S, ["https://holbaek.dk/service-og-selvbetjening/bolig-og-byggeri/ejendomme-til-salg"]),
    "Kalundborg": (S, ["https://www.kalundborg.dk/erhverv/salg-af-kommunale-ejendomme-og-arealer"]),
    "Køge": (S, ["https://www.koege.dk/borger/bolig-og-byggeri/byggegrunde-og-ejendomme-til-salg"]),
    "Lejre": (S, ["https://lejre.dk/borger/bolig-byggeri-og-affald/ejendomme-til-salg"]),
    "Lolland": (S, ["https://www.lolland.dk/erhverv/byggegrunde"]),
    "Næstved": (S, ["https://www.naestved.dk/bolig-og-miljoe/byggegrunde-og-ejendomme-til-salg/byggegrunde-og-ejendomme-til-salg",
                    "https://www.naestved.dk/erhverv/erhvervsgrunde"]),
    "Odsherred": (S, ["https://www.odsherred.dk/da/starte-og-drive-virksomhed/teknik-og-miljoe-for-virksomheder/erhvervsbyggeri-og-erhvervsgrunde/erhvervsjord-grunde-og-ejendomme/salg-af-kommunale-ejendomme-og-arealer/"]),
    "Ringsted": (S, ["https://ringsted.dk/da/grunde-til-salg", "https://ringsted.dk/da/erhvervsgrunde-i-ringsted"]),
    "Roskilde": (S, ["https://www.roskilde.dk/da-dk/service-og-selvbetjening/borger/bolig-og-byggeri/grunde-til-salg-1/",
                     "https://www.roskilde.dk/da-dk/service-og-selvbetjening/borger/bolig-og-byggeri/grunde-til-salg/",
                     "https://www.roskilde.dk/da-dk/service-og-selvbetjening/erhverv/byggeri-grunde-planer-og-horinger/erhvervsgrunde-til-salg/"]),
    "Solrød": (S, ["https://solrod.dk/service-og-selvbetjening/bolig-og-byggeri/bolig/byggegrunde-og-ejendomme-til-salg"]),
    "Sorø": (S, ["https://soroe.dk/service-og-selvbetjening/erhverv-og-virksomheder/erhvervsgrunde-til-salg"]),
    "Stevns": (S, ["https://www.stevns.dk/service-and-selvbetjening/erhverv/salg-af-ejendomme-og-erhvervsgrunde"]),
    "Slagelse": (S, ["https://www.slagelse.dk/da/service-og-selvbetjening/bolig-og-byggeri/byggeri-bbr-lokalplaner-og-kommuneplan/byggegrunde-til-salg/",
                     "https://www.slagelse.dk/da/service-og-selvbetjening/erhverv/erhvervsarealer-boligarealer-og-byggeri/boligarealer-til-salg/",
                     "https://www.slagelse.dk/da/service-og-selvbetjening/erhverv/erhvervsarealer-boligarealer-og-byggeri/ejendomme-til-salg/",
                     "https://www.slagelse.dk/da/service-og-selvbetjening/erhverv/erhvervsarealer-boligarealer-og-byggeri/erhvervsgrunde-til-salg/"]),
    "Vordingborg": (S, ["https://www.vordingborg.dk/borger/bolig-og-byggeri/boligejendomme-og-byggegrunde-til-salg",
                        "https://www.vordingborg.dk/erhverv/erhvervsejendomme-og-erhvervsgrunde-til-salg"]),
}

# undersider der er vejledning, ikke salg
SKIP = re.compile(r"(gode-raad|vejledning|betingelser|koebsvilkaar|kontakt|faq|paa-kortet|salgsdokumenter|"
                  r"grundejerforening|solgt-for-nyligt|solgte|kommende|nyhedsbrev|spoergsmaal)", re.I)

session = requests.Session()
session.headers["User-Agent"] = UA
_last = {}
_robots = {}


def allowed(url):
    host = urlparse(url).netloc
    if host not in _robots:
        rp = robotparser.RobotFileParser()
        try:
            r = session.get(f"https://{host}/robots.txt", timeout=20)
            rp.parse(r.text.splitlines() if r.status_code == 200 and "<html" not in r.text[:300].lower() else [])
        except requests.RequestException:
            rp.parse([])
        _robots[host] = rp
        _last[host] = time.time()
    return _robots[host].can_fetch(UA, url)


def fetch(url):
    host = urlparse(url).netloc
    wait = DELAY - (time.time() - _last.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    r = session.get(url, timeout=30)
    _last[host] = time.time()
    r.raise_for_status()
    return r.text


def norm(url):
    u = urlparse(url)
    return f"https://{u.netloc.lower()}{u.path.rstrip('/')}"


def children(html, base):
    """Links på siden der ligger under base-adressen (dvs. undersider)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("header, footer, nav"):
        tag.decompose()
    base_n = norm(base)
    out = []
    for a in soup.select("a[href]"):
        u = norm(urljoin(base, a["href"]))
        if u.startswith(base_n + "/") and u != base_n and not re.search(r"\.(pdf|docx?|xlsx?|jpe?g|png)$", u, re.I) \
                and not SKIP.search(u.rsplit("/", 1)[-1]) and u not in out:
            out.append(u)
    return out


MONTHS = {m: i for i, m in enumerate(["januar", "februar", "marts", "april", "maj", "juni", "juli", "august",
                                       "september", "oktober", "november", "december"], 1)}


def num(s):
    return int(s.replace(".", "").replace(" ", "")) if s else None


def facts(html, url):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, header, footer, nav"):
        tag.decompose()
    h1 = soup.find("h1")
    og = soup.find("meta", property="og:title")
    title = (h1.get_text(" ", strip=True) if h1 else None) or (og["content"] if og else url.rsplit("/", 1)[-1])
    desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    desc = (desc.get("content") or "").strip()[:220] if desc else ""
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    pris = None
    m = re.search(r"(mindstepris|udbudspris|kontantpris|salgspris|minimumspris|fast pris|pris)\D{0,40}?(\d{1,3}(?:\.\d{3})+)\s*(kr|,-)", text, re.I)
    pris_m2 = None
    if m:
        pris = num(m.group(2))
        if pris < 50000:  # fx "pris 1.200 kr. pr. m²"
            pris, pris_m2 = None, pris
    areal = None
    m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d{2,6})\s*m(²|2)\b", text)
    if m:
        areal = num(m.group(1))
    frist = None
    m = re.search(r"(budfrist|tilbudsfrist|frist for (?:afgivelse af |aflevering af )?(?:bud|tilbud)|senest)\D{0,60}?"
                  r"(\d{1,2})\.\s*(januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december|\d{1,2}\.?)\s*(20\d\d)",
                  text, re.I)
    if m:
        mo = m.group(3).lower().rstrip(".")
        mo = MONTHS.get(mo) or (int(mo) if mo.isdigit() else None)
        if mo:
            frist = f"{m.group(4)}-{mo:02d}-{int(m.group(2)):02d}"

    low = (title + " " + url).lower()
    status = "solgt" if re.search(r"\bsolgt\b", low) else "reserveret" if "reserveret" in low else "til salg"
    if re.search(r"erhverv|industri|business|kontor", low):
        kategori = "Erhverv"
    elif re.search(r"parcelhus|byggegrund|grund|parcel|areal|udstykning", low):
        kategori = "Grund"
    else:
        kategori = "Ejendom"
    return {"titel": title, "beskrivelse": desc, "pris": pris, "pris_m2": pris_m2, "areal": areal, "frist": frist,
            "status": status, "kategori": kategori}


_sitemaps = {}


def sitemap_urls(host):
    """Alle side-adresser i kommunens sitemap (hentes én gang pr. kørsel)."""
    if host in _sitemaps:
        return _sitemaps[host]
    urls, queue, n = set(), [], 0
    try:
        r = session.get(f"https://{host}/robots.txt", timeout=20)
        queue = re.findall(r"(?im)^sitemap:\s*(\S+)", r.text) if r.status_code == 200 else []
    except requests.RequestException:
        pass
    queue = queue or [f"https://{host}/sitemap.xml"]
    while queue and n < 15:
        u = queue.pop(0)
        n += 1
        try:
            t = fetch(u)
        except requests.RequestException:
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", t)
        if "<sitemapindex" in t:
            queue += locs
        else:
            urls.update(norm(x) for x in locs)
    _sitemaps[host] = urls
    return urls


RECHECK_DAYS = 7


def crawl(kommune, landsdel, hubs, known, cache, today):
    """Returnerer {url: post} for alle aktuelle salg i kommunen.

    Kandidater = sider under hubbens adresse, fundet i sitemap og som links på hubben.
    En kandidat der linker til 2+ andre kandidater er en oversigt; ellers et salg.
    Kendte salg hentes kun igen hver RECHECK_DAYS. dag (for at opdage 'solgt').
    """
    cands = set()
    hub_html = {}
    for hub in hubs:
        if not allowed(hub):
            print(f"    robots.txt forbyder {hub}", file=sys.stderr)
            continue
        hub_n = norm(hub)
        try:
            hub_html[hub] = fetch(hub)
            cands |= set(children(hub_html[hub], hub))
        except requests.RequestException as e:
            print(f"    fejl {hub}: {e}", file=sys.stderr)
        cands |= {u for u in sitemap_urls(urlparse(hub).netloc)
                  if u.startswith(hub_n + "/") and not SKIP.search(u.rsplit("/", 1)[-1])
                  and not re.search(r"\.(pdf|docx?)$", u, re.I)}
    found = {}
    for n in sorted(cands):
        if cache.get(n) == "oversigt" or not allowed(n):
            continue
        rec = known.get(n)
        if rec and (date.fromisoformat(today) - date.fromisoformat(rec.get("tjekket", rec["foerst_set"]))).days < RECHECK_DAYS:
            found[n] = rec
            continue
        try:
            html = fetch(n)
        except requests.RequestException as e:
            print(f"    fejl {n}: {e}", file=sys.stderr)
            if rec:
                found[n] = rec
            continue
        links = set(children(html, "https://" + urlparse(n).netloc + "/")) & cands
        if len(links - {n}) >= 2:
            cache[n] = "oversigt"
            continue
        cache[n] = "salg"
        rec = dict(rec or {})
        rec.update(facts(html, n))
        rec.update({"id": n, "url": n, "kommune": kommune, "landsdel": landsdel, "tjekket": today})
        rec.setdefault("foerst_set", today)
        found[n] = rec
    # hubs hvor salgene står direkte på siden (ingen undersider): vis hubben som én samlet side
    for hub, html in hub_html.items():
        hub_n = norm(hub)
        if any(u.startswith(hub_n + "/") for u in found):
            continue
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.select("script, style, header, footer, nav, form"):
            tag.decompose()
        main_ = soup.find("main") or soup
        h = hashlib.sha1(re.sub(r"\s+", " ", main_.get_text(" ", strip=True)).encode()).hexdigest()
        rec = dict(known.get(hub_n) or {})
        if rec.get("hash") and rec["hash"] != h:
            rec["aendret"] = today
        rec.update(facts(html, hub))
        rec.update({"id": hub_n, "url": hub_n, "kommune": kommune, "landsdel": landsdel, "tjekket": today,
                    "hash": h, "samlet_side": True, "kategori": "Samlet oversigt",
                    "pris": None, "pris_m2": None, "areal": None, "frist": None})
        rec.setdefault("foerst_set", today)
        found[hub_n] = rec
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="kun denne kommune")
    args = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    old = {a["id"]: a for a in json.loads(OUT.read_text(encoding="utf-8"))} if OUT.exists() else {}
    today = date.today().isoformat()
    merged = dict(old)
    cache_f = DATA / "kommunale_cache.json"
    cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}
    current = set()
    for kommune, (landsdel, hubs) in KOMMUNER.items():
        if args.only and kommune != args.only:
            continue
        print(f"{kommune} ...")
        known = {k: v for k, v in old.items() if v.get("kommune") == kommune}
        found = crawl(kommune, landsdel, hubs, known, cache, today)
        print(f"  {len(found)} salg")
        merged.update(found)
        current |= set(found)
    ran = {args.only} if args.only else set(KOMMUNER)
    for k, a in merged.items():
        if a["kommune"] in ran:
            a["paa_sitet"] = k in current
            if k in current:
                a["sidst_set"] = today
    cache_f.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    result = sorted(merged.values(), key=lambda a: (a["kommune"], a["titel"]))
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "kommunale_meta.json").write_text(json.dumps(
        {"opdateret": datetime.now().isoformat(timespec="minutes"), "antal": sum(a.get("paa_sitet", False) for a in result),
         "kommuner": sorted(KOMMUNER)}, ensure_ascii=False), encoding="utf-8")
    print(f"Færdig: {sum(a.get('paa_sitet', False) for a in result)} aktuelle salg gemt i {OUT}")


if __name__ == "__main__":
    main()
