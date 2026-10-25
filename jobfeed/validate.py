"""Check that a job link is still live and still accepting applications."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from .models import Job

CLOSED_TEXT = re.compile(
    r"no longer (accepting applications|available|open|active|posted)|"
    r"(job|position|posting|requisition|role) (has been|is) (closed|filled|removed|expired|no longer)|"
    r"this job (has )?expired|job not found|position (has been )?filled|"
    r"the page you are looking for (doesn't|does not|no longer) exist|"
    r"we couldn'?t find (the|this) (job|page|position)|this posting is closed|"
    r"applications? (are|is) (now )?closed",
    re.I,
)

# Sources whose feed only contains open jobs - no need to re-check
LIVE_FEEDS = {"greenhouse", "lever", "ashby", "smartrecruiters"}


def _looks_like_generic_page(original: str, final: str) -> bool:
    o, f = urlparse(original), urlparse(final)
    if "error=true" in f.query:          # Greenhouse redirects closed jobs here
        return True
    o_parts = [p for p in o.path.split("/") if p]
    f_parts = [p for p in f.path.split("/") if p]
    # Deep job URL redirected to a careers root page
    return len(o_parts) >= 2 and len(f_parts) <= 1 and o.netloc.split(".")[-2:] == f.netloc.split(".")[-2:]


def check_link(session, job: Job, timeout: int = 15) -> None:
    if job.link_status:                  # already decided (e.g. Workday 404)
        return
    if not job.url:
        job.link_status = "no link"
        return
    if job.source in LIVE_FEEDS:
        job.link_status = "open (live company feed)"
        return
    host = urlparse(job.url).netloc.lower()
    if "linkedin.com" in host or "indeed.com" in host or "glassdoor.com" in host:
        # These block automated checks; don't hammer them - mark for a manual click
        job.link_status = "unverified (job board blocks checks)"
        return
    original = job.url
    try:
        r = session.get(original, timeout=timeout, allow_redirects=True,
                        headers={"Accept": "text/html,application/xhtml+xml"})
        final = r.url or original
        if r.status_code in (404, 410):
            job.link_status = f"closed ({r.status_code})"
        elif r.status_code >= 400:
            job.link_status = f"unverified (HTTP {r.status_code})"
        elif final != original and _looks_like_generic_page(original, final):
            job.link_status = "closed (redirected to careers home)"
        elif CLOSED_TEXT.search(r.text[:200000]):
            job.link_status = "closed (page says no longer accepting)"
        else:
            job.link_status = "open"
            # Aggregator links (e.g. Adzuna) redirect to the real page - keep the real one
            if final != original and job.source in ("adzuna", "jsearch"):
                job.url = final
                from .ats import is_direct_employer_link
                if is_direct_employer_link(final):
                    job.via_job_board = False
    except Exception as e:  # noqa: BLE001
        job.link_status = f"unverified ({type(e).__name__})"


def check_links(session, jobs: list[Job], workers: int = 16, timeout: int = 15) -> None:
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(lambda j: check_link(session, j, timeout), jobs))


def is_closed(job: Job) -> bool:
    return job.link_status.startswith("closed")
