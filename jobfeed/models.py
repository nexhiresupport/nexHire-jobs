from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Job:
    source: str                     # greenhouse, lever, ashby, adzuna, jsearch, workday, discovery...
    source_id: str
    title: str
    company: str
    location: str = ""
    url: str = ""                   # best "careers link" (direct employer page preferred)
    description: str = ""
    posted_at: datetime | None = None
    employment_hint: str = ""       # structured employment type from the source, if any
    remote_hint: str = ""           # structured remote/hybrid/onsite from the source, if any
    via_job_board: bool = False     # True when the only link is a job board (LinkedIn/Indeed/...)
    publisher: str = ""             # e.g. LinkedIn, Indeed (aggregators only)
    description_complete: bool = True

    # Filled in by filters / validation
    work_type: str = ""
    employment_type: str = ""
    experience_years: int | None = None
    recruiter_email: str = ""
    sponsorship_note: str = ""
    flags: list[str] = field(default_factory=list)
    link_status: str = ""
    exclude_reason: str = ""

    def dedupe_key(self) -> str:
        return "|".join(
            re.sub(r"[^a-z0-9]", "", s.lower()) for s in (self.company, self.title, self.location)
        )

    def state_key(self) -> str:
        return f"{self.source}:{self.source_id}"


TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t\r\f\v]+")


def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)               # Greenhouse double-escapes its HTML
    s = re.sub(r"(?i)<\s*(br|/p|/li|/div|/h\d)\s*/?>", "\n", s)
    s = re.sub(r"(?i)<\s*li[^>]*>", "\n- ", s)
    s = TAG_RE.sub("", s)
    s = html.unescape(s)
    s = WS_RE.sub(" ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


def parse_dt(value) -> datetime | None:
    """Accepts ISO strings, epoch seconds or epoch milliseconds."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            v = float(value)
            if v > 1e11:
                v /= 1000.0
            return datetime.fromtimestamp(v, tz=timezone.utc)
        s = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None
