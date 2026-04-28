"""Greenhouse public jobs-board API scraper."""

import logging
from typing import Any

import requests

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
DETAIL_URL = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}"

log = logging.getLogger(__name__)


def _get(url: str, params: dict | None = None) -> dict | list | None:
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        log.warning("Greenhouse request failed %s: %s", url, exc)
        return None


def fetch_jobs(company: str) -> list[dict[str, Any]]:
    """Return normalised job dicts for *company* from the Greenhouse board API."""
    data = _get(BASE_URL.format(company=company), params={"content": "true"})
    if not data or "jobs" not in data:
        log.info("Greenhouse: no jobs found for %s", company)
        return []

    jobs: list[dict[str, Any]] = []
    for raw in data["jobs"]:
        location = raw.get("location", {})
        loc_name = location.get("name", "") if isinstance(location, dict) else str(location)

        salary_text = _extract_salary_text(raw)

        jobs.append(
            {
                "id": f"greenhouse_{company}_{raw['id']}",
                "source": "Greenhouse",
                "company": _company_display(raw, company),
                "title": raw.get("title", ""),
                "location": loc_name,
                "url": raw.get("absolute_url", ""),
                "description": raw.get("content", ""),
                "salary_text": salary_text,
            }
        )

    log.info("Greenhouse: %d jobs fetched for %s", len(jobs), company)
    return jobs


def _company_display(raw: dict, slug: str) -> str:
    dept = raw.get("departments")
    if dept and isinstance(dept, list) and dept[0].get("name"):
        return dept[0]["name"]
    return slug.replace("-", " ").title()


def _extract_salary_text(raw: dict) -> str:
    """Pull salary text from the job's metadata or content field."""
    for meta in raw.get("metadata", []):
        name = (meta.get("name") or "").lower()
        if any(k in name for k in ("salary", "compensation", "pay", "wage")):
            value = meta.get("value")
            if value:
                return str(value)

    content: str = raw.get("content", "")
    import re
    match = re.search(
        r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:\s*/?\s*(?:yr|year|annual|k))?",
        content,
        re.IGNORECASE,
    )
    return match.group(0) if match else ""
