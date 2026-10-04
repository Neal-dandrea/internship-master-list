#!/usr/bin/env python3
"""semantic.py — score a posting against a resume by meaning, not by shared words.

The keyword score in match.py only sees terms from a fixed vocabulary. This
score uses a small open-source embedding model, which turns a sentence into a
list of numbers such that sentences with similar meaning land close together.
"Experience training robot policies from human demonstrations" lands next to a
resume line about imitation learning, although they share no keywords.

HOW A SCORE IS MADE

  1. The resume is split into its statements: each bullet, each skills line and
     the summary. Each one is embedded.
  2. The posting's description is split into sentences. Boilerplate such as the
     equal opportunity notice and the benefits list is dropped, and each
     remaining sentence is embedded.
  3. Every posting sentence is paired with the resume statement closest to it.
     The score blends two things: how strong the best dozen pairings are, and
     how well the posting's requirement sentences are covered on average.

  It reads meaning. It does not read numbers, so it cannot tell "5+ years" from
  "1 year". Those details are handled by requirements.py.

The model is BAAI/bge-small-en-v1.5 (MIT licence), run on the CPU through the
fastembed library. Nothing is sent to any service. If fastembed is not installed
or there is no resume, this step is skipped and the rest of the run is unchanged.

THE RESUME STATEMENTS ARE PRIVATE. They come from the RESUME_STATEMENTS
environment variable or from private/statements.json, never from the repository.
Only the resulting number and the name of the best-fitting resume are published.

The raw result is kept in data/semantic.json and reused, so a posting is embedded once.
The file records which resume it was computed against. When the resume changes,
run `python3 semantic.py --rescore` on the machine that holds the stored
description text.

USAGE

    python3 semantic.py --build-statements General=cv.pdf Quant=quant.pdf
    python3 semantic.py --rescore
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
SCORES = os.path.join(HERE, "data", "semantic.json")
STATEMENTS = os.path.join(HERE, "private", "statements.json")
MODEL = "BAAI/bge-small-en-v1.5"

# The raw blend sits in a narrow band, because this model gives even unrelated
# sentences a similarity near 0.5. LOW and HIGH map that band onto 0 to 100.
# They were set on 2026-10-04 from the spread across the real postings.
LOW, HIGH = 0.59, 0.75
TOP_N = 12
MAX_SENTENCES = 60        # per posting, which bounds the work on a long description
MAX_WORDS = 45            # a longer sentence is cut, since its start carries the point

_SPLIT = re.compile(r"\n+|(?<=[.!?;:])\s+|\s+[•·▪●◦■□–—*]\s+|\s{2,}|\s-\s(?=[A-Z])")
MIN_SENTENCES = 8         # fewer than this is too little text to judge by meaning
_BOILERPLATE = re.compile(
    r"equal opportunity|affirmative action|without regard to|protected veteran|"
    r"disabilit|accommodation|race, color|gender identity|sexual orientation|e-verify|"
    r"401\(?k|medical, dental|dental|vision|paid time off|\bPTO\b|parental leave|"
    r"benefits|salary range|base pay|pay range|compensation|per hour|\$\s?\d|"
    r"background check|drug (test|screen)|privacy (notice|policy)|applicants? (will|must|may)|"
    r"recruit(er|ing) (scam|fraud)|click (here|apply)|apply (now|today|online)|"
    r"about (us|the company)|our mission|we are an? |founded in|headquartered", re.I)
_REQUIREMENT = re.compile(
    r"experience|knowledge|proficien|familiar|ability|skills?\b|understanding|"
    r"degree|required|preferred|qualif|responsib|develop|build|design|implement|"
    r"research|analy[sz]|work(ing)? (with|on)|you will|you'll|background in|expertise", re.I)


def sentences(text: str) -> List[str]:
    """The posting's content sentences, with boilerplate removed."""
    out = []
    for piece in _SPLIT.split(text or ""):
        piece = piece.strip(" -•·:;")
        words = piece.split()
        if len(words) < 5:
            continue
        words = words[:MAX_WORDS]
        if _BOILERPLATE.search(piece):
            continue
        out.append(" ".join(words))
        if len(out) >= MAX_SENTENCES:
            break
    return out


# ── the resume ──────────────────────────────────────────────────────────────
def statements_from(text: str, one_per_line: bool = False) -> List[str]:
    """A resume's statements: bullets, skills lines and summary paragraphs.

    A PDF wraps one bullet over several lines, so lines are joined until the
    next bullet or heading. A Word file gives one paragraph per line, so there
    each line stands alone (`one_per_line`)."""
    if one_per_line:
        out = []
        for raw in text.splitlines():
            line = " ".join(raw.split())
            if "@" in line or re.search(r"\d{3}[-.\s)]\s?\d{3}[-.\s]\d{4}", line):
                continue
            if 6 <= len(line.split()) <= 90:
                out.append(line)
        return out
    chunks: List[str] = []
    current: List[str] = []

    def flush():
        if current:
            chunks.append(" ".join(" ".join(current).split()))
            current.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        letters = [c for c in line if c.isalpha()]
        heading = (len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) > 0.8
                   and len(line) < 90)
        if line[0] in "•·▪●◦■-*":
            flush()
            current.append(line.lstrip("•·▪●◦■-* "))
        elif heading or "@" in line or re.search(r"\d{3}[-.\s]\d{3}[-.\s]\d{4}", line):
            flush()                      # headings and contact lines are not statements
        elif re.match(r"^[A-Z][A-Za-z /&]{3,40}: ", line):
            flush()                      # a skills line such as "Machine Learning: ..."
            current.append(line)
        else:
            current.append(line)
    flush()
    return [c for c in chunks if 6 <= len(c.split()) <= 90]


def build_statements(pairs: List[str]) -> None:
    import match
    bullets: List[str] = []
    resumes: Dict[str, List[int]] = {}
    for pair in pairs:
        name, path = pair.split("=", 1)
        path = os.path.expanduser(path)
        mine = statements_from(match.resume_text(path),
                               one_per_line=path.lower().endswith(".docx"))
        resumes[name] = []
        for b in mine:
            if b not in bullets:
                bullets.append(b)
            resumes[name].append(bullets.index(b))
        print(f"  {name}: {len(mine)} statements")
    os.makedirs(os.path.dirname(STATEMENTS), exist_ok=True)
    with open(STATEMENTS, "w") as fh:
        json.dump({"bullets": bullets, "resumes": resumes}, fh, indent=1)
    size = len(json.dumps({"bullets": bullets, "resumes": resumes}, separators=(",", ":")))
    print(f"  wrote {os.path.relpath(STATEMENTS, HERE)} (private, not committed), "
          f"{len(bullets)} distinct statements, {size:,} bytes as a secret")


def load_statements() -> dict:
    raw = os.environ.get("RESUME_STATEMENTS", "").strip()
    if raw:
        return json.loads(raw)
    try:
        with open(STATEMENTS) as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return {}


# ── scoring ─────────────────────────────────────────────────────────────────
class Scorer:
    def __init__(self, statements: dict):
        from fastembed import TextEmbedding
        import numpy as np
        self.np = np
        # Half the cores at most, so a shared machine keeps room for other work.
        self.model = TextEmbedding(MODEL, threads=max(1, min(12, (os.cpu_count() or 2) // 2)))
        self.resumes = statements["resumes"]
        self.bullets = np.array(list(self.model.embed(statements["bullets"])))
        # LOW and HIGH are left out on purpose. The stored value is the raw
        # blend, so the scale can be retuned without embedding anything again.
        self.key = hashlib.sha1(json.dumps(statements, sort_keys=True).encode()
                                + f"{MODEL}{TOP_N}{MAX_SENTENCES}{MAX_WORDS}".encode()).hexdigest()[:12]

    def score_many(self, texts: Dict[str, str]) -> Dict[str, Tuple[float, str]]:
        """{posting id: (raw blend, best resume name)} for each description."""
        np = self.np
        split = {pid: sentences(t) for pid, t in texts.items()}
        flat = [s for ss in split.values() for s in ss]
        if not flat:
            return {}
        vectors = np.array(list(self.model.embed(flat, batch_size=128)))
        out, at = {}, 0
        for pid, ss in split.items():
            if len(ss) < MIN_SENTENCES:
                at += len(ss)
                continue                       # too little text to judge
            sims = vectors[at:at + len(ss)] @ self.bullets.T
            at += len(ss)
            is_req = np.array([bool(_REQUIREMENT.search(s)) for s in ss])
            best = (-1.0, "")
            for name, idx in self.resumes.items():
                nearest = sims[:, idx].max(axis=1)
                top = np.sort(nearest)[-TOP_N:].mean()
                req = nearest[is_req].mean() if is_req.sum() >= 3 else nearest.mean()
                raw = 0.5 * top + 0.5 * req
                if raw > best[0] + 1e-9:
                    best = (float(raw), name)
            out[pid] = (round(best[0], 4), best[1])
        return out


def percent(raw: float) -> int:
    """The raw blend on the published 0 to 100 scale."""
    return round(100 * min(1.0, max(0.0, (raw - LOW) / (HIGH - LOW))))


def _load_scores() -> dict:
    try:
        with open(SCORES) as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return {}


def enrich(listings: List[dict], fresh_texts: Dict[str, str],
           all_texts: Optional[Dict[str, str]] = None) -> dict:
    """Set `sem` and `sem_resume` on every listing that has a score.

    `fresh_texts` holds the descriptions read during this run. `all_texts`, when
    given, is the full stored set, used to fill in anything still missing.
    Returns counts for the run report."""
    statements = load_statements()
    if not statements.get("bullets"):
        return {"scored": 0, "note": "no resume statements"}
    try:
        scorer = Scorer(statements)
    except Exception as e:                                # noqa: BLE001
        return {"scored": 0, "note": f"embedding model unavailable ({type(e).__name__})"}
    doc = _load_scores()
    scores = doc.get("s", {}) if doc.get("key") == scorer.key else {}
    active = {r["id"] for r in listings}
    todo = {pid: t for pid, t in {**(all_texts or {}), **fresh_texts}.items()
            if pid in active and pid not in scores and len(t) > 200}
    new = scorer.score_many(todo) if todo else {}
    for pid, (raw, name) in new.items():
        scores[pid] = [raw, name]
    scores = {pid: v for pid, v in scores.items() if pid in active}
    os.makedirs(os.path.dirname(SCORES), exist_ok=True)
    with open(SCORES, "w") as fh:
        json.dump({"key": scorer.key, "s": scores}, fh, separators=(",", ":"), sort_keys=True)
    for r in listings:
        if r["id"] in scores:
            r["sem"], r["sem_resume"] = percent(scores[r["id"]][0]), scores[r["id"]][1]
        else:
            r.pop("sem", None)
            r.pop("sem_resume", None)
    return {"scored": len(scores), "new": len(new)}


if __name__ == "__main__":
    if "--build-statements" in sys.argv:
        build_statements(sys.argv[sys.argv.index("--build-statements") + 1:])
    elif "--rescore" in sys.argv:
        import match
        texts = match._load_texts()
        listings = json.load(open(os.path.join(HERE, "docs", "data.json")))["listings"]
        try:
            os.remove(SCORES)
        except FileNotFoundError:
            pass
        print(" ", enrich(listings, {}, texts))
    else:
        print(__doc__)
