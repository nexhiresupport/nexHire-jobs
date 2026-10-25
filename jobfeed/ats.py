"""Company career-site sources (public, no-key APIs that power each company's careers page)."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .http import polite_sleep
from .models import Job, html_to_text, parse_dt


# ---------- Greenhouse ----------
def fetch_greenhouse(session, slug: str) -> list[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    company = slug
    jobs = []
    for j in data.get("jobs", []):
        company = j.get("company_name") or company
        jobs.append(Job(
            source="greenhouse",
            source_id=str(j.get("id")),
            title=j.get("title", "").strip(),
            company=company,
            location=(j.get("location") or {}).get("name", ""),
            url=j.get("absolute_url", ""),
            description=html_to_text(j.get("content")),
            posted_at=parse_dt(j.get("first_published") or j.get("updated_at")),
        ))
    return jobs


# ---------- Lever ----------
def fetch_lever(session, slug: str) -> list[Job]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    polite_sleep(1.0)  # Lever robots.txt asks for a 1-second crawl delay
    jobs = []
    for j in r.json():
        cats = j.get("categories") or {}
        parts = [j.get("descriptionPlain") or html_to_text(j.get("description"))]
        for lst in j.get("lists") or []:
            parts.append(f"{lst.get('text', '')}\n{html_to_text(lst.get('content'))}")
        parts.append(j.get("additionalPlain") or html_to_text(j.get("additional")))
        loc = cats.get("location") or ", ".join(cats.get("allLocations") or [])
        jobs.append(Job(
            source="lever",
            source_id=str(j.get("id")),
            title=(j.get("text") or "").strip(),
            company=slug,
            location=loc or "",
            url=j.get("hostedUrl") or j.get("applyUrl") or "",
            description="\n\n".join(p for p in parts if p),
            posted_at=parse_dt(j.get("createdAt")),
            employment_hint=cats.get("commitment") or "",
            remote_hint=j.get("workplaceType") or "",
        ))
    return jobs


# ---------- Ashby ----------
def fetch_ashby(session, slug: str) -> list[Job]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    jobs = []
    for j in r.json().get("jobs", []):
        if j.get("isListed") is False:
            continue
        loc = j.get("location") or ""
        country = (((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry")) or ""
        if country and country not in loc:
            loc = f"{loc}, {country}" if loc else country
        remote = j.get("workplaceType") or ("Remote" if j.get("isRemote") else "")
        jobs.append(Job(
            source="ashby",
            source_id=str(j.get("id")),
            title=(j.get("title") or "").strip(),
            company=slug,
            location=loc,
            url=j.get("jobUrl") or j.get("applyUrl") or "",
            description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
            posted_at=parse_dt(j.get("publishedAt")),
            employment_hint=j.get("employmentType") or "",
            remote_hint=remote,
        ))
    return jobs


# ---------- SmartRecruiters ----------
def fetch_smartrecruiters(session, slug: str, keyword_filter=None) -> list[Job]:
    """List postings, then fetch full detail only for titles that match (saves requests)."""
    jobs, offset = [], 0
    while True:
        r = session.get(
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
            params={"limit": 100, "offset": offset, "country": "us"}, timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        content = data.get("content", [])
        for p in content:
            title = (p.get("name") or "").strip()
            if keyword_filter and not keyword_filter(title):
                continue
            jobs.append(_smartrecruiters_detail(session, slug, str(p.get("id")), p))
        offset += len(content)
        if not content or offset >= data.get("totalFound", 0) or offset >= 1000:
            break
    return jobs


def _smartrecruiters_detail(session, slug: str, pid: str, summary: dict | None = None) -> Job:
    summary = summary or {}
    desc, complete = "", False
    try:
        r = session.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{pid}", timeout=30)
        r.raise_for_status()
        d = r.json()
        sections = ((d.get("jobAd") or {}).get("sections") or {})
        desc = "\n\n".join(html_to_text((sections.get(k) or {}).get("text"))
                           for k in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"))
        summary = {**summary, **d}
        complete = True
    except Exception:
        pass
    loc = summary.get("location") or {}
    loc_str = ", ".join(x for x in (loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()) if x)
    return Job(
        source="smartrecruiters",
        source_id=pid,
        title=(summary.get("name") or "").strip(),
        company=(summary.get("company") or {}).get("name") or slug,
        location=loc_str,
        url=f"https://jobs.smartrecruiters.com/{slug}/{pid}",
        description=desc.strip(),
        posted_at=parse_dt(summary.get("releasedDate")),
        employment_hint=(summary.get("typeOfEmployment") or {}).get("label", ""),
        remote_hint="Remote" if loc.get("remote") else ("Hybrid" if loc.get("hybrid") else ""),
        description_complete=complete,
    )


# ---------- Workday (single posting detail, for links found by discovery) ----------
WD_RE = re.compile(
    r"https?://(?P<host>(?P<tenant>[^./]+)\.(?P<wd>wd\d+)\.myworkdayjobs\.com)/(?:(?:[a-z]{2}-[A-Z]{2})/)?(?P<site>[^/]+)/job/(?P<path>.+)$"
)


def fetch_workday_detail(session, url: str, fallback_title: str = "") -> Job | None:
    m = WD_RE.match(url.split("?")[0])
    if not m:
        return None
    api = f"https://{m['host']}/wday/cxs/{m['tenant']}/{m['site']}/job/{m['path']}"
    r = session.get(api, timeout=30)
    if r.status_code == 404:
        j = Job(source="workday", source_id=url, title=fallback_title, company=m["tenant"], url=url)
        j.link_status = "closed (404)"
        return j
    r.raise_for_status()
    d = r.json()
    info = d.get("jobPostingInfo") or {}
    org = (d.get("hiringOrganization") or {}).get("name") or m["tenant"]
    locs = [info.get("location") or ""] + list(info.get("additionalLocations") or [])
    return Job(
        source="workday",
        source_id=str(info.get("jobReqId") or info.get("id") or url),
        title=(info.get("title") or fallback_title).strip(),
        company=org,
        location="; ".join(l for l in locs if l),
        url=info.get("externalUrl") or url,
        description=html_to_text(info.get("jobDescription")),
        posted_at=parse_dt(info.get("startDate")),
        employment_hint=info.get("timeType") or "",
        remote_hint=info.get("remoteType") or "",
    )


# ---------- URL helpers used by discovery ----------
def classify_ats_url(url: str) -> tuple[str, str] | None:
    """Return (ats, slug) for a careers URL, else None."""
    p = urlparse(url)
    host, parts = p.netloc.lower(), [x for x in p.path.split("/") if x]
    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io") and parts:
        if parts[0] == "embed":
            from urllib.parse import parse_qs
            tok = parse_qs(p.query).get("for", [""])[0]
            return ("greenhouse", tok) if tok else None
        return "greenhouse", parts[0]
    if host == "jobs.lever.co" and parts:
        return "lever", parts[0]
    if host == "jobs.ashbyhq.com" and parts:
        return "ashby", parts[0]
    if host == "jobs.smartrecruiters.com" and parts:
        return "smartrecruiters", parts[0]
    if host.endswith(".myworkdayjobs.com"):
        return "workday", host.split(".")[0]
    return None


ATS_DOMAINS = (
    "greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com", "smartrecruiters.com",
    "workable.com", "jobvite.com", "icims.com", "bamboohr.com", "recruitee.com", "taleo.net",
    "successfactors.com", "oraclecloud.com", "breezy.hr", "jazzhr.com", "applytojob.com",
    "paylocity.com", "ultipro.com", "ukg.com", "adp.com", "dayforcehcm.com", "rippling.com",
)


def is_direct_employer_link(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    boards = ("linkedin.", "indeed.", "glassdoor.", "ziprecruiter.", "dice.", "monster.", "simplyhired.",
              "careerbuilder.", "talent.com", "jooble.", "adzuna.", "lensa.", "jobright.", "builtin.",
              "upwork.", "snagajob.", "salary.com", "learn4good.", "jobilize.", "teal", "bebee.")
    if any(b in host for b in boards):
        return False
    return True
