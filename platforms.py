"""platforms.py — readers for careers platforms that publish no job feed.

Each of these was worked out by watching what a careers page on that platform
requests when an ordinary visitor opens it. None needs a login, and none is a
documented feed, so any of them can change without notice. A reader that stops
working raises, and the collector reports that employer as unreachable.

Every reader has the same shape:

    reader(token, company, fetch, listing, want, keywords) -> list of listings

    token      the employer's identifier on that platform (see each reader)
    want       a function that says whether a job title belongs on the list
    keywords   search words to try on platforms that only answer a search.
               Platforms that return every job ignore it.

A listing that arrives with its description carries it as "_text".

This file is shared by both boards. Each board keeps its own copy.
"""
from __future__ import annotations

import datetime as dt
import html as _html
import json
import re
import urllib.parse
from typing import Callable, Dict, List, Optional


def _text(markup: str) -> str:
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", markup or "")).split())


def _date(value) -> Optional[str]:
    return (str(value)[:10] or None) if value else None


def _page(fetch, url: str, **kw) -> str:
    return fetch(url, **kw).decode("utf-8", errors="replace")


# ── platforms that return every open job in one answer ───────────────────────
def rippling(token, company, fetch, listing, want, keywords):
    doc = json.loads(fetch(f"https://ats.rippling.com/api/v2/board/{token}/jobs"
                           f"?page=0&pageSize=500"))
    return [listing("careers", company, j["name"], j["url"],
                    location="; ".join(x.get("name") or "" for x in j.get("locations") or []))
            for j in doc.get("items") or [] if want(j.get("name"))]


def bamboohr(token, company, fetch, listing, want, keywords):
    doc = json.loads(fetch(f"https://{token}.bamboohr.com/careers/list"))
    out = []
    for j in doc.get("result") or []:
        if not want(j.get("jobOpeningName")):
            continue
        loc = j.get("location") or {}
        where = ", ".join(x for x in (loc.get("city"), loc.get("state")) if x)
        if j.get("isRemote"):
            where = (where + "; Remote").strip("; ")
        out.append(listing("careers", company, j["jobOpeningName"],
                           f"https://{token}.bamboohr.com/careers/{j['id']}", location=where))
    return out


def pinpoint(token, company, fetch, listing, want, keywords):
    doc = json.loads(fetch(f"https://{token}.pinpointhq.com/postings.json"))
    out = []
    for j in doc.get("data") or []:
        if not want(j.get("title")):
            continue
        row = listing("careers", company, j["title"], j["url"],
                      location=(j.get("location") or {}).get("name") or "")
        row["_text"] = " ".join(str(j.get(k) or "") for k in
                                ("description", "key_responsibilities",
                                 "skills_knowledge_expertise"))
        out.append(row)
    return out


def breezy(token, company, fetch, listing, want, keywords):
    doc = json.loads(fetch(f"https://{token}.breezy.hr/json?verbose=true"))
    out = []
    for j in doc if isinstance(doc, list) else []:
        if not want(j.get("name")):
            continue
        loc = j.get("location") or {}
        where = loc.get("name") or ""
        if loc.get("is_remote") and "remote" not in where.lower():
            where = (where + "; Remote").strip("; ")
        row = listing("careers", company, j["name"], j["url"], location=where,
                      posted=_date(j.get("published_date")))
        row["_text"] = j.get("description") or ""
        out.append(row)
    return out


def recruitee(token, company, fetch, listing, want, keywords):
    """The identifier is the company name, or a whole host for a custom domain."""
    host = token if "." in token else f"{token}.recruitee.com"
    doc = json.loads(fetch(f"https://{host}/api/offers/"))
    out = []
    for j in doc.get("offers") or []:
        if not want(j.get("title")):
            continue
        where = j.get("location") or ""
        if j.get("remote") and "remote" not in where.lower():
            where = (where + "; Remote").strip("; ")
        row = listing("careers", company, j["title"], j.get("careers_url") or "",
                      location=where, posted=_date(j.get("published_at")))
        row["_text"] = (j.get("description") or "") + " " + (j.get("requirements") or "")
        out.append(row)
    return out


def teamtailor(token, company, fetch, listing, want, keywords):
    host = token if "." in token else f"{token}.teamtailor.com"
    doc = json.loads(fetch(f"https://{host}/jobs.json"))
    out = []
    for j in doc.get("items") or []:
        if not want(j.get("title")):
            continue
        places = []
        for loc in (j.get("_jobposting") or {}).get("jobLocation") or []:
            a = loc.get("address") or {}
            places.append(", ".join(x for x in (a.get("addressLocality"),
                                                a.get("addressCountry")) if x))
        row = listing("careers", company, j["title"], j["url"],
                      location="; ".join(p for p in places if p),
                      posted=_date(j.get("date_published")))
        row["_text"] = j.get("content_html") or ""
        out.append(row)
    return out


def personio(token, company, fetch, listing, want, keywords):
    xml = _page(fetch, f"https://{token}.jobs.personio.de/xml?language=en")
    out = []
    for block in re.findall(r"<position>(.*?)</position>", xml, re.S):
        def field(name, block=block):
            m = re.search(rf"<{name}>(.*?)</{name}>", block, re.S)
            return _text(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", m.group(1), flags=re.S)) if m else ""
        title = field("name")
        if not want(title):
            continue
        row = listing("careers", company, title,
                      f"https://{token}.jobs.personio.de/job/{field('id')}?language=en",
                      location=field("office"), posted=_date(field("createdAt")))
        row["_text"] = _text(" ".join(re.findall(r"<value>(.*?)</value>", block, re.S)))
        out.append(row)
    return out


def gem(token, company, fetch, listing, want, keywords):
    doc = json.loads(fetch(f"https://api.gem.com/job_board/v0/{token}/job_posts/"))
    out = []
    for j in doc if isinstance(doc, list) else []:
        if not want(j.get("title")):
            continue
        loc = j.get("location") or {}
        where = loc.get("name") or ""
        if j.get("location_type") == "remote" and "remote" not in where.lower():
            where = (where + "; Remote").strip("; ")
        row = listing("careers", company, j["title"], j["absolute_url"], location=where,
                      posted=_date(j.get("first_published_at")))
        row["_text"] = j.get("content") or ""
        out.append(row)
    return out


def dover(token, company, fetch, listing, want, keywords):
    board = json.loads(fetch(f"https://app.dover.com/api/v1/careers-page-slug/{token}"))["id"]
    doc = json.loads(fetch(f"https://app.dover.com/api/v1/careers-page/{board}/jobs?limit=300"))
    return [listing("careers", company, j["title"],
                    f"https://app.dover.com/apply/{token}/{j['id']}",
                    location="; ".join(x.get("name") or "" for x in j.get("locations") or []))
            for j in doc.get("results") or []
            if want(j.get("title")) and j.get("is_published", True) and not j.get("is_sample")]


_PAYLOCITY = re.compile(r"window\.pageData\s*=\s*(\{.*?\});\s*(?:</script>|window\.)", re.S)


def paylocity(token, company, fetch, listing, want, keywords):
    """The identifier is the employer's long id from its Paylocity careers link."""
    page = _page(fetch, f"https://recruiting.paylocity.com/Recruiting/Jobs/All/{token}")
    m = _PAYLOCITY.search(page)
    if not m:
        raise ValueError("no job data in the page")
    out = []
    for j in json.loads(m.group(1)).get("Jobs") or []:
        if not want(j.get("JobTitle")):
            continue
        loc = j.get("JobLocation") or {}
        where = ", ".join(x for x in (loc.get("City"), loc.get("State")) if x) \
            or j.get("LocationName") or ""
        if j.get("IsRemote"):
            where = (where + "; Remote").strip("; ")
        out.append(listing("careers", company, j["JobTitle"],
                           f"https://recruiting.paylocity.com/Recruiting/Jobs/Details/{j['JobId']}",
                           location=where, posted=_date(j.get("PublishedDate"))))
    return out


_JAZZ = re.compile(r'<li class="list-group-item">.*?<a href="(https://[^"]+/apply/[A-Za-z0-9]+/[^"]*)">'
                   r"\s*(.*?)\s*</a>.*?fa-map-marker'></i>(.*?)</li>", re.S)


def jazzhr(token, company, fetch, listing, want, keywords):
    page = _page(fetch, f"https://{token}.applytojob.com/apply")
    return [listing("careers", company, _text(title), url, location=_text(loc))
            for url, title, loc in _JAZZ.findall(page) if want(_text(title))]


# ── platforms that only answer a search, tried once per keyword ─────────────
_JOBVITE = re.compile(r'<td class="jv-job-list-name">\s*<a href="(/[^"/]+/job/[A-Za-z0-9]+)">(.*?)</a>'
                      r'\s*</td>\s*<td class="jv-job-list-location">(.*?)</td>', re.S)


def jobvite(token, company, fetch, listing, want, keywords, max_pages: int = 4):
    out, seen = [], set()
    for word in keywords or [""]:
        for p in range(max_pages):
            page = _page(fetch, f"https://jobs.jobvite.com/{token}/search"
                                f"?q={urllib.parse.quote(word)}&p={p}")
            rows = _JOBVITE.findall(page)
            for path, title, loc in rows:
                if path not in seen and want(_text(title)):
                    seen.add(path)
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


def rmk(token, company, fetch, listing, want, keywords, max_pages: int = 4):
    """SAP SuccessFactors career sites. The identifier is the careers host. The
    results are a web page in one of two layouts, both read here."""
    out, seen = [], set()
    for word in keywords or [""]:
        for n in range(max_pages):
            page = _page(fetch, f"https://{token}/search/?q=&title={urllib.parse.quote(word)}"
                                f"&sortColumn=referencedate&sortDirection=desc&startrow={n * 100}")
            chunks = re.split(r'<tr class="data-row|<li class="job-tile', page)[1:]
            new = 0
            for chunk in chunks:
                m = _RMK_LINK.search(chunk)
                if not m:
                    continue
                path, title = m.group(1) or m.group(3), _text(m.group(2) or m.group(4))
                if path in seen:
                    continue
                seen.add(path)
                new += 1
                if not want(title):
                    continue
                where = ""
                for g1, g2 in _RMK_LOC.findall(chunk):     # skip the "Location" label itself
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


_PHENOM = re.compile(r"phApp\.ddo\s*=\s*(\{.*?\});\s*phApp\.", re.S)


def phenom(token, company, fetch, listing, want, keywords, max_pages: int = 8):
    """Phenom career sites. The identifier is the site's base address with its
    language part, such as careers.example.com/us/en."""
    base = "https://" + token
    out, seen = [], set()
    for word in keywords or [""]:
        for n in range(max_pages):
            page = _page(fetch, f"{base}/search-results?keywords={urllib.parse.quote(word)}"
                                f"&from={n * 10}")
            m = _PHENOM.search(page)
            if not m:
                raise ValueError("no job data in the page")
            search = (json.loads(m.group(1)).get("eagerLoadRefineSearch") or {})
            jobs = (search.get("data") or {}).get("jobs") or []
            for j in jobs:
                if j.get("jobId") in seen or not want(j.get("title")):
                    continue
                seen.add(j.get("jobId"))
                where = "; ".join(j.get("multi_location") or []) or j.get("location") or ""
                out.append(listing("careers", company, j["title"], f"{base}/job/{j['jobId']}",
                                   location=where, posted=_date(j.get("postedDate"))))
            if len(jobs) < 10 or (n + 1) * 10 >= int(search.get("totalHits") or 0):
                break
    return out


_RADANCY = re.compile(r'<a[^>]*href="([^"]*/job/[^"]+)"[^>]*data-job-id="(\d+)"[^>]*>(.*?)</a>', re.S)
_RADANCY_TITLE = re.compile(r'<(?:h2|h3|span class="[^"]*job-title[^"]*")[^>]*>(.*?)</(?:h2|h3|span)>', re.S)
_RADANCY_LOC = re.compile(r'class="[^"]*(?:job-location|job-info location|location)[^"]*"[^>]*>(.*?)</span>',
                          re.S)


def radancy(token, company, fetch, listing, want, keywords, max_pages: int = 4):
    """Radancy (TalentBrew) career sites. The identifier is the site's base
    address. The answer wraps a piece of web page, and each employer styles it
    differently, so the title and location are looked for in a few places."""
    base = "https://" + token
    origin = "https://" + token.split("/")[0]
    out, seen = [], set()
    for word in keywords or [""]:
        for n in range(1, max_pages + 1):
            doc = json.loads(fetch(
                f"{base}/search-jobs/results?CurrentPage={n}&RecordsPerPage=50"
                f"&Keywords={urllib.parse.quote(word)}&SearchResultsModuleName=Search+Results"
                f"&SearchFiltersModuleName=Search+Filters&SearchType=5"))
            body = doc.get("results") or ""
            rows = _RADANCY.findall(body)
            for href, job_id, inner in rows:
                if job_id in seen:
                    continue
                t = _RADANCY_TITLE.search(inner)
                title = _text(t.group(1)) if t else _text(inner)
                if not want(title):
                    continue
                seen.add(job_id)
                loc = _RADANCY_LOC.search(inner)
                out.append(listing("careers", company, title, origin + href,
                                   location=_text(loc.group(1)) if loc else ""))
            pages = re.search(r'data-total-pages="(\d+)"', body)
            if len(rows) < 50 or (pages and n >= int(pages.group(1))):
                break
    return out


_AVATURE = re.compile(r'<article class="article article--result.*?<a[^>]*href="([^"]*JobDetail/[^"]*?/(\d+))"'
                      r'[^>]*>\s*(.*?)\s*</a>(.*?)</article>', re.S)


def avature(token, company, fetch, listing, want, keywords, max_pages: int = 12):
    """Avature career portals. The identifier is the portal's base address, such
    as example.avature.net/careers. Every employer lays its page out its own
    way, so the location is often missing."""
    base = "https://" + token
    out, seen = [], set()
    for word in keywords or [""]:
        offset = 0
        for _ in range(max_pages):
            page = _page(fetch, f"{base}/SearchJobs/?search={urllib.parse.quote(word)}"
                                f"&jobOffset={offset}")
            rows = _AVATURE.findall(page)
            for href, job_id, title, rest in rows:
                if job_id in seen:
                    continue
                seen.add(job_id)
                if not want(_text(title)):
                    continue
                loc = re.search(r'class="[^"]*list-item-location[^"]*"[^>]*>(.*?)</span>', rest, re.S)
                url = href if href.startswith("http") else "https://" + token.split("/")[0] + href
                out.append(listing("careers", company, _text(title), url,
                                   location=_text(loc.group(1)) if loc else ""))
            if not rows:
                break
            offset += len(rows)
            legend = re.search(r"(\d+)\s*-\s*(\d+)\s+of\s+(\d+)", page)
            if legend and offset >= int(legend.group(3)):
                break
    return out


_TALEO_BODY = {
    "multilineEnabled": False,
    "sortingSelection": {"sortBySelectionParam": "3", "ascendingSortingOrder": "false"},
    "fieldData": {"fields": {"KEYWORD": "", "LOCATION": ""}, "valid": True},
    "filterSelectionParam": {"searchFilterSelections": [
        {"id": "POSTING_DATE", "selectedValues": []}, {"id": "LOCATION", "selectedValues": []},
        {"id": "JOB_FIELD", "selectedValues": []}]},
    "advancedSearchFiltersSelectionParam": {"searchFilterSelections": [
        {"id": k, "selectedValues": []} for k in (
            "ORGANIZATION", "LOCATION", "JOB_FIELD", "JOB_NUMBER", "URGENT_JOB",
            "EMPLOYEE_STATUS", "STUDY_LEVEL", "WILL_TRAVEL", "JOB_SHIFT")]},
    "pageNo": 1,
}
_TALEO_PORTALS: Dict[str, str] = {}


def taleo(token, company, fetch, listing, want, keywords, max_pages: int = 6):
    """Taleo career sections. The identifier is tenant/section, as in the address
    tenant.taleo.net/careersection/section/. The search needs a number that the
    section's own search page carries, so that page is read first."""
    tenant, section = token.split("/")
    base = f"https://{tenant}.taleo.net/careersection"
    if token not in _TALEO_PORTALS:
        page = _page(fetch, f"{base}/{section}/jobsearch.ftl?lang=en")
        m = re.search(r"portalNo:\s*'(\d+)'", page)
        if not m:
            raise ValueError("this career section does not offer a search")
        _TALEO_PORTALS[token] = m.group(1)
    out, seen = [], set()
    for word in keywords or [""]:
        for n in range(1, max_pages + 1):
            body = json.loads(json.dumps(_TALEO_BODY))
            body["fieldData"]["fields"]["KEYWORD"] = word
            body["pageNo"] = n
            doc = json.loads(fetch(
                f"{base}/rest/jobboard/searchjobs?lang=en&portal={_TALEO_PORTALS[token]}",
                json_body=body, headers={"tz": "GMT-05:00"}))
            rows = doc.get("requisitionList") or []
            for j in rows:
                cols = j.get("column") or []
                number = j.get("contestNo")
                if not cols or number in seen:
                    continue
                seen.add(number)
                title = cols[j.get("linkedColumn", 0) if isinstance(j.get("linkedColumn"), int) else 0]
                if not want(title):
                    continue
                where = ""
                for i in j.get("locationsColumns") or []:
                    try:
                        where = "; ".join(json.loads(cols[i]))
                    except (ValueError, IndexError, TypeError):
                        where = cols[i] if i < len(cols) else ""
                    break
                out.append(listing("careers", company, title,
                                   f"{base}/{section}/jobdetail.ftl?job={number}&lang=en",
                                   location=where))
            paging = doc.get("pagingData") or {}
            if len(rows) < int(paging.get("pageSize") or 25) or \
                    n * int(paging.get("pageSize") or 25) >= int(paging.get("totalCount") or 0):
                break
    return out


READERS: Dict[str, Callable] = {
    "rippling": rippling, "bamboohr": bamboohr, "pinpoint": pinpoint, "breezy": breezy,
    "recruitee": recruitee, "teamtailor": teamtailor, "personio": personio, "gem": gem,
    "dover": dover, "paylocity": paylocity, "jazzhr": jazzhr, "jobvite": jobvite,
    "rmk": rmk, "phenom": phenom, "radancy": radancy, "avature": avature, "taleo": taleo,
}

# How to recognise an employer on one of these platforms from a posting link.
# Only platforms whose address names the employer can be recognised this way.
LINK_PATTERNS = [
    ("rippling", re.compile(r"ats\.rippling\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/?#]+)/jobs")),
    ("bamboohr", re.compile(r"https?://([a-z0-9-]+)\.bamboohr\.com/")),
    ("pinpoint", re.compile(r"https?://([a-z0-9-]+)\.pinpointhq\.com")),
    ("breezy", re.compile(r"https?://([a-z0-9-]+)\.breezy\.hr")),
    ("jazzhr", re.compile(r"https?://([a-z0-9-]+)\.applytojob\.com/")),
    ("jobvite", re.compile(r"jobs\.jobvite\.com/(?:careers/)?([^/?#]+)/(?:job|jobs|search)")),
    ("recruitee", re.compile(r"https?://([a-z0-9-]+)\.recruitee\.com")),
    ("teamtailor", re.compile(r"https?://([a-z0-9-]+)\.teamtailor\.com")),
    ("personio", re.compile(r"https?://([a-z0-9-]+)\.jobs\.personio\.(?:de|com)")),
    ("gem", re.compile(r"jobs\.gem\.com/([^/?#]+)")),
    ("dover", re.compile(r"app\.dover\.com/(?:apply/)?([^/?#]+)/")),
    ("paylocity", re.compile(r"recruiting\.paylocity\.com/[Rr]ecruiting/[Jj]obs/All/([0-9a-f-]{36})")),
    ("taleo", re.compile(r"https?://([a-z0-9-]+)\.taleo\.net/careersection/([A-Za-z0-9_-]+)/")),
    ("avature", re.compile(r"https?://([a-z0-9-]+\.avature\.net(?:/[a-z]{2}_[A-Z]{2})?/[A-Za-z0-9_-]+)/"
                           r"(?:JobDetail|SearchJobs)")),
]


def discover(url: str):
    """(platform, identifier) for a posting link on one of these platforms."""
    for name, pat in LINK_PATTERNS:
        m = pat.search(url)
        if not m:
            continue
        token = "/".join(m.groups())
        if token.split("/")[0].lower() in ("www", "app", "jobs", "careers", "api", "rest"):
            continue
        return name, token
    return None


def probe(host: str, fetch) -> Optional[str]:
    """Work out which platform an employer's own careers address runs on, by
    asking for the page each platform is known to answer. Returns an identifier
    such as "jibe:careers.example.com", or None."""
    try:
        doc = json.loads(fetch(f"https://{host}/api/jobs?page=1&limit=1"))
        if isinstance(doc, dict) and "jobs" in doc and "totalCount" in doc:
            return f"jibe:{host}"
    except Exception:                                     # noqa: BLE001
        pass
    try:
        page = _page(fetch, f"https://{host}/search/?q=&startrow=0")
        if "jobTitle-link" in page:
            return f"rmk:{host}"
    except Exception:                                     # noqa: BLE001
        pass
    for base in ("/us/en", "/global/en", "/en"):
        try:
            page = _page(fetch, f"https://{host}{base}/search-results?keywords=&from=0")
            if _PHENOM.search(page):
                return f"phenom:{host}{base}"
        except Exception:                                 # noqa: BLE001
            pass
    try:
        doc = json.loads(fetch(f"https://{host}/search-jobs/results?CurrentPage=1&RecordsPerPage=5"
                               f"&Keywords=&SearchResultsModuleName=Search+Results"
                               f"&SearchFiltersModuleName=Search+Filters&SearchType=5"))
        if isinstance(doc, dict) and "results" in doc and "data-job-id" in (doc.get("results") or ""):
            return f"radancy:{host}"
    except Exception:                                     # noqa: BLE001
        pass
    return None
