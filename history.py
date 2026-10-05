#!/usr/bin/env python3
"""history.py — when each company opened its summer internship applications last year.

The SimplifyJobs internship board keeps one data file and overwrites it as the
year goes on, but its version history still holds older copies. This reads the
copy from the end of January, which covers the previous cycle from June through
January, plus the current file, and keeps every listing for LAST summer.

For each company it records the day its first listing for that summer appeared,
how many it posted, and how many of those were for PhD students. The collector
compares that with what the company has posted so far this year (timing.py in
collect.py), which is what the "Not posted yet" tab shows.

    python3 history.py --build      # rewrites data/history.json, about a minute

The cycle is set by CYCLE below. Change it once a year.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

import collect

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "history.json")
REPO = "SimplifyJobs/Summer2027-Internships"
PATH = ".github/scripts/listings.json"
CYCLE = "Summer 2026"            # the summer whose postings count as "last year"
SNAPSHOT_BEFORE = "2026-01-31"   # the stored copy to read, taken just before this day
_PHD = re.compile(r"\bph\.?\s?d\b|doctoral|doctorate", re.I)


def _iso(ts) -> str:
    return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).date().isoformat()


def build() -> None:
    api = (f"https://api.github.com/repos/{REPO}/commits?path={PATH}"
           f"&until={SNAPSHOT_BEFORE}T00:00:00Z&per_page=1&sha=dev")
    sha = json.loads(collect.fetch(api))[0]["sha"]
    old = json.loads(collect.fetch(f"{collect.RAW}/{REPO}/{sha}/{PATH}", timeout=120))
    new = json.loads(collect.fetch(f"{collect.RAW}/{REPO}/dev/{PATH}", timeout=120))
    seen, companies = set(), {}
    for x in old + new:
        if CYCLE not in (x.get("terms") or []) or not x.get("date_posted"):
            continue
        if x["id"] in seen:
            continue
        seen.add(x["id"])
        key = collect.norm_company(x["company_name"])
        if not key:
            continue
        day = _iso(x["date_posted"])
        c = companies.setdefault(key, {"name": x["company_name"], "first": day, "n": 0,
                                       "phd": 0, "phd_first": None, "titles": []})
        c["n"] += 1
        c["first"] = min(c["first"], day)
        is_phd = "PhD" in (x.get("degrees") or []) or bool(_PHD.search(x.get("title") or ""))
        if is_phd:
            c["phd"] += 1
            c["phd_first"] = min(c["phd_first"] or day, day)
        if len(c["titles"]) < 3 and x.get("title") not in c["titles"]:
            c["titles"].append(x["title"])
    with open(OUT, "w") as fh:
        json.dump({"cycle": CYCLE, "built": dt.date.today().isoformat(),
                   "companies": companies}, fh, separators=(",", ":"), sort_keys=True)
    print(f"  {len(seen)} listings for {CYCLE} from {len(companies)} companies")
    months = {}
    for c in companies.values():
        months[c["first"][:7]] = months.get(c["first"][:7], 0) + 1
    print("  companies by the month of their first listing:",
          ", ".join(f"{m} {n}" for m, n in sorted(months.items())))


if __name__ == "__main__":
    if "--build" in sys.argv:
        build()
    else:
        print(__doc__)
