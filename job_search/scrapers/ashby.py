"""Ashby HQ public job board API scraper.

Ashby is used by many modern tech companies (OpenAI, Anthropic, Linear,
Notion, etc.) that don't appear on Greenhouse or Lever.

Public API: GET https://api.ashbyhq.com/posting-api/job-board/{slug}
Returns JSON with a `jobPostings` array — no auth required.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
JOB_URL = "https://jobs.ashbyhq.com/{slug}/{job_id}"

log = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }
)


def fetch_jobs(slug: str) -> list[dict[str, Any]]:
    """Return normalised job dicts for *slug* from the Ashby board API."""
    try:
        resp = SESSION.get(
            BASE_URL.format(slug=slug),
            params={"includeCompensation": "true"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        log.warning("Ashby request failed for %s: %s", slug, exc)
        return []
    except ValueError as exc:
        log.warning("Ashby JSON decode failed for %s: %s", slug, exc)
        return []

    postings = data.get("jobPostings") or []
    jobs: list[dict[str, Any]] = []

    for raw in postings:
        location = _extract_location(raw)
        salary_text = _extract_salary(raw)
        description = raw.get("descriptionPlain") or _strip_html(raw.get("descriptionHtml") or "")
        job_id = raw.get("id", "")
        url = raw.get("applyUrl") or raw.get("jobUrl") or JOB_URL.format(slug=slug, job_id=job_id)

        jobs.append(
            {
                "id": f"ashby_{slug}_{job_id}",
                "source": "Ashby",
                "company": data.get("name") or slug.replace("-", " ").title(),
                "title": raw.get("title", ""),
                "location": location,
                "url": url,
                "description": description,
                "salary_text": salary_text,
            }
        )

    log.info("Ashby: %d jobs for %s", len(jobs), slug)
    return jobs


def _extract_location(raw: dict) -> str:
    """Best-effort location string from an Ashby posting."""
    # Prefer explicit locationName; fall back to isRemote flag
    loc = raw.get("locationName") or raw.get("location") or ""
    if isinstance(loc, dict):
        loc = loc.get("name") or loc.get("locationName") or ""
    if not loc and raw.get("isRemote"):
        loc = "Remote"
    return loc


def _extract_salary(raw: dict) -> str:
    comp = raw.get("compensation") or {}
    # Top-level summary string
    summary = comp.get("compensationTierSummary") or comp.get("summary") or ""
    if summary:
        return summary

    # Components list
    for component in comp.get("summaryComponents") or []:
        label = component.get("label") or ""
        value = component.get("value") or ""
        if value and any(k in label.lower() for k in ("salary", "base", "compensation", "pay")):
            return str(value)

    # Fallback: scan description for a dollar figure
    text = raw.get("descriptionPlain") or ""
    m = re.search(
        r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:\s*/?\s*(?:yr|year|annual|k))?",
        text,
        re.IGNORECASE,
    )
    return m.group(0) if m else ""


def _strip_html(html: str) -> str:
    """Very light HTML tag stripper — avoids importing bs4 just for this."""
    return re.sub(r"<[^>]+>", " ", html).strip()
