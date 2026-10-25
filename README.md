# Data Engineer Job Feed

Automated pipeline that pulls **US Data Engineer job postings** from every major source and saves them to a dated Excel file every weekday at **7 AM IST (01:30 UTC)** via GitHub Actions.

---

## What it collects

| Source | Type | Key |
|--------|------|-----|
| Greenhouse (50+ companies) | Direct ATS API | — (free) |
| Lever | Direct ATS API | — (free) |
| Ashby | Direct ATS API | — (free) |
| SmartRecruiters | Direct ATS API | — (free) |
| JSearch / Google for Jobs | LinkedIn, Indeed, Glassdoor, Dice, ZipRecruiter | `JSEARCH_RAPIDAPI_KEY` or `OPENWEBNINJA_API_KEY` |
| Adzuna | Job aggregator | `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` |
| Brave Search Discovery | Finds new company ATS boards (Brian's-style) | `BRAVE_API_KEY` |

---

## Excel columns (Jobs sheet)

| Column | Purpose |
|--------|---------|
| Company | Employer name |
| Role | Job title |
| Location | As listed |
| Work Type | remote / hybrid / on-site / unspecified |
| Employment Type | Full-time / W2 Contract / C2C / Contract / Contract-to-hire |
| Careers Link | Direct job URL (clickable) |
| Recruiter Email | Email found in JD (W2/contract roles) |
| **careersLink for resume prompt** | C2C → job URL · W2 → recruiter email; paste directly into your resume-tailoring prompt |
| Experience Req (yrs) | Smallest years figure extracted from JD |
| Profile (3yr/5yr) | ≤3 yrs → 3yr, else 5yr |
| Posted (IST) | Posting time in India Standard Time |
| Source | greenhouse / jsearch / adzuna / … |
| Sponsorship | "No sponsorship" / "Sponsorship mentioned as available" |
| Flags | Staffing agency · LinkedIn/Easy Apply · snippet JD · evergreen |
| Link Status | open / closed / unverified |
| Job Description | Full JD (up to 30 000 chars) |

Additional sheets: **Excluded** (reason) and **Run Log**.

---

## Auto-filters

Jobs are **dropped** when the description contains:
- Security clearance / active clearance required
- US citizens only / green-card holders only / USC/GC only
- ITAR / U.S. person requirements
- Federal or DoD restrictions

Jobs with "no sponsorship" are **flagged** (not dropped) so you can still apply to sponsor-friendly employers that forgot to remove boilerplate.

---

## One-time setup

### 1 · Fork the repo

```
https://github.com/<you>/data-engineer-job-feed
```

### 2 · Add GitHub Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**.

| Secret | Where to get it |
|--------|-----------------|
| `JSEARCH_RAPIDAPI_KEY` | [rapidapi.com → JSearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) *or* |
| `OPENWEBNINJA_API_KEY` | [openwebninja.com](https://openwebninja.com) (often cheaper) |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | [developer.adzuna.com](https://developer.adzuna.com) — free tier ~1 000 calls/mo |
| `BRAVE_API_KEY` *(optional)* | [api.search.brave.com](https://api.search.brave.com) — $5 free credit/mo |
| `SMTP_USER` / `SMTP_PASS` / `EMAIL_TO` *(optional)* | Gmail app password for delivery |

**Need at least one of** `JSEARCH_RAPIDAPI_KEY` or `OPENWEBNINJA_API_KEY` for aggregated results.  
The ATS direct feeds (Greenhouse, Lever, Ashby, SmartRecruiters) need no key.

### 3 · Enable Actions write permission

Settings → Actions → General → Workflow permissions → **Read and write**.

### 4 · Trigger first run

Actions → "Daily Data Engineer Job Feed" → Run workflow.

---

## Output location

Each run commits:
- `output/DataEngineerJobs_YYYY-MM-DD.xlsx` — the Excel for that day
- `data/seen.json` — dedup state (prevents reprinting the same jobs)
- `data/companies_discovered.json` — new companies found via Brave discovery

If you set `SMTP_USER/SMTP_PASS/EMAIL_TO`, the xlsx is also emailed to you.

---

## Local run

```bash
pip install -r requirements.txt
export JSEARCH_RAPIDAPI_KEY=...
export ADZUNA_APP_ID=... ADZUNA_APP_KEY=...
python -m jobfeed
```

## Run tests

```bash
pytest tests/ -v
```

---

## Adding more companies

Edit `companies.yaml` — add slugs under `greenhouse`, `lever`, `ashby` or `smartrecruiters`.

For Greenhouse: `https://boards.greenhouse.io/<slug>`  
For Lever: `https://jobs.lever.co/<slug>`  
For Ashby: `https://jobs.ashbyhq.com/<slug>`  

---

## Resume-prompt integration

The **careersLink for resume prompt** column feeds directly into the resume-tailoring JSON schema:

```
CAREERS LINK (C2C) OR RECRUITER EMAIL (W2): <value from that column>
HERE IS THE JOB DESCRIPTION: <Job Description column>
```

Profile (3yr / 5yr) maps to the `experienceLevel` field.
