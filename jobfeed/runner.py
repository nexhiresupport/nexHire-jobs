"""Main pipeline: collect → filter → dedupe → validate → export."""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

from .aggregators import adzuna_available, fetch_adzuna, fetch_jsearch, jsearch_available
from .ats import (classify_ats_url, fetch_ashby, fetch_greenhouse, fetch_lever,
                   fetch_smartrecruiters, fetch_workday_detail)
from .discovery import discover_urls, discovery_available
from .filters import (add_flags, check_eligibility, classify_employment, classify_work_type,
                      extract_experience, extract_recruiter_email, is_us_location,
                      make_title_matcher)
from .http import make_session
from .models import Job
from .output import send_email, write_excel
from .validate import check_links, is_closed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
BASE = Path(__file__).parent.parent
DATA = BASE / "data"
OUTPUT_DIR = BASE / "output"


def load_config() -> dict:
    with open(BASE / "config.yaml") as f:
        return yaml.safe_load(f)


def load_companies() -> dict:
    with open(BASE / "companies.yaml") as f:
        return yaml.safe_load(f)


def load_seen() -> set[str]:
    p = DATA / "seen.json"
    if p.exists():
        return set(json.loads(p.read_text()))
    return set()


def save_seen(seen: set[str]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "seen.json").write_text(json.dumps(sorted(seen), indent=2))


def lookback_hours(cfg: dict, now_ist: datetime) -> int:
    if now_ist.weekday() == 0:  # Monday IST
        return cfg.get("lookback_hours_monday", 73)
    return cfg.get("lookback_hours_weekday", 25)


def annotate(job: Job, cfg: dict, staffing_kw: list[str]) -> None:
    job.work_type = classify_work_type(job)
    job.employment_type = classify_employment(job)
    job.experience_years = extract_experience(job)
    job.recruiter_email = extract_recruiter_email(job)
    add_flags(job, staffing_kw)


def run_ats(session, companies: dict, cfg: dict, title_ok, lookback_h: int, now_utc: datetime) -> list[Job]:
    jobs: list[Job] = []
    src = cfg.get("sources", {})
    cutoff = now_utc - timedelta(hours=lookback_h)

    if src.get("greenhouse", True):
        for slug in companies.get("greenhouse", []):
            try:
                for j in fetch_greenhouse(session, slug):
                    if j.posted_at and j.posted_at < cutoff:
                        continue
                    if title_ok(j.title):
                        jobs.append(j)
            except Exception as e:
                log.warning("Greenhouse %s: %s", slug, e)

    if src.get("lever", True):
        for slug in companies.get("lever", []):
            try:
                for j in fetch_lever(session, slug):
                    if j.posted_at and j.posted_at < cutoff:
                        continue
                    if title_ok(j.title):
                        jobs.append(j)
            except Exception as e:
                log.warning("Lever %s: %s", slug, e)

    if src.get("ashby", True):
        for slug in companies.get("ashby", []):
            try:
                for j in fetch_ashby(session, slug):
                    if j.posted_at and j.posted_at < cutoff:
                        continue
                    if title_ok(j.title):
                        jobs.append(j)
            except Exception as e:
                log.warning("Ashby %s: %s", slug, e)

    if src.get("smartrecruiters", True):
        for slug in companies.get("smartrecruiters", []):
            try:
                for j in fetch_smartrecruiters(session, slug, title_ok):
                    if j.posted_at and j.posted_at < cutoff:
                        continue
                    jobs.append(j)
            except Exception as e:
                log.warning("SmartRecruiters %s: %s", slug, e)

    return jobs


def run_aggregators(session, cfg: dict, lookback_h: int) -> list[Job]:
    jobs: list[Job] = []
    phrases = cfg.get("search_phrases", ["data engineer"])
    agg = cfg.get("sources", {})
    date_posted = "today" if lookback_h <= 25 else "3days"

    if agg.get("jsearch", True) and jsearch_available():
        for phrase in phrases:
            try:
                jobs.extend(fetch_jsearch(session, phrase, date_posted, cfg.get("jsearch", {})))
            except Exception as e:
                log.warning("JSearch %s: %s", phrase, e)

    if agg.get("adzuna", True) and adzuna_available():
        max_days = max(1, lookback_h // 24 + 1)
        for phrase in phrases:
            try:
                jobs.extend(fetch_adzuna(session, phrase, max_days, cfg.get("adzuna", {})))
            except Exception as e:
                log.warning("Adzuna %s: %s", phrase, e)

    return jobs


def run_discovery(session, cfg: dict, lookback_h: int, now_utc: datetime,
                  title_ok, cutoff: datetime) -> list[Job]:
    if not discovery_available():
        return []
    disc_cfg = cfg.get("discovery", {})
    phrases = cfg.get("search_phrases", ["data engineer"])[:3]
    site_groups = disc_cfg.get("site_groups", [
        "site:greenhouse.io OR site:lever.co",
        "site:ashbyhq.com OR site:smartrecruiters.com",
        "site:myworkdayjobs.com OR site:jobs.lever.co",
    ])
    pages = disc_cfg.get("pages_per_query", 2)
    try:
        results, n_queries = discover_urls(session, phrases, site_groups, lookback_h, now_utc, pages)
        log.info("Discovery: %d URLs from %d Brave queries", len(results), n_queries)
    except Exception as e:
        log.warning("Discovery failed: %s", e)
        return []

    jobs = []
    disc_file = DATA / "companies_discovered.json"
    discovered = json.loads(disc_file.read_text()) if disc_file.exists() else {}

    for item in results:
        url, raw_title = item["url"], item.get("title", "")
        ats, slug = classify_ats_url(url)
        if not ats:
            continue
        if not title_ok(raw_title):
            continue
        if ats == "workday":
            try:
                j = fetch_workday_detail(session, url, raw_title)
                if j and title_ok(j.title) and (not j.posted_at or j.posted_at >= cutoff):
                    jobs.append(j)
                    if slug:
                        discovered.setdefault("workday", [])
                        if slug not in discovered["workday"]:
                            discovered["workday"].append(slug)
            except Exception as e:
                log.debug("Workday %s: %s", url, e)
        elif slug and ats in ("greenhouse", "lever", "ashby", "smartrecruiters"):
            discovered.setdefault(ats, [])
            if slug not in discovered[ats]:
                discovered[ats].append(slug)

    DATA.mkdir(parents=True, exist_ok=True)
    disc_file.write_text(json.dumps(discovered, indent=2))
    return jobs


def main() -> None:
    cfg = load_config()
    companies = load_companies()
    seen = load_seen()

    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(IST)
    lb_h = lookback_hours(cfg, now_ist)
    cutoff = now_utc - timedelta(hours=lb_h)
    log.info("Run start %s IST | lookback %dh", now_ist.strftime("%Y-%m-%d %H:%M"), lb_h)

    title_ok = make_title_matcher(
        cfg.get("role_keywords", ["data engineer"]),
        cfg.get("title_exclude", []),
    )
    staffing_kw = [k.lower() for k in cfg.get("staffing_keywords", [])]
    elig_cfg = {k: cfg.get(k) for k in
                ("exclude_clearance", "exclude_citizenship_only", "exclude_itar_us_person", "exclude_no_sponsorship")}
    link_cfg = cfg.get("link_check", {})
    out_cfg = cfg.get("output", {})
    max_desc = out_cfg.get("max_description_chars", 30000)

    session = make_session()

    log_rows: list[tuple] = []
    log_rows.append(("Run time (UTC)", now_utc.strftime("%Y-%m-%d %H:%M:%S")))
    log_rows.append(("Run time (IST)", now_ist.strftime("%Y-%m-%d %H:%M:%S")))
    log_rows.append(("Lookback hours", str(lb_h)))

    # Collect
    raw: list[Job] = []
    ats_jobs = run_ats(session, companies, cfg, title_ok, lb_h, now_utc)
    raw.extend(ats_jobs)
    log_rows.append(("ATS jobs fetched", str(len(ats_jobs))))

    agg_jobs = run_aggregators(session, cfg, lb_h)
    raw.extend(agg_jobs)
    log_rows.append(("Aggregator jobs fetched", str(len(agg_jobs))))

    disc_jobs = run_discovery(session, cfg, lb_h, now_utc, title_ok, cutoff)
    raw.extend(disc_jobs)
    log_rows.append(("Discovery jobs fetched", str(len(disc_jobs))))

    log.info("Total raw: %d", len(raw))

    # Filter
    kept: list[Job] = []
    excluded: list[Job] = []
    deduped_keys: set[str] = set()
    state_keys_new: set[str] = set()

    for job in raw:
        # US location
        if not is_us_location(job.location):
            job.exclude_reason = f"Non-US location: {job.location}"
            excluded.append(job)
            continue
        # title match
        if not title_ok(job.title):
            job.exclude_reason = f"Title mismatch: {job.title}"
            excluded.append(job)
            continue
        # state / dedupe
        sk = job.state_key()
        if sk in seen:
            continue
        dk = job.dedupe_key()
        if dk in deduped_keys:
            continue
        deduped_keys.add(dk)
        state_keys_new.add(sk)
        # eligibility
        reason = check_eligibility(job, elig_cfg)
        if reason:
            job.exclude_reason = reason
            excluded.append(job)
            continue
        # annotate
        annotate(job, cfg, staffing_kw)
        kept.append(job)

    log.info("After filter/dedupe: %d kept, %d excluded", len(kept), len(excluded))
    log_rows.append(("After filter/dedupe kept", str(len(kept))))
    log_rows.append(("Excluded", str(len(excluded))))

    # Validate links
    workers = link_cfg.get("workers", 16)
    timeout = link_cfg.get("timeout", 15)
    check_links(session, kept, workers=workers, timeout=timeout)

    closed_jobs = [j for j in kept if is_closed(j)]
    kept = [j for j in kept if not is_closed(j)]
    log.info("After link check: %d open, %d closed", len(kept), len(closed_jobs))
    for j in closed_jobs:
        j.exclude_reason = f"Link closed: {j.link_status}"
        excluded.append(j)
    log_rows.append(("Open after link check", str(len(kept))))
    log_rows.append(("Closed links removed", str(len(closed_jobs))))

    # Save state
    seen.update(state_keys_new)
    save_seen(seen)

    # Excel
    run_date = now_ist.strftime("%Y-%m-%d")
    out_dir = BASE / out_cfg.get("dir", "output")
    xlsx_path = out_dir / f"DataEngineerJobs_{run_date}.xlsx"
    write_excel(xlsx_path, kept, excluded, log_rows, max_desc)
    log.info("Saved %s", xlsx_path)

    # Email
    email_result = send_email(xlsx_path, len(kept), run_date)
    log.info("Email: %s", email_result)

    print(f"\n✅  {len(kept)} new jobs → {xlsx_path}")
    if excluded:
        print(f"   {len(excluded)} excluded (see Excluded sheet)")
