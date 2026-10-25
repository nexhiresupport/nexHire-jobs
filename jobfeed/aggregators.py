"""Aggregator sources: JSearch (Google for Jobs: LinkedIn, Indeed, Glassdoor, ZipRecruiter, Dice...) and Adzuna."""
from __future__ import annotations

import os
from urllib.parse import urlparse

from .ats import ATS_DOMAINS, is_direct_employer_link
from .models import Job, parse_dt


# ---------- JSearch ----------
def _jsearch_endpoint():
    if os.getenv("OPENWEBNINJA_API_KEY"):
        return "https://api.openwebninja.com/jsearch/search", {"x-api-key": os.environ["OPENWEBNINJA_API_KEY"]}
    if os.getenv("JSEARCH_RAPIDAPI_KEY"):
        return "https://jsearch.p.rapidapi.com/search", {
            "X-RapidAPI-Key": os.environ["JSEARCH_RAPIDAPI_KEY"],
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
    return None, None


def jsearch_available() -> bool:
    return _jsearch_endpoint()[0] is not None


def _best_apply_link(j: dict) -> tuple[str, bool]:
    """Prefer the employer's own ATS page over LinkedIn/Indeed. Returns (url, via_job_board)."""
    options = j.get("apply_options") or []
    for o in options:
        link = o.get("apply_link") or ""
        if any(d in urlparse(link).netloc.lower() for d in ATS_DOMAINS):
            return link, False
    for o in options:
        link = o.get("apply_link") or ""
        if o.get("is_direct") and is_direct_employer_link(link):
            return link, False
    main = j.get("job_apply_link") or ""
    if main and (j.get("job_apply_is_direct") or is_direct_employer_link(main)):
        return main, False
    return main or (options[0].get("apply_link") if options else ""), True


def fetch_jsearch(session, phrase: str, date_posted: str, cfg: dict) -> list[Job]:
    url, headers = _jsearch_endpoint()
    params = {
        "query": f"{phrase} in USA",
        "page": 1,
        "num_pages": cfg.get("num_pages", 3),
        "date_posted": date_posted,          # today | 3days
        "country": "us",
        "employment_types": cfg.get("employment_types", "FULLTIME,CONTRACTOR"),
    }
    r = session.get(url, params=params, headers=headers, timeout=60)
    r.raise_for_status()
    jobs = []
    for j in r.json().get("data") or []:
        link, via_board = _best_apply_link(j)
        loc = j.get("job_location") or ", ".join(
            x for x in (j.get("job_city"), j.get("job_state"), j.get("job_country")) if x)
        jobs.append(Job(
            source="jsearch",
            source_id=str(j.get("job_id")),
            title=(j.get("job_title") or "").strip(),
            company=j.get("employer_name") or "",
            location=loc or "",
            url=link,
            description=j.get("job_description") or "",
            posted_at=parse_dt(j.get("job_posted_at_timestamp") or j.get("job_posted_at_datetime_utc")),
            employment_hint=j.get("job_employment_type") or ", ".join(j.get("job_employment_types") or []),
            remote_hint="Remote" if j.get("job_is_remote") else "",
            via_job_board=via_board,
            publisher=j.get("job_publisher") or "",
        ))
    return jobs


# ---------- Adzuna ----------
def adzuna_available() -> bool:
    return bool(os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_APP_KEY"))


def fetch_adzuna(session, phrase: str, max_days_old: int, cfg: dict) -> list[Job]:
    jobs = []
    for page in range(1, cfg.get("pages", 3) + 1):
        r = session.get(
            f"https://api.adzuna.com/v1/api/jobs/us/search/{page}",
            params={
                "app_id": os.environ["ADZUNA_APP_ID"],
                "app_key": os.environ["ADZUNA_APP_KEY"],
                "what_phrase": phrase,
                "max_days_old": max_days_old,
                "results_per_page": cfg.get("results_per_page", 50),
                "sort_by": "date",
                "content-type": "application/json",
            },
            timeout=30,
        )
        r.raise_for_status()
        results = r.json().get("results") or []
        for j in results:
            hint = " ".join(x for x in (j.get("contract_type"), j.get("contract_time")) if x)
            jobs.append(Job(
                source="adzuna",
                source_id=str(j.get("id")),
                title=(j.get("title") or "").replace("<strong>", "").replace("</strong>", "").strip(),
                company=(j.get("company") or {}).get("display_name", ""),
                location=(j.get("location") or {}).get("display_name", ""),
                url=j.get("redirect_url", ""),
                description=j.get("description") or "",
                posted_at=parse_dt(j.get("created")),
                employment_hint=hint,
                via_job_board=True,
                publisher="Adzuna",
                description_complete=False,   # Adzuna only returns a snippet
            ))
        if len(results) < cfg.get("results_per_page", 50):
            break
    return jobs
