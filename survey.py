#!/usr/bin/env python3
"""survey.py — find which of many candidate companies actually post internships.

data/candidates.json holds tens of thousands of company career sites gathered
from public lists. Reading all of them every hour would be slow and rude, and
most never post an internship. So the hourly collector only reads the sites in
data/companies.json, and this script is how a site gets onto that list.

It reads each candidate once. A candidate with at least one internship open
right now is added to data/companies.json, and the collector picks it up from
then on. The rest are left as candidates and looked at again on a later pass,
since a company with nothing today may post next month.

    python3 survey.py                  # every candidate not yet in the registry
    python3 survey.py --slice 3 7      # only the 4th seventh, for a daily rotation
    python3 survey.py --limit 500      # a quick test

A candidate's site is never read more than once per run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ats
import collect

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = os.path.join(HERE, "data", "candidates.json")
REGISTRY = os.path.join(HERE, "data", "companies.json")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--slice", nargs=2, type=int, metavar=("N", "OF"),
                    help="only candidates in slice N of OF (N counts from 0)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=24)
    a = ap.parse_args()

    candidates = collect.load_json(CANDIDATES, {})
    companies = collect.load_json(REGISTRY, {})
    todo = [k for k in candidates
            if k not in companies and k.split(":", 1)[0] in ats.READERS]
    if a.slice:
        n, of = a.slice
        todo = [k for k in todo
                if int(hashlib.sha1(k.encode()).hexdigest(), 16) % of == n]
    if a.limit:
        todo = todo[:a.limit]
    print(f"  {len(todo)} candidates to read ({len(candidates)} known, "
          f"{len(companies)} already in the registry)", flush=True)

    def fetch(url, json_body=None, headers=None):
        return collect.fetch(url, 15, json_body, headers)

    def one(key):
        platform, token = key.split(":", 1)
        try:
            rows = ats.READERS[platform](token, candidates[key], fetch, collect.listing)
            return key, len(rows), None
        except Exception as e:                            # noqa: BLE001
            return key, 0, type(e).__name__

    t0, found, dead, done = time.time(), 0, 0, 0
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for key, n, err in pool.map(one, todo):
            done += 1
            if err:
                dead += 1
            elif n:
                found += 1
                companies[key] = {"name": candidates[key], "worked": True, "ok": True,
                                  "fails": 0, "added": dt.date.today().isoformat(),
                                  "from": "survey"}
            if done % 2000 == 0:
                print(f"    {done}/{len(todo)}  {found} with internships, "
                      f"{dead} did not answer  ({time.time() - t0:.0f}s)", flush=True)
                with open(REGISTRY, "w") as fh:          # keep progress if interrupted
                    json.dump(companies, fh, indent=0, sort_keys=True)
    with open(REGISTRY, "w") as fh:
        json.dump(companies, fh, indent=0, sort_keys=True)
    print(f"  read {done} candidates in {time.time() - t0:.0f}s: {found} have "
          f"internships now and were added, {dead} did not answer")
    print(f"  the registry now holds {len(companies)} career sites")
    return 0


if __name__ == "__main__":
    sys.exit(main())
