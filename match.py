#!/usr/bin/env python3
"""match.py — read each posting's description and score it against a resume.

HOW A SCORE IS MADE

  1. The posting's description is fetched once and reduced to the vocabulary
     terms it mentions (see skills.py). Those terms are cached in
     data/terms.json, so a posting is only ever fetched one time.
  2. Each resume is reduced to its terms the same way, once, into a profile.
  3. The score asks one question. Of the things this posting mentions, weighted
     so that rare and specific terms count for more than common ones, how much
     is on the resume?

     A posting that names twelve things with ten on the resume scores high. A
     posting that names two things, both on the resume, scores in the middle,
     because two terms is thin evidence. A posting whose description could not
     be read is scored from its title alone and marked that way.

  With several resumes, a posting takes its best score and records which resume
  produced it.

THE PROFILE IS PRIVATE. It comes from the RESUME_PROFILE environment variable or
from private/profile.json, and neither is ever committed. Only the resulting
number and the name of the best-fitting resume are published.

USAGE

    python3 match.py --build-profile General=cv.pdf Quant=quant.pdf
    python3 match.py --gaps           # terms postings ask for that no resume has
    python3 match.py --reextract      # after editing skills.py, on the machine
                                      # that holds the stored description text
"""
from __future__ import annotations

import gzip
import html
import json
import math
import os
import re
import subprocess
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Set

import requirements
import skills

HERE = os.path.dirname(os.path.abspath(__file__))
TERMS = os.path.join(HERE, "data", "terms.json")
PROFILE = os.path.join(HERE, "private", "profile.json")
# The raw description text is kept only on a machine that has a private/
# directory. It lets `--reextract` rebuild every posting's terms after the
# vocabulary changes, without fetching anything again.
TEXTS = os.path.join(HERE, "private", "descriptions.json.gz")
MAX_TRIES = 3            # give up on a description after this many failed runs
# Descriptions read during this run, by posting id. The embedding score and the
# requirement extraction need the text itself, which is not kept in the
# repository, so they work from this.
FRESH: Dict[str, str] = {}


# ── reading a description ───────────────────────────────────────────────────
_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)


_BLOCK = re.compile(r"<\s*(br|/p|/li|/div|/h[1-6]|/tr|/ul|/ol|li|p)\b[^>]*>", re.I)


def plain(markup: str) -> str:
    """Text with the markup removed. List items and paragraphs stay on their own
    lines, because a bulleted requirement is a sentence of its own even though
    it has no full stop."""
    text = html.unescape(html.unescape(markup or ""))
    text = _TAGS.sub(" ", _BLOCK.sub("\n", text))
    lines = (" ".join(line.split()) for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


_WORKDAY = re.compile(r"https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/"
                      r"(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)(/job/[^?#]+)")
_GREENHOUSE = re.compile(r"greenhouse\.io/([A-Za-z0-9_-]+)/jobs/(\d+)")
# zapply links are redirects that spell out the platform, company and job id.
_ZAPPLY_GH = re.compile(r"zapply\.jobs/l/d/greenhouse-([A-Za-z0-9_]+)-(\d+)")
_GH_JID = re.compile(r"[?&]gh_jid=(\d+)")
_LEVER = re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]+)/([0-9a-f-]{36})")
_ASHBY = re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)/([0-9a-f-]{36})")
_SMART = re.compile(r"jobs\.smartrecruiters\.com/([A-Za-z0-9_-]+)/(\d+)")
_ORACLE = re.compile(r"https?://([a-z0-9.-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/"
                     r"[a-z-]+/sites/([A-Za-z0-9_-]+)/(?:job|requisitions/preview)/(\d+)")
_JSONLD = re.compile(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.S | re.I)


def _jsonld_description(page: str) -> str:
    for block in _JSONLD.findall(page):
        try:
            doc = json.loads(block)
        except ValueError:
            continue
        for item in (doc if isinstance(doc, list) else [doc]):
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return plain(str(item.get("description") or ""))
    return ""


def describe(url: str, ats: List[str], fetch: Callable, ashby_cache: dict) -> str:
    """The posting's description as plain text, or "" when it cannot be read."""
    m = _WORKDAY.search(url)
    if m:
        tenant, wd, site, path = m.groups()
        path = re.sub(r"/apply/?$", "", path)
        doc = json.loads(fetch(f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/"
                               f"{tenant}/{site}{path}"))
        return plain((doc.get("jobPostingInfo") or {}).get("jobDescription") or "")
    m = _GREENHOUSE.search(url) or _ZAPPLY_GH.search(url)
    token, job = (m.groups() if m else (None, None))
    if not m:
        j = _GH_JID.search(url)
        t = next((a.split(":", 1)[1] for a in ats if a.startswith("greenhouse:")), None)
        if j and t:
            token, job = t, j.group(1)
    if token:
        doc = json.loads(fetch(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job}"))
        return plain(doc.get("content") or "")
    m = _LEVER.search(url)
    if m:
        doc = json.loads(fetch(f"https://api.lever.co/v0/postings/{m.group(1)}/{m.group(2)}"))
        parts = [doc.get("descriptionPlain") or "", doc.get("additionalPlain") or ""]
        parts += [plain(x.get("text", "") + " " + x.get("content", ""))
                  for x in doc.get("lists") or []]
        return " ".join(parts).strip()
    m = _ASHBY.search(url)
    if m:
        token = urllib.parse.unquote(m.group(1))
        if token not in ashby_cache:
            board = json.loads(fetch("https://api.ashbyhq.com/posting-api/job-board/"
                                     + urllib.parse.quote(token)))
            ashby_cache[token] = {j.get("id") or j.get("jobUrl", "").rsplit("/", 1)[-1]:
                                  j.get("descriptionPlain") or plain(j.get("descriptionHtml") or "")
                                  for j in board.get("jobs", [])}
        return ashby_cache[token].get(m.group(2), "")
    m = _SMART.search(url)
    if m:
        doc = json.loads(fetch("https://api.smartrecruiters.com/v1/companies/"
                               f"{m.group(1)}/postings/{m.group(2)}"))
        sections = ((doc.get("jobAd") or {}).get("sections") or {}).values()
        return plain(" ".join(s.get("text", "") for s in sections if isinstance(s, dict)))
    m = _ORACLE.search(url)
    if m:
        host, site, job = m.groups()
        doc = json.loads(fetch(
            f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
            f"?expand=all&onlyData=true&finder=ById;Id=%22{job}%22,siteNumber={site}"))
        item = (doc.get("items") or [{}])[0]
        return plain(" ".join(str(item.get(k) or "") for k in (
            "ExternalDescriptionStr", "ExternalQualificationsStr",
            "ExternalResponsibilitiesStr", "CorporateDescriptionStr")))
    # Anything else: many career pages embed the posting as structured data.
    return _jsonld_description(fetch(url).decode("utf-8", errors="replace"))


# ── the term cache ──────────────────────────────────────────────────────────
def _load(path: str, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return default


def title_terms(rec: dict) -> Set[str]:
    return skills.extract(rec["title"] + " . " + " . ".join(rec.get("categories") or []))


def read_descriptions(listings: List[dict], fetch: Callable, budget: int,
                      workers: int = 8, progress=None) -> Dict[str, dict]:
    """Fill the term cache for up to `budget` postings that have none yet.

    Returns the cache, pruned to the postings that are still active. Each entry
    is {"t": [terms], "b": "d" for description or "t" for title only, "n": tries,
    "q": the hard requirements found in the description (see requirements.py)}.
    """
    cache = _load(TERMS, {})
    cache = {r["id"]: cache[r["id"]] for r in listings if r["id"] in cache}
    todo = [r for r in listings
            if r["id"] not in cache
            or (cache[r["id"]]["b"] == "t" and cache[r["id"]].get("n", 0) < MAX_TRIES)]
    todo = todo[:max(0, budget)]
    ashby_cache: dict = {}

    def one(rec: dict):
        text = ""
        for url in rec.get("urls") or [rec["url"]]:
            try:
                text = describe(url, rec.get("ats") or [], fetch, ashby_cache)
            except Exception:                              # noqa: BLE001
                text = ""
            if len(text) > 200:
                break
        return rec, text

    keep_text = os.path.isdir(os.path.dirname(TEXTS))
    texts = _load_texts() if keep_text else {}
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for rec, text in pool.map(one, todo):
            tries = cache.get(rec["id"], {}).get("n", 0) + 1
            terms = title_terms(rec)
            if len(text) > 200:
                terms |= skills.extract(text)
                cache[rec["id"]] = {"t": sorted(terms), "b": "d", "n": tries,
                                    "q": requirements.extract(text)}
                texts[rec["id"]] = text
                FRESH[rec["id"]] = text
            else:
                cache[rec["id"]] = {"t": sorted(terms), "b": "t", "n": tries}
            done += 1
            if progress and done % 200 == 0:
                progress(done, len(todo))
    for rec in listings:                       # anything over budget: title only, untried
        cache.setdefault(rec["id"], {"t": sorted(title_terms(rec)), "b": "t", "n": 0})
    if keep_text:
        _save_texts({k: v for k, v in texts.items() if k in cache})
    _save_terms(cache)
    return cache


def _save_terms(cache: Dict[str, dict]) -> None:
    os.makedirs(os.path.dirname(TERMS), exist_ok=True)
    with open(TERMS, "w") as fh:
        json.dump(cache, fh, separators=(",", ":"), sort_keys=True)


def _load_texts() -> Dict[str, str]:
    try:
        with gzip.open(TEXTS, "rt") as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _save_texts(texts: Dict[str, str]) -> None:
    with gzip.open(TEXTS, "wt") as fh:
        json.dump(texts, fh)


def reextract() -> None:
    """Rebuild every cached posting's terms from the stored text and titles.
    Run this after changing skills.py."""
    cache, texts = _load(TERMS, {}), _load_texts()
    listings = {r["id"]: r for r in _load(os.path.join(HERE, "docs", "data.json"),
                                          {}).get("listings", [])}
    redone = 0
    for pid, entry in cache.items():
        rec = listings.get(pid)
        terms = title_terms(rec) if rec else set()
        if pid in texts:
            terms |= skills.extract(texts[pid])
            entry["b"] = "d"
            entry["q"] = requirements.extract(texts[pid])
            redone += 1
        elif entry["b"] == "d":
            continue                 # no stored text for it; leave its terms alone
        entry["t"] = sorted(terms)
    _save_terms(cache)
    print(f"  rebuilt terms for {redone} postings from stored text")


# ── scoring ─────────────────────────────────────────────────────────────────
def load_profile() -> Dict[str, Set[str]]:
    raw = os.environ.get("RESUME_PROFILE", "").strip()
    doc = json.loads(raw) if raw else _load(PROFILE, {})
    return {name: set(terms) for name, terms in doc.items()}   # keeps file order


def term_weights(cache: Dict[str, dict]) -> Dict[str, float]:
    """Rare terms count for more. A term in half of all postings (Python) is worth
    well under a fifth of one that appears in a handful (KDB+)."""
    docs = [e["t"] for e in cache.values() if e["b"] == "d"] or \
           [e["t"] for e in cache.values()]
    n = max(len(docs), 1)
    df: Dict[str, int] = {}
    for terms in docs:
        for t in terms:
            df[t] = df.get(t, 0) + 1
    return {t: min(5.0, max(0.2, math.log(n / (1 + df.get(t, 0)))))
            for t in skills.VOCAB}


def score(job: Set[str], resume: Set[str], w: Dict[str, float]) -> int:
    if not job:
        return 0
    asked = sum(w.get(t, 1.0) for t in job)
    have = sum(w.get(t, 1.0) for t in job & resume)
    # Half the score is coverage: the share of what the posting asks for that is
    # on the resume. It is pulled toward a low prior when the posting says
    # little, so two matching terms do not outrank ten of twelve.
    coverage = (have + PRIOR_WEIGHT * PRIOR) / (asked + PRIOR_WEIGHT)
    # The other half is depth: how much matching evidence there is in total.
    depth = min(1.0, have / FULL_DEPTH)
    return round(100 * (0.5 * coverage + 0.5 * depth))


# Settings chosen on 2026-10-04 against about 5,200 real postings, so that
# roughly one posting in six scores 70 or more and the median sits near 40.
PRIOR, PRIOR_WEIGHT, FULL_DEPTH = 0.1, 14.0, 28.0


def enrich(listings: List[dict], fetch: Callable, budget: int, progress=None) -> dict:
    """Read descriptions, then set match / match_resume / match_basis on each
    listing. Returns counts for the run report."""
    cache = read_descriptions(listings, fetch, budget, progress=progress)
    profile = load_profile()
    described = sum(1 for e in cache.values() if e["b"] == "d")
    for r in listings:
        if cache[r["id"]].get("q"):
            r["req"] = cache[r["id"]]["q"]
        else:
            r.pop("req", None)
    if not profile:
        for r in listings:
            for k in ("match", "match_resume", "match_basis"):
                r.pop(k, None)
        return {"described": described, "scored": 0}
    w = term_weights(cache)
    for r in listings:
        entry = cache[r["id"]]
        job = set(entry["t"])
        scores = {name: score(job, profile[name], w) for name in profile}
        top = max(scores.values())
        tied = [name for name in profile if scores[name] == top]
        # The first resume in the profile is the general one. When every resume
        # ties it is named. When a focused resume ties with it and beats the
        # other focused ones, the focused resume is named, since it is the
        # better one to send.
        best = tied[0] if len(tied) == len(profile) or len(tied) == 1 else \
            next((name for name in tied if name != next(iter(profile))), tied[0])
        r["match"] = top
        r["match_resume"] = best
        r["match_basis"] = "description" if entry["b"] == "d" else "title"
    return {"described": described, "scored": len(listings)}


# ── command line ────────────────────────────────────────────────────────────
def resume_text(path: str) -> str:
    """Plain text of a resume in PDF or Word format."""
    if path.lower().endswith(".docx"):
        import zipfile
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        # Word splits a word across formatting runs, so tags are removed without
        # adding a space, except for paragraph ends and tabs.
        xml = re.sub(r"<w:tab/>|<w:br/>", " ", xml.replace("</w:p>", "\n"))
        text = html.unescape(re.sub(r"<[^>]+>", "", xml))
    else:
        text = subprocess.run(["pdftotext", "-layout", path, "-"],
                              capture_output=True, text=True, check=True).stdout
    return re.sub(r"[ \t]+", " ", text)



def build_profile(pairs: List[str]) -> None:
    out = {}
    for pair in pairs:
        name, path = pair.split("=", 1)
        text = resume_text(os.path.expanduser(path))
        out[name] = sorted(skills.expand(skills.extract(text)))
        print(f"  {name}: {len(out[name])} terms")
    os.makedirs(os.path.dirname(PROFILE), exist_ok=True)
    with open(PROFILE, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"  wrote {os.path.relpath(PROFILE, HERE)} (private, not committed)")


def gaps(top: int = 30) -> None:
    """Terms that postings mention most often and no resume has."""
    cache, profile = _load(TERMS, {}), load_profile()
    have = set().union(*profile.values()) if profile else set()
    docs = [e["t"] for e in cache.values() if e["b"] == "d"]
    count: Dict[str, int] = {}
    for terms in docs:
        for t in terms:
            if t not in have:
                count[t] = count.get(t, 0) + 1
    print(f"  {len(docs)} postings with a description read")
    for t, n in sorted(count.items(), key=lambda x: -x[1])[:top]:
        print(f"  {n:6d}  {100 * n / max(len(docs), 1):5.1f}%  {t}")


if __name__ == "__main__":
    if "--build-profile" in sys.argv:
        build_profile(sys.argv[sys.argv.index("--build-profile") + 1:])
    elif "--gaps" in sys.argv:
        gaps()
    elif "--reextract" in sys.argv:
        reextract()
    else:
        print(__doc__)
