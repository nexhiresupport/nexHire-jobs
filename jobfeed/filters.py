"""Role matching, US-location check, eligibility (clearance/citizenship) filter, and tagging."""
from __future__ import annotations

import re

from .models import Job

# ------------------------------------------------------------------ role match
def make_title_matcher(include: list[str], exclude: list[str]):
    inc = [k.lower() for k in include]
    exc = [k.lower() for k in exclude]

    def match(title: str) -> bool:
        t = f" {title.lower()} "
        return any(k in t for k in inc) and not any(k in t for k in exc)
    return match


# ------------------------------------------------------------------ US location
US_STATES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california", "CO": "colorado",
    "CT": "connecticut", "DE": "delaware", "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
    "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas", "KY": "kentucky", "LA": "louisiana",
    "ME": "maine", "MD": "maryland", "MA": "massachusetts", "MI": "michigan", "MN": "minnesota",
    "MS": "mississippi", "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new hampshire", "NJ": "new jersey", "NM": "new mexico", "NY": "new york", "NC": "north carolina",
    "ND": "north dakota", "OH": "ohio", "OK": "oklahoma", "OR": "oregon", "PA": "pennsylvania",
    "RI": "rhode island", "SC": "south carolina", "SD": "south dakota", "TN": "tennessee", "TX": "texas",
    "UT": "utah", "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west virginia",
    "WI": "wisconsin", "WY": "wyoming", "DC": "district of columbia",
}
US_CITIES = ("san francisco", "seattle", "austin", "boston", "chicago", "los angeles", "denver", "atlanta",
             "dallas", "houston", "miami", "phoenix", "san jose", "san diego", "portland", "pittsburgh",
             "philadelphia", "charlotte", "raleigh", "nashville", "minneapolis", "detroit", "columbus",
             "indianapolis", "salt lake", "palo alto", "mountain view", "sunnyvale", "menlo park",
             "redwood city", "jersey city", "bay area", "nyc", "silicon valley", "st. louis", "kansas city")
US_TERMS = re.compile(r"\b(united states|usa|u\.s\.a?\.?|us|americas|north america)\b", re.I)
FOREIGN = re.compile(
    r"\b(canada|toronto|vancouver|montreal|ontario|india|bangalore|bengaluru|hyderabad|pune|chennai|"
    r"united kingdom|uk|london|england|ireland|dublin|germany|berlin|munich|france|paris|netherlands|"
    r"amsterdam|spain|madrid|barcelona|poland|warsaw|portugal|lisbon|mexico|brazil|são paulo|sao paulo|"
    r"argentina|colombia|singapore|japan|tokyo|australia|sydney|melbourne|israel|tel aviv|philippines|"
    r"emea|apac|latam|europe|switzerland|zurich|sweden|stockholm|romania|ukraine|serbia|costa rica)\b", re.I)
STATE_ABBR_RE = re.compile(r"(?:,|\b)\s*(" + "|".join(US_STATES) + r")\b")


def is_us_location(loc: str) -> bool:
    if not loc:
        return True  # unknown -> keep (aggregators already restricted to US)
    l = loc.lower()
    us = bool(US_TERMS.search(loc)) or any(n in l for n in US_STATES.values()) or any(c in l for c in US_CITIES) \
        or bool(STATE_ABBR_RE.search(loc))
    foreign = bool(FOREIGN.search(loc))
    if us:
        return True
    if foreign:
        return False
    return "remote" in l or "anywhere" in l


# ------------------------------------------------------------------ eligibility
NEGATION = re.compile(r"(no|not|without|n't|never|nor)\b[\w\s,/-]{0,25}$", re.I)

CLEARANCE_PATTERNS = [
    r"security\s+clearance", r"\bclearance\b[^.\n]{0,30}\brequired", r"\b(active|current)\s+(secret|top\s*secret|ts|clearance)",
    r"\bts\s*/\s*sci\b", r"\btop\s*secret\b", r"\bsecret\s+clearance", r"\bpublic\s+trust\b",
    r"\bpolygraph\b", r"\b(dod|doe|dhs)\s+clearance", r"\bq\s+clearance\b",
    r"(ability|able|eligib\w*)\s+to\s+obtain\s+(an?\s+)?(and\s+maintain\s+)?(a\s+)?(security\s+|government\s+)?clearance",
    r"\bcleared\s+(candidate|professional|engineer|position)s?\b",
]
CITIZEN_PATTERNS = [
    r"must\s+be\s+(an?\s+)?(u\.?\s?s\.?|united\s+states)\s+citizens?",
    r"(u\.?\s?s\.?|united\s+states)\s+citizens?\s+only",
    r"only\s+(u\.?\s?s\.?|united\s+states)\s+citizens?",
    r"(u\.?\s?s\.?|united\s+states)\s+citizenship\s+(is\s+)?(required|mandatory|needed)",
    r"requires?\s+(u\.?\s?s\.?|united\s+states)\s+citizenship",
    r"citizenship\s+(is\s+)?required",
    r"\busc\s*(/|or|and|,)\s*gc\b", r"\bgc\s*(/|or|and|,)\s*usc\b", r"\busc\s+only\b",
    r"\b(green\s*card|gc)\s+(holders?\s+)?only\b",
    r"only\s+(green\s*card|gc)\s+holders?",
    r"must\s+(be|hold)\s+(an?\s+)?(green\s*card(\s+holder)?|permanent\s+resident)",
    r"permanent\s+residents?\s+only",
    r"citizens?\s+(or|and|/)\s+(green\s*card\s+holders?|permanent\s+residents?|lawful\s+permanent)",
    r"(u\.?\s?s\.?|united\s+states)\s+citizens?\s+(or|and|/)\s+(gc|green\s*card)",
]
ITAR_PATTERNS = [
    r"\bitar\b", r"\bear\b\s*(controlled|regulations|restricted)", r"export\s+control\w*[^.\n]{0,80}(u\.?\s?s\.?\s+person|citizen)",
    r"(u\.?\s?s\.?|united\s+states)\s+persons?\b[^.\n]{0,40}(required|only|as\s+defined)",
    r"must\s+(be|qualify\s+as)\s+an?\s+(u\.?\s?s\.?|united\s+states)\s+person",
]
NO_SPONSOR_PATTERNS = [
    r"(unable|not\s+able)\s+to\s+(provide\s+)?sponsor", r"(will|can|do(es)?)\s*not\s+(provide\s+)?sponsor",
    r"(won't|cannot|can't)\s+(provide\s+)?sponsor", r"no\s+(visa\s+|h-?1b\s+)?sponsorship",
    r"sponsorship\s+(is\s+)?not\s+(available|provided|offered)",
    r"without\s+(the\s+)?(need\s+for\s+)?(current\s+or\s+future\s+)?(visa\s+|employer\s+)?sponsorship",
    r"not\s+eligible\s+for\s+(visa\s+)?sponsorship", r"\bno\s+h-?1b\b", r"\bno\s+(opt|cpt|ead)\b",
]
# Phrases that mean "citizen OR work authorization" (not citizen-only) - suppress a citizen hit
CITIZEN_ESCAPE = re.compile(r"^[^.\n]{0,50}(authoriz|eligible\s+to\s+work|work\s+permit|visa|ead|h-?1b|opt)", re.I)

_compiled = {
    "clearance": [re.compile(p, re.I) for p in CLEARANCE_PATTERNS],
    "citizen": [re.compile(p, re.I) for p in CITIZEN_PATTERNS],
    "itar": [re.compile(p, re.I) for p in ITAR_PATTERNS],
    "nosponsor": [re.compile(p, re.I) for p in NO_SPONSOR_PATTERNS],
}


def _find(kind: str, text: str) -> str | None:
    for rx in _compiled[kind]:
        for m in rx.finditer(text):
            before = text[max(0, m.start() - 40):m.start()]
            if NEGATION.search(before):
                continue  # e.g. "no security clearance required"
            if kind == "citizen" and CITIZEN_ESCAPE.search(text[m.end():m.end() + 80]):
                continue  # e.g. "must be a US citizen or authorized to work"
            return text[max(0, m.start() - 30):m.end() + 30].replace("\n", " ").strip()
    return None


def check_eligibility(job: Job, cfg: dict) -> str | None:
    """Returns an exclusion reason or None. Also sets job.sponsorship_note."""
    text = f"{job.title}\n{job.description}"
    if cfg.get("exclude_clearance", True) and (hit := _find("clearance", text)):
        return f"Security clearance: …{hit}…"
    if cfg.get("exclude_citizenship_only", True) and (hit := _find("citizen", text)):
        return f"Citizens / green card only: …{hit}…"
    if cfg.get("exclude_itar_us_person", True) and (hit := _find("itar", text)):
        return f"ITAR / U.S. person: …{hit}…"
    if hit := _find("nosponsor", text):
        job.sponsorship_note = "No sponsorship"
        if cfg.get("exclude_no_sponsorship", False):
            return f"No visa sponsorship: …{hit}…"
    elif re.search(r"(h-?1b|visa)\s+(transfer|sponsorship)\s+(available|provided|offered|ok)|will\s+sponsor|"
                   r"sponsorship\s+(is\s+)?available", text, re.I):
        job.sponsorship_note = "Sponsorship mentioned as available"
    return None


# ------------------------------------------------------------------ tagging
def classify_employment(job: Job) -> str:
    hint = job.employment_hint.lower()
    text = f"{job.title}\n{job.description}".lower()
    no_c2c = re.search(r"no\s+c2c|not\s+(open\s+to\s+|accepting\s+)?c2c|w-?2\s+only|only\s+w-?2|no\s+corp[\s-]to[\s-]corp", text)
    c2c = re.search(r"\bc2c\b|corp[\s-]to[\s-]corp|\b1099\b", text)
    w2 = re.search(r"\bw-?2\b", text)
    contract = ("contract" in hint or "contractor" in hint or "temporary" in hint or "temp" == hint
                or re.search(r"\bcontract(or)?\b|\bduration\b[^.\n]{0,20}\bmonths?\b|\bcontract[\s-]to[\s-]hire\b", text))
    if c2c and not no_c2c:
        return "C2C / Contract"
    if contract or w2:
        if w2 or no_c2c:
            return "W2 Contract"
        if "contract-to-hire" in text or "contract to hire" in text:
            return "Contract-to-hire"
        return "Contract"
    if "part" in hint and "time" in hint or "parttime" in hint:
        return "Part-time"
    if "intern" in hint:
        return "Internship"
    return "Full-time"


def classify_work_type(job: Job) -> str:
    hint = (job.remote_hint or "").lower()
    loc = job.location.lower()
    text = job.description.lower()[:4000]
    if "hybrid" in hint or "hybrid" in loc:
        return "hybrid"
    if "remote" in hint or "remote" in loc:
        return "remote"
    if "onsite" in hint or "on-site" in hint or "on site" in hint:
        return "on-site"
    if re.search(r"\bhybrid\b", text):
        return "hybrid"
    if re.search(r"\b(fully|100%)\s+remote\b|\bremote[\s-]first\b|\bthis (role|position) is remote\b", text):
        return "remote"
    if re.search(r"\bon[\s-]?site\b|\bin[\s-]office\b|\b(5|five) days (a|per) week in", text):
        return "on-site"
    return "unspecified"


EXP_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|to)?\s*(?:\d{1,2})?\s*\+?\s*years?(?:'|’)?\s*(?:of\s+)?(?:[\w/,&\-]+\s+){0,6}?experience",
    re.I)


def extract_experience(job: Job) -> int | None:
    vals = [int(m.group(1)) for m in EXP_RE.finditer(job.description)]
    vals = [v for v in vals if 0 < v <= 20]
    return min(vals) if vals else None


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IGNORE_EMAIL = re.compile(r"(accommodat|privacy|noreply|no-reply|donotreply|ada@|eeo|benefits|careers-support|example\.)", re.I)


def extract_recruiter_email(job: Job) -> str:
    for e in EMAIL_RE.findall(job.description):
        if not IGNORE_EMAIL.search(e):
            return e.rstrip(".")
    return ""


def add_flags(job: Job, staffing_keywords: list[str]) -> None:
    c = job.company.lower()
    if any(k in c for k in staffing_keywords):
        job.flags.append("Possible staffing agency")
    if job.via_job_board:
        if (job.publisher or "").lower().startswith("linkedin"):
            job.flags.append("LinkedIn only (may be Easy Apply)")
        else:
            job.flags.append(f"Job-board link only ({job.publisher or 'board'})")
    if not job.description_complete:
        job.flags.append("JD is a snippet - check clearance/citizenship manually")
    if re.search(r"\b(repost|re-?posted|evergreen|talent\s+(pool|community|network))\b",
                 f"{job.title} {job.description[:1500]}", re.I):
        job.flags.append("Evergreen / talent pool")


def suggested_profile(years: int | None) -> str:
    if years is None:
        return ""
    return "3yr" if years <= 3 else "5yr"
