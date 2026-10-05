"""ats.py — read internship postings straight from company career sites.

Most companies host their careers page on one of a few platforms, and each
platform has a public feed that the careers page itself reads. Given a company's
identifier on a platform, these functions return that company's internship
postings in the collector's common shape.

The company list is not hand-written. `discover` reads the links that the job
boards point at and pulls the identifiers out of them, so every company a board
has ever listed gets checked at the source from then on. That catches postings
before a board picks them up.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Tuple

import platforms

TODAY = dt.date.today()

# What counts as an internship when a feed returns every job at the company.
INTERN = re.compile(
    r"\b(intern|interns|internship|internships|co-?op|co-?ops|"
    r"student researcher|research resident|phd resident|"
    r"summer analyst|summer associate|working student|werkstudent)\b", re.I)
STALE_YEAR = re.compile(r"\b20(1\d|2[0-5])\b")


def is_internship(title: str) -> bool:
    return bool(INTERN.search(title or "")) and not STALE_YEAR.search(title or "")


# ── finding company identifiers in board links ──────────────────────────────
_PATTERNS = [
    ("greenhouse", re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?([A-Za-z0-9_-]+)(?=/jobs|&|$)")),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)")),
    ("smartrecruiters", re.compile(r"jobs\.smartrecruiters\.com/([A-Za-z0-9_-]+)")),
    ("workable", re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)(?=/j/)")),
]
_WORKDAY = re.compile(r"https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/"
                      r"(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)")
# The same sites are also reached as wdN.myworkdaysite.com/recruiting/TENANT/SITE.
_WORKDAYSITE = re.compile(r"https?://(wd\d+)\.myworkdaysite\.com/(?:[a-z]{2}-[A-Z]{2}/)?"
                          r"recruiting/([a-z0-9_-]+)/([A-Za-z0-9_-]+)", re.I)
_ORACLE = re.compile(r"https?://([a-z0-9.-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/"
                     r"[a-z-]+/sites/([A-Za-z0-9_-]+)")
_ICIMS = re.compile(r"https?://([a-z0-9-]+)\.icims\.com")
_EIGHTFOLD = re.compile(r"https?://([a-z0-9-]+\.eightfold\.ai)")
_UKG = re.compile(r"https?://((?:recruiting2?\.ultipro\.com|[a-z0-9.-]+\.ukg\.net))/"
                  r"([A-Za-z0-9]+)/JobBoard/([0-9a-fA-F-]{36})")
_MORE_PATTERNS = [
    ("rippling", re.compile(r"ats\.rippling\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/?#]+)/jobs")),
    ("bamboohr", re.compile(r"https?://([a-z0-9-]+)\.bamboohr\.com/")),
    ("pinpoint", re.compile(r"https?://([a-z0-9-]+)\.pinpointhq\.com")),
    ("breezy", re.compile(r"https?://([a-z0-9-]+)\.breezy\.hr")),
    ("jazzhr", re.compile(r"https?://([a-z0-9-]+)\.applytojob\.com/")),
    ("jobvite", re.compile(r"jobs\.jobvite\.com/(?:careers/)?([^/?#]+)/(?:job|jobs|search)")),
]
# Employers with a reader of their own, recognised by their careers address.
_FIXED_SITES = [
    ("atsx", "tiktok", "lifeattiktok.com"), ("atsx", "bytedance", "jobs.bytedance.com"),
    ("atsx", "bytedance", "joinbytedance.com"), ("amazon", "jobs", "amazon.jobs"),
    ("apple", "jobs", "jobs.apple.com"),
    ("eightfold", "apply.careers.microsoft.com|microsoft.com", "careers.microsoft.com"),
    ("eightfold", "careers.qualcomm.com|qualcomm.com", "careers.qualcomm.com"),
    ("deshaw", "jobs", "deshaw.com/careers"), ("ibm", "jobs", "careers.ibm.com"),
    ("jibe", "careers.amd.com", "careers.amd.com"), ("jibe", "jobs.keysight.com", "jobs.keysight.com"),
    ("jibe", "careers.garmin.com", "careers.garmin.com"),
    ("rmk", "jobs.l3harris.com", "jobs.l3harris.com"), ("rmk", "careers.qorvo.com", "careers.qorvo.com"),
    ("radancy", "jobs.boeing.com", "jobs.boeing.com"),
    ("radancy", "www.disneycareers.com/en", "disneycareers.com"),
    ("avature", "bloomberg.avature.net/careers", "bloomberg.avature.net"),
]
_NOT_TOKENS = {"embed", "jobs", "j", "job", "careers", "api", "wday"}


def discover(url: str) -> Optional[Tuple[str, str]]:
    """(platform, identifier) for a posting link, or None if it is not one we read."""
    m = _WORKDAY.search(url)
    # "Careers" and "jobs" are common names for a Workday site, so they are fine
    # here even though they are not company names elsewhere.
    if m and m.group(3).lower() not in ("wday", "api", "job"):
        return "workday", "/".join(m.groups())
    m = _WORKDAYSITE.search(url)
    if m:
        return "workday", f"{m.group(2)}/{m.group(1)}/{m.group(3)}"
    m = _ORACLE.search(url)
    if m:
        return "oracle", "/".join(m.groups())
    m = _ICIMS.search(url)
    if m and m.group(1) not in ("www", "cdn", "cdn02", "images"):
        return "icims", m.group(1)
    m = _EIGHTFOLD.search(url)
    if m:
        return "eightfold", m.group(1) + "|"
    m = _UKG.search(url)
    if m:
        return "ukg", "/".join(m.groups())
    found = platforms.discover(url)
    if found:
        return found
    for name, key, host in _FIXED_SITES:
        if host in url:
            return name, key
    for name, pat in _PATTERNS:
        m = pat.search(url)
        if m and m.group(1).lower() not in _NOT_TOKENS:
            return name, urllib.parse.unquote(m.group(1))
    return None


# ── one reader per platform ─────────────────────────────────────────────────
# Each takes (identifier, company name, fetch, listing) and returns listings.
def _date(text) -> Optional[str]:
    return (str(text)[:10] or None) if text else None


def greenhouse(token, company, fetch, listing):
    doc = json.loads(fetch(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"))
    return [listing("careers", company, j["title"], j["absolute_url"],
                    location=(j.get("location") or {}).get("name") or "",
                    posted=_date(j.get("first_published") or j.get("updated_at")))
            for j in doc.get("jobs", []) if is_internship(j.get("title"))]


def lever(token, company, fetch, listing):
    doc = json.loads(fetch(f"https://api.lever.co/v0/postings/{token}?mode=json"))
    out = []
    for j in doc if isinstance(doc, list) else []:
        cat = j.get("categories") or {}
        # "Internal" must not count, so the commitment is matched as a word.
        if not (is_internship(j.get("text")) or
                re.search(r"\bintern(ship)?s?\b", cat.get("commitment") or "", re.I)):
            continue
        if STALE_YEAR.search(j.get("text") or ""):
            continue
        posted = None
        if j.get("createdAt"):
            posted = dt.datetime.fromtimestamp(
                j["createdAt"] / 1000, dt.timezone.utc).date().isoformat()
        out.append(listing("careers", company, j["text"], j["hostedUrl"],
                           location="; ".join(cat.get("allLocations") or
                                              [cat.get("location") or ""]),
                           posted=posted))
    return out


def ashby(token, company, fetch, listing):
    doc = json.loads(fetch("https://api.ashbyhq.com/posting-api/job-board/"
                           + urllib.parse.quote(token)))
    out = []
    for j in doc.get("jobs", []):
        if not (is_internship(j.get("title")) or j.get("employmentType") == "Intern"):
            continue
        if STALE_YEAR.search(j.get("title") or ""):
            continue
        loc = j.get("location") or ""
        if j.get("isRemote") and "remote" not in loc.lower():
            loc = (loc + "; Remote").strip("; ")
        out.append(listing("careers", company, j["title"], j["jobUrl"],
                           location=loc, posted=_date(j.get("publishedAt"))))
    return out


def smartrecruiters(token, company, fetch, listing):
    doc = json.loads(fetch("https://api.smartrecruiters.com/v1/companies/"
                           f"{token}/postings?q=intern&limit=100"))
    out = []
    for j in doc.get("content", []):
        if not is_internship(j.get("name")):
            continue
        loc = j.get("location") or {}
        where = loc.get("fullLocation") or ", ".join(
            x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)
        if loc.get("remote"):
            where = (where + "; Remote").strip("; ")
        out.append(listing("careers", company, j["name"],
                           f"https://jobs.smartrecruiters.com/{token}/{j['id']}",
                           location=where, posted=_date(j.get("releasedDate"))))
    return out


def workable(token, company, fetch, listing):
    doc = json.loads(fetch(f"https://apply.workable.com/api/v1/widget/accounts/{token}"))
    return [listing("careers", company, j["title"], j["url"],
                    location=", ".join(x for x in (j.get("city"), j.get("state"),
                                                   j.get("country")) if x),
                    posted=_date(j.get("published_on")))
            for j in doc.get("jobs", []) if is_internship(j.get("title"))]


def _workday_posted(text: str) -> Optional[str]:
    """'Posted Today' / 'Posted Yesterday' / 'Posted 3 Days Ago' -> a date.
    'Posted 30+ Days Ago' has no real date, so it stays None."""
    t = (text or "").lower()
    if "today" in t:
        return TODAY.isoformat()
    if "yesterday" in t:
        return (TODAY - dt.timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)(\+?) days? ago", t)
    if m and not m.group(2):
        return (TODAY - dt.timedelta(days=int(m.group(1)))).isoformat()
    return None


def workday(token, company, fetch, listing, max_pages: int = 5):
    tenant, wd, site = token.split("/")
    base = f"https://{tenant}.{wd}.myworkdayjobs.com"
    out, offset = [], 0
    for _ in range(max_pages):
        doc = json.loads(fetch(f"{base}/wday/cxs/{tenant}/{site}/jobs",
                               json_body={"appliedFacets": {}, "limit": 20,
                                          "offset": offset, "searchText": "intern"}))
        posts = doc.get("jobPostings") or []
        for j in posts:
            if not j.get("externalPath") or not is_internship(j.get("title")):
                continue
            out.append(listing("careers", company, j["title"],
                               f"{base}/{site}{j['externalPath']}",
                               location=j.get("locationsText") or "",
                               posted=_workday_posted(j.get("postedOn"))))
        offset += 20
        if len(posts) < 20 or offset >= int(doc.get("total") or 0):
            break
    return out


def oracle(token, company, fetch, listing, max_jobs: int = 500):
    """Oracle Cloud career sites. The identifier is host/site."""
    host, site = token.split("/")
    out, offset = [], 0
    while offset < max_jobs:
        doc = json.loads(fetch(
            f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
            f"?onlyData=true&expand=requisitionList.secondaryLocations"
            f"&finder=findReqs;siteNumber={site},keyword=%22intern%22,limit=100,"
            f"offset={offset},sortBy=POSTING_DATES_DESC"))
        item = (doc.get("items") or [{}])[0]
        rows = item.get("requisitionList") or []
        for j in rows:
            if not is_internship(j.get("Title")):
                continue
            locs = [j.get("PrimaryLocation") or ""] + [
                x.get("Name") or "" for x in j.get("secondaryLocations") or []]
            out.append(listing(
                "careers", company, j["Title"],
                f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{j['Id']}",
                location="; ".join(x for x in locs if x), posted=_date(j.get("PostedDate"))))
        offset += 100
        if len(rows) < 100 or offset >= int(item.get("TotalJobsCount") or 0):
            break
    return out


_ICIMS_ROW = re.compile(
    r'<a href="(https://[^"]+?/jobs/(\d+)/[^"]*?/job)[^"]*"[^>]*class="iCIMS_Anchor"[^>]*>'
    r'.*?<h3[^>]*>\s*(.*?)\s*</h3>', re.S)
_ICIMS_FIELD = re.compile(r'field-label">([^<]+)</span>\s*<span[^>]*>\s*([^<]*)', re.S)
_ICIMS_PAGES = re.compile(r"Page \d+ of (\d+)")
_ICIMS_DATE = re.compile(r'Posted Date</span>\s*<span[^>]*title="(\d{1,2})/(\d{1,2})/(\d{4})')


def icims(token, company, fetch, listing, max_pages: int = 15):
    """iCIMS career sites. The identifier is the subdomain. The job list is a
    web page, twenty postings at a time, searched for "intern"."""
    import html as _html
    base = (f"https://{token}.icims.com/jobs/search?ss=1&searchKeyword=intern"
            f"&in_iframe=1&pr=")
    out, pages, page = [], 1, 0
    while page < min(pages, max_pages):
        text = fetch(base + str(page)).decode("utf-8", errors="replace")
        m = _ICIMS_PAGES.search(text)
        if m:
            pages = int(m.group(1))
        found = 0
        for block in re.split(r'<div class="row">', text):
            row = _ICIMS_ROW.search(block)
            if not row:
                continue
            found += 1
            url, _, title = row.groups()
            title = _html.unescape(re.sub(r"<[^>]+>", "", title)).strip()
            if not is_internship(title):
                continue
            fields = [(k.strip(), _html.unescape(v).strip())
                      for k, v in _ICIMS_FIELD.findall(block)]
            loc = next((v for k, v in fields if "location" in k.lower() and v), "") or \
                next((v for k, v in fields if k != "Job Title" and v), "")
            loc = "; ".join(re.sub(r"^US-([A-Z]{2})-(.+)$", r"\2, \1", x.strip())
                            for x in loc.split("|") if x.strip())
            d = _ICIMS_DATE.search(block)
            posted = f"{d.group(3)}-{int(d.group(1)):02d}-{int(d.group(2)):02d}" if d else None
            out.append(listing("careers", company, title, url, location=loc, posted=posted))
        if not found:
            break
        page += 1
    return out


def eightfold(token, company, fetch, listing, max_jobs: int = 400):
    """Eightfold career sites. The identifier is host|domain. When the domain is
    not known it is guessed from the host. Eightfold has an older feed and a
    newer one, and a given employer answers only one of them."""
    host, domain = token.split("|")
    domain = domain or host.split(".")[0] + ".com"

    def stamp(ts):
        return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).date().isoformat() if ts else None

    out, start = [], 0
    try:
        while start < max_jobs:
            doc = json.loads(fetch(f"https://{host}/api/apply/v2/jobs?domain={domain}"
                                   f"&query=intern&num=100&start={start}&sort_by=timestamp"))
            rows = doc["positions"]
            for j in rows:
                if is_internship(j.get("name")):
                    out.append(listing(
                        "careers", company, j["name"],
                        j.get("canonicalPositionUrl") or f"https://{host}/careers/job/{j.get('id')}",
                        location="; ".join(j.get("locations") or [j.get("location") or ""]),
                        posted=stamp(j.get("t_create"))))
            start += 100
            if len(rows) < 100 or start >= int(doc.get("count") or 0):
                break
        return out
    except Exception:                                     # noqa: BLE001
        out, start = [], 0
    while start < max_jobs:
        doc = json.loads(fetch(f"https://{host}/api/pcsx/search?domain={domain}"
                               f"&query=intern&start={start}"))
        data = doc.get("data") or {}
        rows = data.get("positions") or []
        for j in rows:
            if is_internship(j.get("name")):
                locs = [re.sub(r", US$", "", x) for x in
                        (j.get("standardizedLocations") or j.get("locations") or [])]
                out.append(listing("careers", company, j["name"],
                                   f"https://{host}{j.get('positionUrl') or ''}",
                                   location="; ".join(locs), posted=stamp(j.get("postedTs"))))
        start += len(rows)
        if not rows or start >= int(data.get("count") or 0):
            break
    return out


def ukg(token, company, fetch, listing, max_jobs: int = 300):
    """UKG (UltiPro) job boards. The identifier is host/tenant/board id."""
    host, tenant, board = token.split("/")
    base = f"https://{host}/{tenant}/JobBoard/{board}"
    out, skip = [], 0
    while skip < max_jobs:
        doc = json.loads(fetch(base + "/JobBoardView/LoadSearchResults", json_body={
            "opportunitySearch": {"Top": 50, "Skip": skip, "QueryString": "intern",
                                  "OrderBy": [{"Value": "postedDateDesc",
                                               "PropertyName": "PostedDate",
                                               "Ascending": False}],
                                  "Filters": []},
            "matchCriteria": {"PreferredJobs": [], "Educations": [],
                              "LicenseAndCertifications": [], "Skills": [],
                              "hasNoLicenses": False, "SkippedSkills": []}}))
        rows = doc.get("opportunities") or []
        for j in rows:
            if not is_internship(j.get("Title")):
                continue
            locs = []
            for x in j.get("Locations") or []:
                a = x.get("Address") or {}
                state = (a.get("State") or {}).get("Code") or ""
                locs.append(", ".join(v for v in (a.get("City"), state) if v)
                            or x.get("LocalizedName") or "")
            out.append(listing("careers", company, j["Title"],
                               f"{base}/OpportunityDetail?opportunityId={j['Id']}",
                               location="; ".join(v for v in locs if v),
                               posted=_date(j.get("PostedDate"))))
        skip += 50
        if len(rows) < 50 or skip >= int(doc.get("totalCount") or 0):
            break
    return out


# ── readers worked out by watching what each careers page itself requests ────
# None of these is a published feed. Each is the request the employer's own
# careers page makes, or the page itself, read without logging in. They can
# change without notice, and a reader that stops working simply reports that.
def _text(html_text: str) -> str:
    import html as _html
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", html_text or "")).split())


def jibe(token, company, fetch, listing, max_pages: int = 6):
    """Career sites on iCIMS's newer front end. The identifier is the careers host."""
    out = []
    for page in range(1, max_pages + 1):
        doc = json.loads(fetch(f"https://{token}/api/jobs?keywords=intern&page={page}"
                               f"&limit=100&sortBy=posted_date&descending=true"))
        jobs = doc.get("jobs") or []
        for item in jobs:
            j = item.get("data") or {}
            if not is_internship(j.get("title")):
                continue
            url = ((j.get("meta_data") or {}).get("canonical_url")
                   or f"https://{token}/jobs/{j.get('slug') or j.get('req_id')}")
            row = listing("careers", company, j["title"], url,
                          location=j.get("full_location") or j.get("location_name") or "",
                          posted=_date(j.get("posted_date")))
            row["_text"] = " ".join(str(j.get(k) or "") for k in
                                    ("description", "qualifications", "responsibilities"))
            out.append(row)
        if len(jobs) < 100 or page * 100 >= int(doc.get("totalCount") or 0):
            break
    return out


def rippling(token, company, fetch, listing):
    doc = json.loads(fetch(f"https://ats.rippling.com/api/v2/board/{token}/jobs"
                           f"?page=0&pageSize=500"))
    return [listing("careers", company, j["name"], j["url"],
                    location="; ".join(x.get("name") or "" for x in j.get("locations") or []))
            for j in doc.get("items") or [] if is_internship(j.get("name"))]


def bamboohr(token, company, fetch, listing):
    doc = json.loads(fetch(f"https://{token}.bamboohr.com/careers/list"))
    out = []
    for j in doc.get("result") or []:
        title = j.get("jobOpeningName") or ""
        if STALE_YEAR.search(title):
            continue
        if not (is_internship(title) or (j.get("employmentStatusLabel") or "") == "Intern"):
            continue
        loc = j.get("location") or {}
        where = ", ".join(x for x in (loc.get("city"), loc.get("state")) if x)
        if j.get("isRemote"):
            where = (where + "; Remote").strip("; ")
        out.append(listing("careers", company, title,
                           f"https://{token}.bamboohr.com/careers/{j['id']}", location=where))
    return out


def pinpoint(token, company, fetch, listing):
    doc = json.loads(fetch(f"https://{token}.pinpointhq.com/postings.json"))
    out = []
    for j in doc.get("data") or []:
        if not (is_internship(j.get("title")) or j.get("employment_type") == "internship"):
            continue
        if STALE_YEAR.search(j.get("title") or ""):
            continue
        row = listing("careers", company, j["title"], j["url"],
                      location=(j.get("location") or {}).get("name") or "")
        row["_text"] = " ".join(str(j.get(k) or "") for k in
                                ("description", "key_responsibilities",
                                 "skills_knowledge_expertise"))
        out.append(row)
    return out


def breezy(token, company, fetch, listing):
    doc = json.loads(fetch(f"https://{token}.breezy.hr/json?verbose=true"))
    out = []
    for j in doc if isinstance(doc, list) else []:
        kind = ((j.get("type") or {}).get("name") or "")
        if not (is_internship(j.get("name")) or "intern" in kind.lower()):
            continue
        row = listing("careers", company, j["name"], j["url"],
                      location=(j.get("location") or {}).get("name") or "",
                      posted=_date(j.get("published_date")))
        row["_text"] = j.get("description") or ""
        out.append(row)
    return out


_JAZZ = re.compile(r'<li class="list-group-item">.*?<a href="(https://[^"]+/apply/[A-Za-z0-9]+/[^"]*)">'
                   r"\s*(.*?)\s*</a>.*?fa-map-marker'></i>(.*?)</li>", re.S)


def jazzhr(token, company, fetch, listing):
    page = fetch(f"https://{token}.applytojob.com/apply").decode("utf-8", errors="replace")
    return [listing("careers", company, _text(title), url, location=_text(loc))
            for url, title, loc in _JAZZ.findall(page) if is_internship(_text(title))]


_JOBVITE = re.compile(r'<td class="jv-job-list-name">\s*<a href="(/[^"/]+/job/[A-Za-z0-9]+)">(.*?)</a>'
                      r'\s*</td>\s*<td class="jv-job-list-location">(.*?)</td>', re.S)


def jobvite(token, company, fetch, listing, max_pages: int = 4):
    out = []
    for p in range(max_pages):
        page = fetch(f"https://jobs.jobvite.com/{token}/search?q=intern&p={p}").decode(
            "utf-8", errors="replace")
        rows = _JOBVITE.findall(page)
        for path, title, loc in rows:
            if is_internship(_text(title)):
                out.append(listing("careers", company, _text(title),
                                   "https://jobs.jobvite.com" + path, location=_text(loc)))
        if len(rows) < 50 or "jv-pagination-next" not in page:
            break
    return out


_RMK_LINK = re.compile(r'<a[^>]*class="[^"]*jobTitle-link[^"]*"[^>]*href="(/job/[^"]+)"[^>]*>(.*?)</a>'
                       r'|<a[^>]*href="(/job/[^"]+)"[^>]*class="[^"]*jobTitle-link[^"]*"[^>]*>(.*?)</a>',
                       re.S)
_RMK_LOC = re.compile(r'section-location-value[^>]*>(.*?)</|class="jobLocation[^"]*"[^>]*>(.*?)</', re.S)
_RMK_TOTAL = re.compile(r"of\s+(?:<b>)?\s*([\d,]+)\s*(?:</b>)?\s*(?:Jobs|Results)", re.I)


def rmk(token, company, fetch, listing, max_pages: int = 5):
    """SAP SuccessFactors career sites. The identifier is the careers host. The
    results are a web page in one of two layouts, both read here."""
    out, seen = [], set()
    for n in range(max_pages):
        page = fetch(f"https://{token}/search/?q=&title=intern&sortColumn=referencedate"
                     f"&sortDirection=desc&startrow={n * 100}").decode("utf-8", errors="replace")
        # Each posting is a table row or a tile. Split on either marker.
        chunks = re.split(r'<tr class="data-row|<li class="job-tile', page)[1:]
        if not chunks and "rmk-jobs-search" in page:
            # The newest layout draws results in the browser, so its feed is read.
            return platforms._rmk_feed(token, company, fetch, listing, is_internship,
                                       ["intern", "internship", "co-op"])
        new = 0
        for chunk in chunks:
            m = _RMK_LINK.search(chunk)
            if not m:
                continue
            path = m.group(1) or m.group(3)
            title = _text(m.group(2) or m.group(4))
            if path in seen:
                continue
            seen.add(path)
            new += 1
            if not is_internship(title):
                continue
            where = ""
            for g1, g2 in _RMK_LOC.findall(chunk):       # skip the "Location" label itself
                text = _text(g1 or g2)
                if text and text.lower() != "location":
                    where = text
                    break
            out.append(listing("careers", company, title, f"https://{token}{path}",
                               location=where))
        total = _RMK_TOTAL.search(page)
        if not new or (total and (n + 1) * 100 >= int(total.group(1).replace(",", ""))):
            break
    return out


# TikTok and ByteDance run the same careers software. Each needs its own
# "website-path" header, and a posting's public address differs from the API's.
_ATSX = {
    "tiktok": ("https://api.lifeattiktok.com", "tiktok", "https://lifeattiktok.com/search/{id}"),
    "bytedance": ("https://jobs.bytedance.com", "en", "https://joinbytedance.com/search/{id}"),
}


def atsx(token, company, fetch, listing, max_jobs: int = 2500):
    base, site, link = _ATSX[token]
    out, offset = [], 0
    while offset < max_jobs:
        doc = json.loads(fetch(
            base + "/api/v1/public/supplier/search/job/posts",
            json_body={"recruitment_id_list": ["202"],        # 202 is "Intern"
                       "job_category_id_list": [], "subject_id_list": [],
                       "location_code_list": [], "keyword": "", "limit": 100,
                       "offset": offset},
            headers={"website-path": site}))
        data = doc.get("data") or {}
        rows = data.get("job_post_list") or []
        for j in rows:
            if STALE_YEAR.search(j.get("title") or ""):
                continue
            place, parts = j.get("city_info") or {}, []
            while place and len(parts) < 3:
                if place.get("en_name"):
                    parts.append(place["en_name"])
                place = place.get("parent") or {}
            row = listing("careers", company, j["title"], link.format(id=j["id"]),
                          location=", ".join(parts))
            row["_text"] = (j.get("description") or "") + "\n" + (j.get("requirement") or "")
            out.append(row)
        offset += 100
        if len(rows) < 100 or offset >= int(data.get("count") or 0):
            break
    return out


def amazon(token, company, fetch, listing, max_jobs: int = 1000):
    out, offset = [], 0
    while offset < max_jobs:
        doc = json.loads(fetch("https://www.amazon.jobs/en/search.json?base_query=intern"
                               f"&result_limit=100&offset={offset}&sort=recent"))
        rows = doc.get("jobs") or []
        for j in rows:
            if not (is_internship(j.get("title")) or j.get("is_intern")):
                continue
            posted = None
            try:
                posted = dt.datetime.strptime(" ".join((j.get("posted_date") or "").split()),
                                              "%B %d, %Y").date().isoformat()
            except ValueError:
                pass
            row = listing("careers", company, j["title"],
                          "https://www.amazon.jobs" + j["job_path"],
                          location=j.get("normalized_location") or "", posted=posted)
            row["_text"] = " ".join(str(j.get(k) or "") for k in
                                    ("description", "basic_qualifications",
                                     "preferred_qualifications"))
            out.append(row)
        offset += 100
        if len(rows) < 100 or offset >= int(doc.get("hits") or 0):
            break
    return out


_APPLE = re.compile(r'__staticRouterHydrationData\s*=\s*JSON\.parse\("(.*?)"\);', re.S)


def apple_state(page: str) -> dict:
    m = _APPLE.search(page)
    return json.loads(json.loads('"' + m.group(1) + '"')) if m else {}


def apple(token, company, fetch, listing, max_pages: int = 15):
    out = []
    for n in range(1, max_pages + 1):
        page = fetch("https://jobs.apple.com/en-us/search?team=internships-STDNT-INTRN"
                     f"&sort=newest&page={n}").decode("utf-8", errors="replace")
        search = (apple_state(page).get("loaderData") or {}).get("search") or {}
        rows = search.get("searchResults") or []
        for j in rows:
            where = "; ".join(x.get("name") or "" for x in j.get("locations") or [])
            out.append(listing(
                "careers", company, j["postingTitle"],
                f"https://jobs.apple.com/en-us/details/{j['positionId']}/"
                f"{j.get('transformedPostingTitle') or ''}",
                location=where, posted=_date(j.get("postDateInGMT"))))
        if len(rows) < 20 or n * 20 >= int(search.get("totalRecords") or 0):
            break
    return out


def deshaw(token, company, fetch, listing):
    """D. E. Shaw lists its internships inside its careers page."""
    page = fetch("https://www.deshaw.com/careers").decode("utf-8", errors="replace")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    props = json.loads(m.group(1))["props"]["pageProps"]
    out = []
    for j in props.get("internships") or []:
        data = j.get("data") or j
        out.append(listing("careers", company, j.get("displayName") or data.get("displayName"),
                           "https://www.deshaw.com/careers/" + str(data.get("jobUrl") or j.get("jobUrl")),
                           location="; ".join(o.get("name") or "" for o in
                                              (j.get("office") or data.get("office") or []))))
    return out


def ibm(token, company, fetch, listing, max_jobs: int = 300):
    out, start = [], 0
    while start < max_jobs:
        doc = json.loads(fetch("https://www-api.ibm.com/search/api/v2", json_body={
            "appId": "careers", "scopes": ["careers2"],
            "query": {"bool": {"must": [{"simple_query_string": {
                "query": "intern", "fields": ["title^3", "description^2", "body^1"]}}]}},
            "size": 30, "from": start, "sort": [{"dcdate": "desc"}, {"_score": "desc"}],
            "lang": "zz", "localeSelector": {}, "sm": {"query": "intern", "lang": "zz"},
            "_source": ["_id", "title", "url", "description", "language", "entitled",
                        "field_keyword_17", "field_keyword_08", "field_keyword_18",
                        "field_keyword_19", "dcdate"]}))
        hits = (doc.get("hits") or {}).get("hits") or []
        for h in hits:
            j = h.get("_source") or {}
            if not (is_internship(j.get("title")) or j.get("field_keyword_18") == "Internship"):
                continue
            row = listing("careers", company, j["title"], j["url"],
                          location=j.get("field_keyword_19") or "", posted=_date(j.get("dcdate")))
            row["_text"] = j.get("description") or ""
            out.append(row)
        start += 30
        total = ((doc.get("hits") or {}).get("total") or {}).get("value") or 0
        if len(hits) < 30 or start >= int(total):
            break
    return out


def _generic(reader):
    """Wrap a reader from platforms.py, which serves both boards, for this one:
    keep internships, and search for "intern" where a search is needed."""
    return lambda token, company, fetch, listing: reader(
        token, company, fetch, listing, is_internship, ["intern"])


READERS: Dict[str, Callable] = {
    **{name: _generic(fn) for name, fn in platforms.READERS.items()},
    "deshaw": deshaw, "ibm": ibm,
    "greenhouse": greenhouse, "lever": lever, "ashby": ashby,
    "smartrecruiters": smartrecruiters, "workable": workable, "workday": workday,
    "oracle": oracle, "icims": icims, "eightfold": eightfold, "ukg": ukg,
    "jibe": jibe, "rippling": rippling, "bamboohr": bamboohr, "pinpoint": pinpoint,
    "breezy": breezy, "jazzhr": jazzhr, "jobvite": jobvite, "rmk": rmk,
    "atsx": atsx, "amazon": amazon, "apple": apple,
}


def careers_url(key: str) -> str:
    """A page a person can open for a registry entry."""
    platform, token = key.split(":", 1)
    if platform == "workday":
        tenant, wd, site = token.split("/")
        return f"https://{tenant}.{wd}.myworkdayjobs.com/{site}"
    if platform == "oracle":
        host, site = token.split("/")
        return f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/jobs"
    if platform == "icims":
        return f"https://{token}.icims.com/jobs/search"
    if platform == "eightfold":
        return f"https://{token.split('|')[0]}/careers"
    if platform == "ukg":
        host, tenant, board = token.split("/")
        return f"https://{host}/{tenant}/JobBoard/{board}"
    return {"greenhouse": "https://job-boards.greenhouse.io/", "lever": "https://jobs.lever.co/",
            "ashby": "https://jobs.ashbyhq.com/", "smartrecruiters": "https://jobs.smartrecruiters.com/",
            "workable": "https://apply.workable.com/", "jibe": "https://"}.get(platform, "") + token


def collect(companies: Dict[str, dict], fetch, listing, workers: int = 16,
            progress=None) -> Tuple[List[dict], Dict[str, str]]:
    """Read every company in the registry. Returns (listings, failures).

    `companies` maps "platform:identifier" to {"name": ...}. A company whose
    feed fails is reported in `failures` and does not stop the others.
    """
    def one(key: str):
        platform, token = key.split(":", 1)
        try:
            rows = READERS[platform](token, companies[key]["name"], fetch, listing)
            for r in rows:
                r["ats"] = key
            return key, rows, None
        except Exception as e:                            # noqa: BLE001
            return key, [], f"{type(e).__name__}: {str(e)[:80]}"

    rows: List[dict] = []
    failures: Dict[str, str] = {}
    keys = [k for k in companies if k.split(":", 1)[0] in READERS]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for n, (key, got, err) in enumerate(pool.map(one, keys), 1):
            rows += got
            if err:
                failures[key] = err
            if progress and n % 100 == 0:
                progress(n, len(keys))
    return rows, failures
