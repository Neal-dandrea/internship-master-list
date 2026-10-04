"""requirements.py — pull the hard details out of a posting's description.

A similarity score cannot read a number, so "5+ years" and "1 year" look alike
to it. These details follow predictable wording, so they are read with plain
pattern matching instead. Everything found here is a fact about the POSTING and
is published with it. Nothing about the reader is stored or compared.

    extract(text) -> {
        "years": 3,              least experience asked for, in years
        "degrees": ["Bachelor's", "Master's"],   degrees named, lowest first
        "gpa": 3.5,              minimum GPA
        "citizen": True,         US citizenship or US person status required
        "clearance": True,       a security clearance is required or must be obtainable
        "no_sponsor": True,      the employer says it will not sponsor a visa
        "grad": [2027, 2028],    graduation years the posting names
        "creds": ["RHIA"],       credentials named as required or preferred
    }

Only the keys that were found are present.
"""
from __future__ import annotations

import re
from typing import Dict, List

_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10}
_NUM = r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)"
# "3+ years", "3-5 years", "minimum of two (2) years", "at least 3 yrs"
_YEARS = re.compile(
    rf"{_NUM}\s*(?:\(\d+\)\s*)?(?:\+|or more|plus)?\s*(?:-|–|—|to)?\s*(?:{_NUM}\s*)?\+?\s*"
    rf"(?:years?|yrs?)\b", re.I)
_EXPERIENCE = re.compile(r"experience|background|track record|in (the|a) (field|role|industry)|"
                         r"work(ing)? (in|with|as)|practice|post.?doc", re.I)
# Years that are not a requirement on the applicant.
_NOT_REQ = re.compile(r"years? (old|of age|ago|in business|of history|of innovation|"
                      r"of (service|excellence|growth|success))|for (over|more than|the past)|"
                      r"over the (last|past)|\d+.year (plan|program|history|commitment|contract)|"
                      r"founded|since \d{4}|anniversar|(1st|2nd|3rd|first|second|third|"
                      r"fourth|final|penultimate) year|year (of|in) (your|a|the|their) "
                      r"(phd|ph\.d|program|degree|studies|undergrad|master)", re.I)
_SENT = re.compile(r"\n+|(?<=[.!?;•])\s+")

_DEGREES = [
    ("PhD", re.compile(r"\bph\.?\s?d\b|doctoral|doctorate", re.I)),
    ("Master's", re.compile(r"\bmaster'?s?\b|\bM\.?S\.?c?\b(?=[ ,/)]|$)|\bMBA\b|graduate degree", re.I)),
    ("Bachelor's", re.compile(r"\bbachelor'?s?\b|\bB\.?[SA]\.?\b(?=[ ,/)]| degree)|"
                              r"undergraduate degree|four.year degree", re.I)),
]
_DEGREE_CONTEXT = re.compile(r"pursuing|enrolled|candidate|student|required|requires?|must|"
                             r"minimum|qualification|degree in|completed|completion|"
                             r"working toward|preferred|or equivalent", re.I)
_GPA = re.compile(r"\bGPA\b[^.]{0,40}?([2-4]\.\d{1,2})|([2-4]\.\d{1,2})\s*(?:\+|or (?:higher|above|better))?"
                  r"\s*(?:cumulative\s*)?\bGPA\b", re.I)
_CITIZEN = re.compile(r"(u\.?s\.?|united states) citizen(ship)?( is)? (required|only)|"
                      r"must be (a )?(u\.?s\.?|united states) (citizen|person)|"
                      r"(u\.?s\.?|united states) citizenship|\bITAR\b|u\.?s\.? persons? (only|as defined)|"
                      r"citizens? of the united states", re.I)
_CLEARANCE = re.compile(r"security clearance|\b(secret|top secret|TS/SCI)\b clearance|"
                        r"clearance (is )?required|ability to obtain (a |an )?[\w/ ]{0,20}clearance|"
                        r"active (secret|top secret|TS)", re.I)
_NO_SPONSOR = re.compile(
    r"(not|unable to|cannot|can't|won't|will not|does not|do not|no)\s+(be\s+)?"
    r"(able to\s+)?(provide|offer|sponsor|support|consider)[^.]{0,40}?"
    r"(sponsorship|visa|work authorization)|"
    r"without (the need for |requiring )?(visa |employer |current or future )?sponsorship|"
    r"sponsorship (is )?not (available|offered|provided)|"
    r"not eligible for (visa )?sponsorship", re.I)
_GRAD = re.compile(r"(graduat\w+|degree|class of|completion)[^.]{0,80}?\b(20[2-3]\d)\b"
                   r"(?:[^.]{0,25}?\b(20[2-3]\d)\b)?", re.I)
_CREDS = [("RHIA", r"\bRHIA\b"), ("RHIT", r"\bRHIT\b"), ("CCS", r"\bCCS(-P)?\b"),
          ("CPC", r"\bCPC\b"), ("CCA", r"\bCCA\b"), ("CDIP", r"\bCDIP\b"),
          ("CCDS", r"\bCCDS\b"), ("CTR", r"\bCTR\b|\bODS\b"), ("RN", r"\bRN\b"),
          ("CRCR", r"\bCRCR\b"), ("CHDA", r"\bCHDA\b"), ("CCRP", r"\bCCRP\b|\bCCRC\b|\bCCRA\b")]
_CRED_PATS = [(name, re.compile(pat)) for name, pat in _CREDS]


def _n(text: str) -> int:
    return _WORDS.get(text.lower(), None) or int(text)


def extract(text: str) -> Dict[str, object]:
    out: Dict[str, object] = {}
    if not text:
        return out
    sentences = _SENT.split(text)

    # Years of experience: the smallest lower bound among sentences that talk
    # about experience. "3-5 years" counts as 3. The smallest is used because a
    # posting often lists a higher figure for a more senior variant of the role.
    found: List[int] = []
    for s in sentences:
        if not _EXPERIENCE.search(s) or _NOT_REQ.search(s):
            continue
        for m in _YEARS.finditer(s):
            try:
                n = _n(m.group(1))
            except (ValueError, TypeError):
                continue
            if 0 < n <= 20:
                found.append(n)
    if found:
        out["years"] = min(found)

    degrees = [name for name, pat in _DEGREES
               if any(pat.search(s) and _DEGREE_CONTEXT.search(s) for s in sentences)]
    if degrees:
        out["degrees"] = degrees[::-1]          # lowest first

    gpas = [float(a or b) for a, b in _GPA.findall(text)]
    gpas = [g for g in gpas if 2.0 <= g <= 4.0]
    if gpas:
        out["gpa"] = min(gpas)

    if _CITIZEN.search(text):
        out["citizen"] = True
    if _CLEARANCE.search(text):
        out["clearance"] = True
    if _NO_SPONSOR.search(text):
        out["no_sponsor"] = True

    years = sorted({int(y) for m in _GRAD.finditer(text) for y in m.groups()[1:] if y})
    if years:
        out["grad"] = years[:4]

    creds = [name for name, pat in _CRED_PATS if pat.search(text)]
    if creds:
        out["creds"] = creds
    return out
