"""Greenhouse public jobs-board API scraper."""

from __future__ import annotations

import logging
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
BOARD_URL = "https://boards.greenhouse.io/{company}"

log = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
)


def _get_json(url: str, company: str) -> dict | None:
    """Try the JSON API with a spoofed Referer."""
    try:
        resp = SESSION.get(
            url,
            params={"content": "true"},
            headers={"Referer": BOARD_URL.format(company=company)},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        log.debug("Greenhouse JSON API failed for %s: %s", company, exc)
        return None


def _scrape_html(company: str) -> list[dict[str, Any]]:
    """Fallback: scrape the public HTML board page."""
    url = BOARD_URL.format(company=company)
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Greenhouse HTML fallback failed for %s: %s", company, exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    jobs: list[dict[str, Any]] = []

    for section in soup.select("section.level-0"):
        dept = section.select_one("h3")
        dept_name = dept.get_text(strip=True) if dept else ""
        for row in section.select("div.opening"):
            a = row.select_one("a")
            if not a:
                continue
            loc = row.select_one("span.location")
            jobs.append(
                {
                    "id": f"greenhouse_{company}_{a['href'].split('/')[-1]}",
                    "source": "Greenhouse",
                    "company": company.replace("-", " ").title(),
                    "title": a.get_text(strip=True),
                    "location": loc.get_text(strip=True) if loc else "",
                    "url": f"https://boards.greenhouse.io{a['href']}" if a["href"].startswith("/") else a["href"],
                    "description": dept_name,
                    "salary_text": "",
                }
            )
    return jobs


def fetch_jobs(company: str) -> list[dict[str, Any]]:
    """Return normalised job dicts for *company* from the Greenhouse board."""
    data = _get_json(BASE_URL.format(company=company), company)

    if data and "jobs" in data:
        jobs = []
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
        log.info("Greenhouse API: %d jobs for %s", len(jobs), company)
        return jobs

    # API blocked — fall back to HTML scrape
    jobs = _scrape_html(company)
    log.info("Greenhouse HTML: %d jobs for %s", len(jobs), company)
    return jobs


def _company_display(raw: dict, slug: str) -> str:
    dept = raw.get("departments")
    if dept and isinstance(dept, list) and dept[0].get("name"):
        return dept[0]["name"]
    return slug.replace("-", " ").title()


def _extract_salary_text(raw: dict) -> str:
    for meta in raw.get("metadata", []):
        name = (meta.get("name") or "").lower()
        if any(k in name for k in ("salary", "compensation", "pay", "wage")):
            value = meta.get("value")
            if value:
                return str(value)
    content: str = raw.get("content", "")
    match = re.search(
        r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:\s*/?\s*(?:yr|year|annual|k))?",
        content,
        re.IGNORECASE,
    )
    return match.group(0) if match else ""
