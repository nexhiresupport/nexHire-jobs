"""Brian's-Job-Search-style discovery: web search limited to company ATS sites, recent posts only.

Search results are used only to find posting URLs and new company boards. Job details are then
fetched from the employer's own ATS, so nothing from the search API itself is stored.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


def discovery_available() -> bool:
    return bool(os.getenv("BRAVE_API_KEY"))


def brave_freshness(lookback_hours: int, now_utc: datetime) -> str:
    if lookback_hours <= 25:
        return "pd"   # past day
    start = (now_utc - timedelta(hours=lookback_hours)).date()
    return f"{start.isoformat()}to{now_utc.date().isoformat()}"


def discover_urls(session, phrases: list[str], site_groups: list[str], lookback_hours: int,
                  now_utc: datetime, pages: int = 2) -> tuple[list[dict], int]:
    """Returns ([{url, title, snippet}], number_of_queries_used)."""
    headers = {"X-Subscription-Token": os.environ["BRAVE_API_KEY"], "Accept": "application/json"}
    fresh = brave_freshness(lookback_hours, now_utc)
    seen, out, used = set(), [], 0
    for phrase in phrases:
        for group in site_groups:
            for offset in range(pages):
                r = session.get(BRAVE_URL, headers=headers, timeout=30, params={
                    "q": f'"{phrase}" ({group})',
                    "count": 20, "offset": offset, "country": "us", "freshness": fresh,
                })
                used += 1
                r.raise_for_status()
                results = ((r.json().get("web") or {}).get("results")) or []
                for res in results:
                    u = res.get("url", "")
                    if u and u not in seen:
                        seen.add(u)
                        out.append({"url": u, "title": res.get("title", ""), "snippet": res.get("description", "")})
                if len(results) < 20:
                    break
    return out, used
