"""Lever public postings scraper — API with HTML fallback."""

import logging
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

API_URL = "https://api.lever.co/v0/postings/{company}"
BOARD_URL = "https://jobs.lever.co/{company}"

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
        "Connection": "keep-alive",
    }
)


def _get_json(company: str) -> list | None:
    try:
        resp = SESSION.get(
            API_URL.format(company=company),
            params={"mode": "json"},
            headers={
                "Origin": "https://jobs.lever.co",
                "Referer": BOARD_URL.format(company=company),
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        log.debug("Lever API failed for %s: %s", company, exc)
        return None


def _scrape_html(company: str) -> list[dict[str, Any]]:
    """Fallback: parse the public jobs.lever.co board page."""
    url = BOARD_URL.format(company=company)
    try:
        resp = SESSION.get(url, headers={"Referer": "https://www.google.com/"}, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Lever HTML fallback failed for %s: %s", company, exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    jobs: list[dict[str, Any]] = []

    for posting in soup.select("div.posting"):
        title_tag = posting.select_one("h5")
        link_tag = posting.select_one("a.posting-title")
        loc_tag = posting.select_one("span.sort-by-location") or posting.select_one(".location")
        if not title_tag or not link_tag:
            continue
        href = link_tag.get("href", "")
        job_id = href.rstrip("/").split("/")[-1]
        jobs.append(
            {
                "id": f"lever_{company}_{job_id}",
                "source": "Lever",
                "company": company.replace("-", " ").title(),
                "title": title_tag.get_text(strip=True),
                "location": loc_tag.get_text(strip=True) if loc_tag else "",
                "url": href,
                "description": "",
                "salary_text": "",
            }
        )
    return jobs


def fetch_jobs(company: str) -> list[dict[str, Any]]:
    """Return normalised job dicts for *company* from Lever."""
    data = _get_json(company)

    if data is not None:
        jobs = []
        for raw in data:
            cats = raw.get("categories", {}) or {}
            loc_list = cats.get("allLocations") or []
            location = cats.get("location") or (loc_list[0] if loc_list else "")
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
        log.info("Lever API: %d jobs for %s", len(jobs), company)
        return jobs

    jobs = _scrape_html(company)
    log.info("Lever HTML: %d jobs for %s", len(jobs), company)
    return jobs


def _build_description(raw: dict) -> str:
    parts = [
        raw.get("descriptionPlain") or raw.get("description") or "",
        raw.get("additionalPlain") or raw.get("additional") or "",
    ]
    for lst in raw.get("lists", []):
        parts.append(lst.get("content", ""))
    return " ".join(filter(None, parts))


def _extract_salary_text(text: str) -> str:
    match = re.search(
        r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:\s*/?\s*(?:yr|year|annual|k))?",
        text,
        re.IGNORECASE,
    )
    return match.group(0) if match else ""
