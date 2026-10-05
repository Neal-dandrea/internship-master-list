"""manual.py — the list of employers whose jobs cannot be read automatically.

Some employers run their careers pages on their own software, or on a platform
this collector has no reader for. Their postings cannot be pulled into the list,
so they are logged here instead, each with a link, to be visited by hand.

The list has three origins.

  1. data/manual.json, written by hand: employers known to matter.
  2. Job board listings whose link points at a site no reader understands. These
     are found on every run, grouped by site, with a count of the postings seen.
  3. Employers in data/companies.json whose feed has stopped answering.

This file is shared by both boards. Each board keeps its own copy.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
from collections import Counter
from typing import Dict, List

# Sites that only pass a reader along to the real posting.
AGGREGATORS = ("zapply.jobs", "simplify.jobs", "themuse.com", "linkedin.com", "indeed.com",
               "glassdoor.com", "ziprecruiter.com", "wellfound.com", "ycombinator.com",
               "handshake.com", "joinhandshake.com", "google.com/url", "bit.ly", "lnkd.in",
               "jobright.ai", "builtin.com", "docs.google.com", "forms.gle", "notion.site")
# Platforms recognised by their address, for the "platform" column.
PLATFORMS = [
    ("Taleo", r"taleo\.net"), ("SuccessFactors", r"successfactors\.|jobs\.sap\.com|sapsf\."),
    ("Avature", r"avature\.net"), ("Phenom", r"phenompeople|phenom\.com"),
    ("BrassRing", r"brassring\.com"), ("Dayforce", r"dayforcehcm\.com"),
    ("ADP", r"\badp\.com"), ("Paylocity", r"paylocity\.com"), ("Paycom", r"paycomonline"),
    ("BambooHR", r"bamboohr\.com"), ("Jobvite", r"jobvite\.com"), ("Rippling", r"rippling\.com"),
    ("JazzHR", r"applytojob\.com"), ("Teamtailor", r"teamtailor\.com"),
    ("Personio", r"personio\.(com|de)"), ("Recruitee", r"recruitee\.com"),
    ("Breezy", r"breezy\.hr"), ("Pinpoint", r"pinpointhq\.com"), ("TriNet", r"trinethire\.com"),
    ("Gem", r"jobs\.gem\.com"), ("Comeet", r"comeet\.(co|com)"), ("Workable", r"workable\.com"),
    ("Symphony Talent", r"symphonytalent|m-cloud\.io"), ("Cornerstone", r"csod\.com"),
    ("PeopleAdmin", r"peopleadmin\.com"), ("PageUp", r"pageuppeople\.com"),
    ("NeoGov", r"governmentjobs\.com"), ("USAJOBS", r"usajobs\.gov"),
    ("Interfolio", r"interfolio\.com"), ("Kula", r"kula\.ai"), ("Dover", r"dover\.(com|io)"),
]
_PLATFORM_PATS = [(name, re.compile(pat, re.I)) for name, pat in PLATFORMS]
# On these hosts the employer is the first part of the path, not the host.
_PATH_TENANT = re.compile(r"ats\.rippling\.com|jobs\.jobvite\.com|jobs\.dayforcehcm\.com|"
                          r"jobs\.gem\.com|careers-page\.com|jobs\.kula\.ai|app\.dover\.com", re.I)


def platform_of(url: str) -> str:
    for name, pat in _PLATFORM_PATS:
        if pat.search(url):
            return name
    return "Own site"


def _site_key(url: str):
    """(key, landing page) for the employer site a posting link belongs to."""
    p = urllib.parse.urlsplit(url)
    host = p.netloc.lower().removeprefix("www.")
    if not host:
        return None, None
    if _PATH_TENANT.search(host):
        first = p.path.strip("/").split("/")[0]
        return f"{host}/{first}", f"https://{host}/{first}"
    return host, f"https://{p.netloc}"


def from_listings(rows: List[dict], discover) -> List[dict]:
    """Employer sites behind board listings that no reader understands.

    `rows` are raw board rows (company, url). `discover(url)` returns something
    truthy when a reader exists for that link."""
    groups: Dict[str, dict] = {}
    for r in rows:
        url = r.get("url") or ""
        if not url.startswith("http") or discover(url):
            continue
        if any(a in url for a in AGGREGATORS):
            continue
        key, landing = _site_key(url)
        if not key:
            continue
        g = groups.setdefault(key, {"names": Counter(), "url": landing, "count": 0,
                                    "example": url})
        g["names"][r.get("company") or key] += 1
        g["count"] += 1
    out = []
    for key, g in groups.items():
        out.append({"name": g["names"].most_common(1)[0][0], "url": g["url"],
                    "platform": platform_of(g["example"]), "count": g["count"],
                    "example": g["example"], "origin": "boards"})
    return out


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def write(docs_dir: str, data_dir: str, found: List[dict], failing: List[dict]) -> int:
    """Merge the three origins and write docs/manual.json. Returns the count."""
    try:
        with open(os.path.join(data_dir, "manual.json")) as fh:
            curated = json.load(fh)
    except (FileNotFoundError, ValueError):
        curated = []
    merged: Dict[str, dict] = {}
    for e in curated:
        merged[_norm(e["name"])] = {"name": e["name"], "url": e["url"],
                                    "platform": e.get("platform") or platform_of(e["url"]),
                                    "note": e.get("note", ""), "origin": "listed by hand"}
    for e in found:
        k = _norm(e["name"])
        if k in merged:                      # keep the hand-written link, add the count
            merged[k]["count"] = merged[k].get("count", 0) + e["count"]
            merged[k].setdefault("example", e["example"])
        else:
            merged[k] = dict(e)
    for e in failing:
        merged.setdefault(_norm(e["name"]), e)
    rows = sorted(merged.values(), key=lambda e: (-e.get("count", 0), e["name"].lower()))
    with open(os.path.join(docs_dir, "manual.json"), "w") as fh:
        json.dump({"count": len(rows), "employers": rows}, fh, separators=(",", ":"))
    return len(rows)
