#!/usr/bin/env python3
"""collect.py — build one master list of internships from many sources.

Two kinds of source feed the list.

  1. Job boards. Each board is a small function below that returns listings in
     the common shape (see `listing`).
  2. Company career sites. Every link a board points at reveals which careers
     platform that company uses, so the company is remembered in
     data/companies.json and its own feed is read on every run (see ats.py).
     That finds postings before a board picks them up.

The collector then merges duplicates, tags each listing (degree level, co-op,
field, region), tracks what it has seen before, and writes

    docs/data.json         every active listing, with every field
    docs/list.json         the same listings with only what the web page shows
    docs/checked.json      when the sources were last checked (written every run,
                           while the files above change only when a listing does)
    docs/listings.csv      the same, flat, for a spreadsheet
    data/seen.json         id -> date first seen (the state between runs)
    data/companies.json    the career sites to check
    out/new_<date>.md      what is new since the last run (one file per day)

USAGE

    python3 collect.py                 # everything
    python3 collect.py --no-careers    # boards only, a few seconds
    python3 collect.py --only simplify,openquant
    python3 collect.py --list          # show the board sources and stop

A source that fails is reported and skipped. It never stops the run, and its
listings from earlier runs are not marked as gone.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import socket
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Dict, List, Optional

import ats
import manual
import match
import semantic

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DOCS = os.path.join(HERE, "docs")
OUT = os.path.join(HERE, "out")
RAW = "https://raw.githubusercontent.com"
UA = "internship-finder/1.0 (personal job search; python-urllib)"
TODAY = dt.date.today()


# ── fetching ────────────────────────────────────────────────────────────────
# IPv6 connections hang on some machines until they time out, and urllib tries
# IPv6 first. Asking for IPv4 addresses only avoids a minute-long stall per file.
_getaddrinfo = socket.getaddrinfo


def _ipv4_only(host, port, family=0, *args, **kwargs):
    return _getaddrinfo(host, port, socket.AF_INET, *args, **kwargs)


socket.getaddrinfo = _ipv4_only


def fetch(url: str, timeout: int = 60, json_body: Optional[dict] = None) -> bytes:
    headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    data = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body).encode()
    req = urllib.request.Request(url, headers=headers, data=data)
    # A site that says "too many requests" is asked again after a pause.
    for pause in (3, 8, None):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or pause is None:
                raise
            time.sleep(pause)


def fetch_text(url: str) -> str:
    return fetch(url).decode("utf-8-sig", errors="replace")


# ── the common shape ────────────────────────────────────────────────────────
def listing(source: str, company: str, title: str, url: str, *,
            location: str = "", posted: Optional[str] = None,
            degrees: Optional[List[str]] = None, category: str = "",
            sponsorship: str = "", pay: str = "", note: str = "") -> dict:
    return {
        "source": source,
        "company": clean(company),
        "title": clean(title),
        "url": (url or "").strip(),
        "location": clean(location),
        "posted": posted,                 # ISO date, or None when the board gives none
        "degrees": degrees or [],
        "category": clean(category),
        "sponsorship": clean(sponsorship),
        "pay": clean(pay),
        "note": clean(note),
    }


_TAG = re.compile(r"<[^>]+>")
_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿️‍]")


def clean(text) -> str:
    text = _TAG.sub("", str(text or ""))
    text = _EMOJI.sub("", text)
    return re.sub(r"\s+", " ", text.replace("**", "")).strip(" |")


def iso_from_epoch(v) -> Optional[str]:
    try:
        return dt.datetime.fromtimestamp(int(v), dt.timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def iso_from_age(text: str) -> Optional[str]:
    """'0d' / '3d' / '2w' / '1mo' -> a date, counted back from today."""
    m = re.fullmatch(r"\s*(\d+)\s*(d|w|mo)\s*", (text or "").lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    days = n * {"d": 1, "w": 7, "mo": 30}[unit]
    return (TODAY - dt.timedelta(days=days)).isoformat()


# ── sources ─────────────────────────────────────────────────────────────────
def _simplify_format(url: str, name: str) -> List[dict]:
    out = []
    for x in json.loads(fetch_text(url)):
        if not x.get("active") or x.get("is_visible") is False:
            continue
        out.append(listing(
            name, x.get("company_name"), x.get("title"), x.get("url"),
            location="; ".join(x.get("locations") or []),
            posted=iso_from_epoch(x.get("date_posted")),
            degrees=x.get("degrees") or [],
            category=x.get("category") or "",
            sponsorship=x.get("sponsorship") or "",
            note=x.get("season") or ""))
    return out


def src_simplify() -> List[dict]:
    return _simplify_format(
        f"{RAW}/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json",
        "simplify")


def src_vansh() -> List[dict]:
    return _simplify_format(
        f"{RAW}/vanshb03/Summer2027-Internships/dev/.github/scripts/listings.json",
        "vanshb03")


def src_trakker() -> List[dict]:
    out = []
    for x in json.loads(fetch_text(f"{RAW}/TrakkerHQ/quant-jobs/main/data/jobs.json")):
        if (x.get("skill_level") or "").lower() != "intern":
            continue
        out.append(listing(
            "trakker", x.get("company_display"), x.get("title"), x.get("url"),
            location=x.get("location") or "",
            posted=(x.get("date_discovered") or x.get("updated_at") or "")[:10] or None,
            category="Quant"))
    return out


def src_tanh() -> List[dict]:
    text = fetch_text(f"{RAW}/TanhJK728/2027-AI-ML-Internships/main/data/internships.csv")
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        if (r.get("Status") or "").strip().lower() not in ("open", ""):
            continue
        deg = [d.strip() for d in re.split(r"[/,]", r.get("Degree") or "") if d.strip()]
        out.append(listing(
            "tanhjk728", r.get("Company"), r.get("Role"), r.get("Link"),
            location=r.get("Location") or r.get("Country") or "",
            degrees=deg, category=r.get("Track") or "",
            note=("deadline " + r["Deadline"]) if r.get("Deadline") else ""))
    return out


_NU_ROLES = {"QT": "Quantitative Trader", "QR": "Quantitative Researcher",
             "QD": "Quantitative Developer", "SWE": "Software Engineer",
             "HW": "Hardware Engineer"}


def src_northwestern() -> List[dict]:
    import yaml
    blob = fetch("https://codeload.github.com/northwesternfintech/"
                 "2027QuantInternships/tar.gz/refs/heads/main")
    out = []
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for m in tar.getmembers():
            if "/data/" not in m.name or not m.name.endswith((".yaml", ".yml")):
                continue
            doc = yaml.safe_load(tar.extractfile(m).read()) or {}
            for role in doc.get("roles") or []:
                rt = str(role.get("role_type") or "").strip()
                base = _NU_ROLES.get(rt, rt or "Intern")
                for link in role.get("links") or []:
                    if not link.get("url"):
                        continue
                    label = str(link.get("label") or "").strip()
                    title = f"{base} Intern" + (f" ({label})" if label else "")
                    out.append(listing(
                        "northwestern", doc.get("name"), title, link["url"],
                        location=str(doc.get("locations") or ""),
                        category="Quant", note=str(doc.get("notes") or "")))
    return out


def src_phd_board() -> List[dict]:
    text = fetch_text("https://dion-jy.github.io/phd-intern-board/data.js")
    start = text.index("window.JOBS_DATA=") + len("window.JOBS_DATA=")
    doc, _ = json.JSONDecoder().raw_decode(text[start:])
    out = []
    for x in doc.get("jobs") or []:
        out.append(listing(
            "phd-board", x.get("company"), x.get("title"), x.get("url"),
            location=x.get("location") or "",
            posted=(x.get("posted_at") or "")[:10] or None,
            degrees=["PhD"] if x.get("phd") else [],
            category=x.get("department") or "",
            note=f"confidence {x.get('confidence')}" if x.get("confidence") else ""))
    return out


_MD_LINK = re.compile(r"\]\((https?://[^)\s]+)\)")
_HREF = re.compile(r'href="(https?://[^"]+)"')


def _table_rows(text: str):
    """Markdown table rows as lists of raw cells, skipping headers and rules."""
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or set(cells[0]) <= set("-: "):
            continue
        if cells[0].lower() in ("company", "**company**"):
            continue
        yield cells


def src_zapply() -> List[dict]:
    text = fetch_text(f"{RAW}/zapplyjobs/awesome-ml-internships-2027/main/README.md")
    out, section = [], ""
    for line in text.splitlines():
        m = re.search(r"<summary><h3>(.*?)</h3></summary>", line)
        if m:
            section = clean(m.group(1))
            continue
        if not line.startswith("|"):
            continue
        for cells in _table_rows(line):
            if len(cells) < 6:
                continue
            link = _MD_LINK.search(cells[5])
            if not link:
                continue
            out.append(listing(
                "zapply", cells[0], cells[1], link.group(1),
                location=cells[2], posted=iso_from_age(cells[3]),
                sponsorship=cells[4], category=section))
    return out


def src_speedyapply() -> List[dict]:
    text = fetch_text(f"{RAW}/speedyapply/2027-AI-College-Jobs/main/README.md")
    out, section = [], ""
    for line in text.splitlines():
        if line.startswith("#"):
            section = clean(line.lstrip("# "))
            continue
        if not line.startswith("|"):
            continue
        for cells in _table_rows(line):
            # company | position | location | (salary) | posting | age
            links = [_HREF.search(c) for c in cells]
            apply = next((m.group(1) for c, m in zip(cells, links)
                          if m and "alt=\"Apply\"" in c), None)
            if not apply:
                continue
            pay = cells[3] if len(cells) >= 6 else ""
            out.append(listing(
                "speedyapply", cells[0], cells[1], apply,
                location=cells[2], posted=iso_from_age(cells[-1]),
                pay=pay, category=section))
    return out


def src_openquant(max_pages: int = 20, page_size: int = 25) -> List[dict]:
    """OpenQuant has no data file. This is the same request its own page makes
    to load results, one page at a time, with a pause between pages."""
    out, seen = [], set()
    for page in range(1, max_pages + 1):
        rows = json.loads(fetch(
            "https://server.openquant.co/api/job/posts",
            json_body={"page": page, "pageSize": page_size, "positionType": "",
                       "companyType": "", "keywords": "", "level": "Internship",
                       "country": "", "location": ""}))
        if isinstance(rows, dict):
            rows = next((v for v in rows.values() if isinstance(v, list)), [])
        fresh = [r for r in rows if r.get("ID") not in seen]
        for r in fresh:
            seen.add(r.get("ID"))
            out.append(listing(
                "openquant", r.get("CompanyName"), r.get("Position"),
                r.get("ApplicationUrl"), location=r.get("Location") or "",
                posted=r.get("PostedDate") or None,
                category=r.get("PositionType") or "Quant",
                note=("skills " + r["Skills"]) if r.get("Skills") else ""))
        if len(rows) < page_size or not fresh:
            break
        time.sleep(1.0)          # be polite; this is a live site, not a file
    return out


SOURCES: Dict[str, Callable[[], List[dict]]] = {
    "simplify": src_simplify,
    "vanshb03": src_vansh,
    "trakker": src_trakker,
    "tanhjk728": src_tanh,
    "northwestern": src_northwestern,
    "phd-board": src_phd_board,
    "zapply": src_zapply,
    "speedyapply": src_speedyapply,
    "openquant": src_openquant,
}


# ── merging ─────────────────────────────────────────────────────────────────
_TRACKING = re.compile(r"^(utm_|gh_src|src$|source$|ref$|s$|lever-source|microsite$)", re.I)


def canonical_url(url: str) -> str:
    """Same posting, same string: drop tracking parameters and trailing noise."""
    try:
        p = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
             if not _TRACKING.match(k)]
    path = re.sub(r"/(apply|application)/?$", "", p.path).rstrip("/")
    host = p.netloc.lower().removeprefix("www.")
    return urllib.parse.urlunsplit(("https", host, path,
                                    urllib.parse.urlencode(sorted(query)), ""))


_CO_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|group|"
                        r"holdings|technologies|technology|labs?|lp)\b\.?")


def norm_company(name: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    s = _CO_SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_title(title: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (title or "").lower())
    return re.sub(r"\s+", " ", s).strip()


_PHD = re.compile(r"\b(ph\.?\s?d|doctoral|doctorate)\b", re.I)


def merge(rows: List[dict]) -> List[dict]:
    """One record per posting. Two rows are the same posting when their cleaned
    URLs match, or when they come from DIFFERENT boards and company and title
    match after normalizing.

    The name match is deliberately not applied within one board. A company that
    lists "Software Engineer Intern" 36 times on the same board has 36 separate
    postings, and folding them together would hide a new one behind an old one.
    """
    by_url: Dict[str, dict] = {}
    by_name: Dict[tuple, List[dict]] = {}
    merged: List[dict] = []
    for r in rows:
        if not r["url"] or not r["title"] or not r["company"]:
            continue
        cu = canonical_url(r["url"])
        nk = (norm_company(r["company"]), norm_title(r["title"]))
        rec = by_url.get(cu) or next(
            (c for c in by_name.get(nk, []) if r["source"] not in c["sources"]), None)
        if rec is None:
            rec = {"id": hashlib.sha1(cu.encode()).hexdigest()[:12],
                   "company": r["company"], "title": r["title"],
                   "url": r["url"], "urls": [], "locations": [],
                   "posted": None, "degrees": [], "categories": [],
                   "sponsorship": "", "pay": "", "notes": [], "sources": [],
                   "ats": []}
            merged.append(rec)
        by_url.setdefault(cu, rec)
        if rec not in by_name.setdefault(nk, []):
            by_name[nk].append(rec)
        if r["url"] not in rec["urls"]:
            rec["urls"].append(r["url"])
        for loc in filter(None, (x.strip() for x in r["location"].split(";"))):
            if loc not in rec["locations"]:
                rec["locations"].append(loc)
        if r["posted"] and (rec["posted"] is None or r["posted"] < rec["posted"]):
            rec["posted"] = r["posted"]          # earliest sighting wins
        for d in r["degrees"]:
            if d not in rec["degrees"]:
                rec["degrees"].append(d)
        if r["category"] and r["category"] not in rec["categories"]:
            rec["categories"].append(r["category"])
        rec["sponsorship"] = rec["sponsorship"] or r["sponsorship"]
        rec["pay"] = rec["pay"] or r["pay"]
        if r["note"] and r["note"] not in rec["notes"]:
            rec["notes"].append(r["note"])
        if r["source"] not in rec["sources"]:
            rec["sources"].append(r["source"])
        if r.get("ats") and r["ats"] not in rec["ats"]:
            rec["ats"].append(r["ats"])
    for rec in merged:
        # Prefer a direct employer link over an aggregator redirect.
        direct = [u for u in rec["urls"] if "zapply.jobs" not in u and "simplify.jobs" not in u]
        rec["url"] = (direct or rec["urls"])[0]
        tag(rec)
    return merged


# ── tagging ─────────────────────────────────────────────────────────────────
# Tags describe the posting. They are not a ranking and carry no preference.
_MS = re.compile(r"\b(master'?s?|m\.?s\.?c?|mba|graduate student|grad(uate)? intern)\b", re.I)
_COOP = re.compile(r"\bco-?ops?\b", re.I)
_TRACKS = [
    ("Robotics", re.compile(
        r"robot|manipulat|embodied|humanoid|autonom|self.driving|perception|"
        r"\bslam\b|motion planning|controls?\b|mechatronic|drone|\buav\b|"
        r"\bgnc\b|locomotion", re.I)),
    ("AI/ML", re.compile(
        r"machine learning|deep learning|\bml\b|\bai\b|a\.i\.|artificial intelligence|"
        r"\bllm|\bnlp\b|natural language|computer vision|reinforcement|generative|"
        r"foundation model|neural|applied scien", re.I)),
    ("Research", re.compile(
        r"research (scientist|intern|engineer|resident|fellow)|student researcher|"
        r"\bresearch\b.*\bintern|phd resident|scientist", re.I)),
    ("Quant", re.compile(
        r"quant|trading|\btrader\b|\bstrat(s|egist)?\b|market making|"
        r"portfolio|derivatives|fixed income|\balpha\b", re.I)),
    ("Software", re.compile(
        r"software|\bswe\b|\bsde\b|developer|back.?end|front.?end|full.?stack|"
        r"infrastructure|platform|devops|\bsre\b|systems? engineer|compiler|"
        r"distributed|cloud|mobile|\bios\b|android|web", re.I)),
    ("Data", re.compile(
        r"data scien|data engineer|data analy|analytics|business intelligence|"
        r"statistic|\bbi\b", re.I)),
    ("Hardware", re.compile(
        r"hardware|fpga|asic|\brtl\b|embedded|firmware|electrical|circuit|"
        r"semiconductor|silicon|\bvlsi\b|photonic|\brf\b|mechanical", re.I)),
]
_CATEGORY_TRACK = {"ai/ml/data": "AI/ML", "data science, ai & machine learning": "AI/ML",
                   "software": "Software", "software engineering": "Software",
                   "hardware": "Hardware", "hardware engineering": "Hardware",
                   "quant": "Quant"}
_US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN "
                 "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA "
                 "WA WV WI WY DC".split())
_US_NAMES = re.compile(
    r"united states|\busa?\b|u\.s\.|alabama|alaska|arizona|arkansas|california|"
    r"colorado|connecticut|delaware|florida|georgia|hawaii|idaho|illinois|indiana|"
    r"iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|michigan|"
    r"minnesota|mississippi|missouri|montana|nebraska|nevada|new hampshire|"
    r"new jersey|new mexico|new york|north carolina|north dakota|ohio|oklahoma|"
    r"oregon|pennsylvania|rhode island|south carolina|south dakota|tennessee|"
    r"texas|utah|vermont|virginia|washington|west virginia|wisconsin|wyoming|"
    r"bay area|san francisco|seattle|boston|chicago|nyc|silicon valley", re.I)
_STATE_CODE = re.compile(r"\b([A-Z]{2})\b")


def region_of(locations: List[str]) -> List[str]:
    """Which of US / International / Remote a posting covers. May be several.
    An empty list means the posting gave no usable location."""
    out = []
    for loc in locations:
        if re.search(r"remote", loc, re.I) and "Remote" not in out:
            out.append("Remote")
        us = bool(_US_NAMES.search(loc)) or any(
            c in _US_STATES for c in _STATE_CODE.findall(loc))
        plain = re.sub(r"remote|hybrid|multiple|locations?|\d+|[^a-z]", "", loc.lower())
        if us:
            if "US" not in out:
                out.append("US")
        elif plain and "International" not in out:
            out.append("International")
    return out


_STATE_NAMES = dict(zip(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV "
    "NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split(),
    ["Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
     "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
     "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
     "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
     "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina",
     "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
     "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia",
     "Washington", "West Virginia", "Wisconsin", "Wyoming", "District of Columbia"]))
_CA_PROVINCES = {"ON": "Ontario", "QC": "Quebec", "BC": "British Columbia", "AB": "Alberta",
                 "MB": "Manitoba", "SK": "Saskatchewan", "NS": "Nova Scotia",
                 "NB": "New Brunswick"}
_COUNTRIES = [
    ("Canada", r"canada|toronto|vancouver|montr[eé]al|ottawa|waterloo|calgary"),
    ("United Kingdom", r"united kingdom|\buk\b|england|scotland|london|cambridge, (uk|gb)|\bgbr?\b"),
    ("Germany", r"germany|deutschland|berlin|munich|m[uü]nchen|\bdeu?\b"),
    ("France", r"france|paris|\bfra\b"),
    ("India", r"india|bangalore|bengaluru|hyderabad|pune|mumbai|gurgaon|chennai|\bind\b"),
    ("China", r"china|shanghai|beijing|shenzhen|hangzhou|\bchn\b"),
    ("Japan", r"japan|tokyo|\bjpn\b"),
    ("Singapore", r"singapore|\bsgp\b"),
    ("Ireland", r"ireland|dublin|\birl\b"),
    ("Netherlands", r"netherlands|amsterdam|eindhoven|\bnld\b"),
    ("Switzerland", r"switzerland|z[uü]rich|geneva|\bche\b"),
    ("Israel", r"israel|tel aviv|\bisr\b"),
    ("Australia", r"australia|sydney|melbourne|\baus\b"),
    ("Poland", r"poland|warsaw|krak[oó]w|\bpol\b"),
    ("Spain", r"spain|madrid|barcelona|\besp\b"),
    ("Italy", r"italy|milan|rome\b|\bita\b"),
    ("Sweden", r"sweden|stockholm|\bswe\b(?! intern)"),
    ("Mexico", r"mexico|\bmex\b"),
    ("Brazil", r"bra[sz]il|s[aã]o paulo|\bbra\b"),
    ("South Korea", r"korea|seoul|\bkor\b"),
    ("Taiwan", r"taiwan|taipei|hsinchu|\btwn\b"),
    ("Hong Kong", r"hong kong|\bhkg\b"),
    ("Romania", r"romania|bucharest"),
    ("Hungary", r"hungary|budapest"),
    ("Malaysia", r"malaysia|kuala lumpur|penang"),
    ("Philippines", r"philippines|manila"),
    ("United Arab Emirates", r"emirates|dubai|abu dhabi|\buae\b"),
]
_COUNTRY_PATS = [(name, re.compile(pat, re.I)) for name, pat in _COUNTRIES]


def places_of(locations: List[str], regions: List[str]) -> List[str]:
    """State and country names a posting's locations imply, spelled out, so a
    search for "Ohio" finds "Cincinnati, OH" and "Canada" finds "Toronto, ON"."""
    out: List[str] = []

    def add(name: str):
        if name not in out:
            out.append(name)

    for loc in locations:
        codes = _STATE_CODE.findall(loc)
        for c in codes:
            if c in _STATE_NAMES:
                add(_STATE_NAMES[c])
            elif c in _CA_PROVINCES and not _US_NAMES.search(loc):
                add(_CA_PROVINCES[c]); add("Canada")
        for name in _STATE_NAMES.values():
            if re.search(r"\b" + re.escape(name) + r"\b", loc, re.I):
                add(name)
        for name, pat in _COUNTRY_PATS:
            if pat.search(loc):
                add(name)
    if "US" in regions:
        add("United States")
    return out


def tag(rec: dict) -> None:
    title = rec["title"]
    degrees = " ".join(rec["degrees"])
    rec["phd"] = ("PhD" in rec["degrees"]) or bool(_PHD.search(title))
    rec["ms"] = bool(re.search(r"master|\bms\b", degrees, re.I)) or bool(_MS.search(title))
    rec["coop"] = bool(_COOP.search(title))
    tracks = []
    text = title + " " + " ".join(rec["categories"])
    for name, pat in _TRACKS:
        if pat.search(text):
            tracks.append(name)
    for c in rec["categories"]:
        t = _CATEGORY_TRACK.get(c.lower())
        if t and t not in tracks:
            tracks.append(t)
    rec["tracks"] = tracks
    rec["regions"] = region_of(rec["locations"])
    rec["places"] = places_of(rec["locations"], rec["regions"])


# ── state and output ────────────────────────────────────────────────────────
def load_json(path: str, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


PAGE_FIELDS = {"company", "title", "url", "locations", "places", "posted", "first_seen", "match", "match_basis", "match_resume", "sem", "sem_resume", "req", "tracks", "sources", "phd", "ms", "coop", "regions", "pay", "sponsorship"}


def slim(rec: dict) -> dict:
    """The record as published. Drops what is empty or repeats another field."""
    out = {k: v for k, v in rec.items() if v not in ("", [], None, {})}
    if out.get("urls") == [rec["url"]]:
        del out["urls"]
    for k in ("phd", "ms", "coop"):
        if not out.get(k):
            out.pop(k, None)
    return out


_DEFAULTS = {"urls": None, "locations": [], "posted": None, "degrees": [],
             "categories": [], "sponsorship": "", "pay": "", "notes": [],
             "sources": [], "ats": [], "phd": False, "ms": False, "coop": False,
             "tracks": [], "regions": [], "places": []}


def unslim(rec: dict) -> dict:
    out = dict(rec)
    for k, v in _DEFAULTS.items():
        if k not in out:
            out[k] = [rec["url"]] if k == "urls" else (list(v) if isinstance(v, list) else v)
    return out


CYCLE_START = "2026-06-01"       # postings from this day on count as this year's


def _loose(name: str) -> str:
    """A company name reduced to letters and digits, without a bracketed part
    or a legal suffix, for matching one source's spelling to another's."""
    name = re.sub(r"\([^)]*\)", " ", name or "")
    return re.sub(r"\s+", "", norm_company(name))


def write_timing(listings: List[dict]) -> int:
    """docs/timing.json: for each company that posted internships last summer,
    the day it first posted then, and what it has posted so far this year.
    Returns how many of them have posted nothing yet."""
    hist = load_json(os.path.join(DATA, "history.json"), {})
    now: Dict[str, dict] = {}
    for r in listings:
        day = r.get("posted") or r.get("first_seen") or ""
        if day < CYCLE_START:
            continue
        c = now.setdefault(_loose(r["company"]), {"n": 0, "first": day})
        c["n"] += 1
        c["first"] = min(c["first"], day)
    long_keys = [k for k in now if len(k) >= 6]

    def this_year(name: str) -> dict:
        """What this company has posted this year. Names differ between sources
        ("Procter & Gamble" and "Procter & Gamble (P&G)"), so one name starting
        with the other also counts as the same company."""
        key = _loose(name)
        if key in now:
            return now[key]
        if len(key) >= 6:
            for k in long_keys:
                if k.startswith(key) or key.startswith(k):
                    return now[k]
        return {}

    out = []
    for key, h in (hist.get("companies") or {}).items():
        y, m, d = (int(x) for x in h["first"].split("-"))
        if m == 2 and d == 29:
            d = 28
        expected = f"{y + 1:04d}-{m:02d}-{d:02d}"
        got = this_year(h["name"])
        row = {"name": h["name"], "last_first": h["first"], "last_n": h["n"],
               "last_phd": h["phd"], "last_phd_first": h.get("phd_first"),
               "expected": expected, "titles": h.get("titles", [])}
        if got:
            row["now_n"], row["now_first"] = got["n"], got["first"]
        out.append(row)
    out.sort(key=lambda c: (c["expected"], c["name"].lower()))
    with open(os.path.join(DOCS, "timing.json"), "w") as fh:
        json.dump({"last_cycle": hist.get("cycle", ""), "companies": out}, fh,
                  separators=(",", ":"))
    return sum(1 for c in out if not c.get("now_n"))


def write_outputs(listings: List[dict], new: List[dict], report: Dict[str, str],
                  first_run: bool, tabs: Optional[Dict[str, int]] = None) -> str:
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(DOCS, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    # With frequent runs, most find nothing changed. The large files are then
    # left alone, so the repository does not grow by megabytes every hour, and
    # only this small file records that the sources were checked.
    published = [slim(r) for r in listings]
    sig = hashlib.sha1(json.dumps(published, sort_keys=True).encode()).hexdigest()
    old = load_json(os.path.join(DOCS, "data.json"), {})
    unchanged = (old.get("sig") == sig and os.path.exists(os.path.join(DOCS, "list.json")))
    with open(os.path.join(DOCS, "checked.json"), "w") as fh:
        json.dump({"checked": now, "changed": old.get("generated") if unchanged else now,
                   "sources": report, "tabs": tabs or {}}, fh, separators=(",", ":"))
    path = os.path.join(OUT, f"new_{TODAY.isoformat()}.md")
    if unchanged:
        return path
    with open(os.path.join(DOCS, "data.json"), "w") as fh:
        json.dump({"generated": dt.datetime.now(dt.timezone.utc)
                                  .isoformat(timespec="seconds"),
                   "count": len(listings), "sources": report, "sig": sig,
                   # the day of the first build, when everything was "first seen"
                   "baseline": min((r["first_seen"] for r in listings), default=""),
                   "listings": [slim(r) for r in listings]}, fh,
                  separators=(",", ":"))
    # The page reads this smaller file. It carries only the fields the page shows.
    with open(os.path.join(DOCS, "list.json"), "w") as fh:
        json.dump({"generated": dt.datetime.now(dt.timezone.utc)
                                  .isoformat(timespec="seconds"),
                   "sources": report,
                   "baseline": min((r["first_seen"] for r in listings), default=""),
                   "listings": [{k: v for k, v in slim(r).items() if k in PAGE_FIELDS}
                                for r in listings]}, fh, separators=(",", ":"))
    cols = ["first_seen", "posted", "match", "match_resume", "match_basis",
            "sem", "sem_resume", "years", "degrees_asked", "gpa", "citizen",
            "clearance", "no_sponsor", "company", "title", "locations", "regions",
            "phd", "ms", "coop", "tracks", "degrees", "sponsorship", "pay",
            "sources", "url", "id"]
    with open(os.path.join(DOCS, "listings.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in listings:
            q = r.get("req") or {}
            flat = dict(r, years=q.get("years", ""), degrees_asked=q.get("degrees", []),
                        gpa=q.get("gpa", ""), citizen="yes" if q.get("citizen") else "",
                        clearance="yes" if q.get("clearance") else "",
                        no_sponsor="yes" if q.get("no_sponsor") else "")
            w.writerow(["; ".join(flat[c]) if isinstance(flat.get(c), list)
                        else flat.get(c, "") for c in cols])
    # One report per day. A second run on the same day adds a section to it and
    # never replaces what an earlier run found.
    path = os.path.join(OUT, f"new_{TODAY.isoformat()}.md")
    exists = os.path.exists(path)
    if exists and not new:
        return path
    with open(path, "a") as fh:
        if not exists:
            fh.write(f"# New listings, {TODAY.isoformat()}\n\n")
        else:
            fh.write(f"\n## Later run at {dt.datetime.now().strftime('%H.%M')}\n\n")
        if first_run:
            fh.write("First run, so every listing counts as new. Later runs "
                     "show only what appeared since the run before.\n\n")
        fh.write(f"{len(new)} new of {len(listings)} active.\n\n")
        fh.write("| Posted | Company | Title | Location | PhD | Sources |\n")
        fh.write("|---|---|---|---|---|---|\n")
        for r in new:
            loc = "; ".join(r["locations"][:2]) + (" +" + str(len(r["locations"]) - 2)
                                                  if len(r["locations"]) > 2 else "")
            title = r["title"].replace("|", "/")
            fh.write(f"| {r['posted'] or ''} | {r['company'].replace('|', '/')} | "
                     f"[{title}]({r['url']}) | {loc.replace('|', '/')} | "
                     f"{'yes' if r['phd'] else ''} | {', '.join(r['sources'])} |\n")
    return path


# A company feed returns every internship the company has, in every department,
# and some feeds never retire old postings. A board has already made those
# choices, so its listings are kept as they are.
CAREERS_MAX_AGE_DAYS = 180


def keep(rec: dict) -> bool:
    """False for a listing found only on a company site that is not a technical
    role or is older than CAREERS_MAX_AGE_DAYS."""
    if rec["sources"] != ["careers"]:
        return True
    if not rec["tracks"]:
        return False
    if rec["posted"]:
        oldest = (TODAY - dt.timedelta(days=CAREERS_MAX_AGE_DAYS)).isoformat()
        if rec["posted"] < oldest:
            return False
    return True


NEVER_WORKED_TRIES = 4


def update_registry(companies: Dict[str, dict], rows: List[dict]) -> int:
    """Remember the career site behind every board link. Returns how many are new."""
    added = 0
    for r in rows:
        found = ats.discover(r["url"])
        if not found:
            continue
        key = f"{found[0]}:{found[1]}"
        if key not in companies:
            companies[key] = {"name": r["company"], "added": TODAY.isoformat()}
            added += 1
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", default="", help="comma-separated board names")
    ap.add_argument("--no-careers", action="store_true",
                    help="skip the company career sites")
    ap.add_argument("--describe", type=int, default=600, metavar="N",
                    help="read at most N new posting descriptions this run "
                         "(default 600, 0 to skip)")
    ap.add_argument("--list", action="store_true", help="show the boards and stop")
    a = ap.parse_args()
    if a.list:
        print("\n".join(SOURCES))
        return 0
    names = [n.strip() for n in a.only.split(",") if n.strip()] or list(SOURCES)
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        print(f"unknown source: {', '.join(unknown)}", file=sys.stderr)
        return 2

    rows: List[dict] = []
    report: Dict[str, str] = {}
    failed: List[str] = []
    for n in names:
        t0 = time.time()
        try:
            got = SOURCES[n]()
            rows += got
            report[n] = f"{len(got)} listings"
            if not got:
                failed.append(n)          # an empty source is treated as a failure
                report[n] = "0 listings (format may have changed)"
        except Exception as e:                            # noqa: BLE001
            failed.append(n)
            report[n] = f"FAILED: {type(e).__name__}: {e}"
        print(f"  {n:14s} {report[n]}  ({time.time() - t0:.1f}s)", flush=True)

    board_rows = list(rows)          # kept for the "check by hand" list below

    # Company career sites, found through the board links above.
    os.makedirs(DATA, exist_ok=True)
    companies = load_json(os.path.join(DATA, "companies.json"), {})
    added = update_registry(companies, rows)
    failed_sites: Dict[str, str] = {}
    careers_ran = not a.no_careers
    if careers_ran:
        t0 = time.time()
        got, failed_sites = ats.collect(
            companies, lambda url, json_body=None: fetch(url, 25, json_body), listing,
            progress=lambda n, total: print(f"    careers {n}/{total}", flush=True))
        rows += got
        report["careers"] = (f"{len(got)} listings from {len(companies)} company "
                             f"sites, {len(failed_sites)} unreachable")
        print(f"  {'careers':14s} {report['careers']}  ({time.time() - t0:.1f}s)",
              flush=True)
        for key in list(companies):
            entry = companies[key]
            entry["ok"] = key not in failed_sites
            if entry["ok"]:
                entry["worked"] = True
                entry["fails"] = 0
            else:
                entry["fails"] = entry.get("fails", 0) + 1
                # An identifier that has never answered is a bad guess, not an
                # employer that went quiet, so it is forgotten after a few tries.
                if not entry.get("worked") and entry["fails"] >= NEVER_WORKED_TRIES:
                    del companies[key]
    with open(os.path.join(DATA, "companies.json"), "w") as fh:
        json.dump(companies, fh, indent=0, sort_keys=True)

    listings = [r for r in merge(rows) if keep(r)]

    seen = load_json(os.path.join(DATA, "seen.json"), {})
    first_run = not seen
    prev = {r["id"]: unslim(r) for r in load_json(os.path.join(DOCS, "data.json"),
                                                  {}).get("listings", [])}
    # Keep earlier listings from any source that failed or was not run, so a
    # broken board or an unreachable career site does not make postings vanish.
    skipped = set(failed) | (set(SOURCES) - set(names))
    have = {r["id"] for r in listings}
    for pid, p in prev.items():
        if pid in have:
            continue
        boards = set(p.get("sources", [])) - {"careers"}
        sites = set(p.get("ats", []))
        if (boards & skipped) or (sites and not careers_ran) or (sites & set(failed_sites)):
            tag(p)                # so a carried-over listing gets any new tags
            listings.append(p)

    new = []
    for r in listings:
        if r["id"] not in seen:
            seen[r["id"]] = TODAY.isoformat()
            new.append(r)
        r["first_seen"] = seen[r["id"]]
    # Newest first. A listing with no posting date sorts by the day it was first
    # seen, except on the first run, where that day says nothing about its age.
    key = lambda r: (r["posted"] or ("" if first_run else r["first_seen"]),
                     r["company"].lower())
    listings.sort(key=key, reverse=True)
    new.sort(key=key, reverse=True)

    # Read descriptions and score each listing against the resume profile.
    t0 = time.time()
    m = match.enrich(listings, lambda url, json_body=None: fetch(url, 20, json_body),
                     a.describe,
                     progress=lambda n, total: print(f"    descriptions {n}/{total}",
                                                     flush=True))
    report["match"] = (f"{m['described']} of {len(listings)} descriptions read"
                       + ("" if m["scored"] else ", no resume profile so no scores"))
    print(f"  {'match':14s} {report['match']}  ({time.time() - t0:.1f}s)", flush=True)

    # Score by meaning with a small open-source embedding model. On the machine
    # that keeps the description text, anything still unscored is filled in.
    t0 = time.time()
    stored = match._load_texts() if os.path.exists(match.TEXTS) else None
    sem = semantic.enrich(listings, match.FRESH, stored)
    report["meaning"] = (f"{sem['scored']} listings scored, {sem.get('new', 0)} new"
                         if sem["scored"] else f"skipped, {sem.get('note', '')}")
    print(f"  {'meaning':14s} {report['meaning']}  ({time.time() - t0:.1f}s)", flush=True)

    # Employers whose jobs cannot be read: sites no reader understands, and
    # career sites that used to answer and have stopped.
    failing = [{"name": e["name"], "url": ats.careers_url(k),
                "platform": k.split(":", 1)[0].title(), "origin": "feed not answering",
                "note": f"Its job feed has not answered for {e['fails']} runs in a row"}
               for k, e in companies.items() if e.get("worked") and e.get("fails", 0) >= 6]
    by_hand = manual.write(DOCS, DATA, manual.from_listings(board_rows, ats.discover), failing)
    waiting = write_timing(listings)

    path = write_outputs(listings, new, report, first_run,
                         tabs={"timing": waiting, "manual": by_hand})
    with open(os.path.join(DATA, "seen.json"), "w") as fh:
        json.dump(seen, fh, separators=(",", ":"), sort_keys=True)

    only_careers = sum(1 for r in listings if r["sources"] == ["careers"])
    print(f"\n  {len(rows)} raw rows -> {len(listings)} listings after merging")
    print(f"  {only_careers} found only on a company site, "
          f"{sum(1 for r in listings if r['phd'])} mention a PhD, "
          f"{sum(1 for r in listings if r['coop'])} are co-ops")
    print(f"  {len(new)} new" + (" (first run)" if first_run else "")
          + f", {added} company sites added to the registry")
    print(f"  wrote {os.path.relpath(path, HERE)}, docs/data.json, docs/listings.csv")
    if failed:
        print(f"  check these boards: {', '.join(failed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
