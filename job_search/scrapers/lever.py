"""Lever public postings API scraper."""

import logging
import re
from typing import Any

import requests

BASE_URL = "https://api.lever.co/v0/postings/{company}"

log = logging.getLogger(__name__)


def _get(url: str, params: dict | None = None) -> list | None:
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        log.warning("Lever request failed %s: %s", url, exc)
        return None


def fetch_jobs(company: str) -> list[dict[str, Any]]:
    """Return normalised job dicts for *company* from the Lever postings API."""
    data = _get(BASE_URL.format(company=company), params={"mode": "json"})
    if not data:
        log.info("Lever: no jobs found for %s", company)
        return []

    jobs: list[dict[str, Any]] = []
    for raw in data:
        cats = raw.get("categories", {}) or {}
        location = cats.get("location") or cats.get("allLocations", [""])[0] if isinstance(cats.get("allLocations"), list) else ""

        description = _build_description(raw)
        salary_text = _extract_salary_text(description)

        jobs.append(
            {
                "id": f"lever_{company}_{raw['id']}",
                "source": "Lever",
                "company": raw.get("company") or company.replace("-", " ").title(),
                "title": raw.get("text", ""),
                "location": location,
                "url": raw.get("hostedUrl", ""),
                "description": description,
                "salary_text": salary_text,
            }
        )

    log.info("Lever: %d jobs fetched for %s", len(jobs), company)
    return jobs


def _build_description(raw: dict) -> str:
    parts = [
        raw.get("descriptionPlain") or raw.get("description") or "",
        raw.get("additionalPlain") or raw.get("additional") or "",
    ]
    lists = raw.get("lists", [])
    for lst in lists:
        parts.append(lst.get("content", ""))
    return " ".join(filter(None, parts))


def _extract_salary_text(text: str) -> str:
    match = re.search(
        r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:\s*/?\s*(?:yr|year|annual|k))?",
        text,
        re.IGNORECASE,
    )
    return match.group(0) if match else ""
