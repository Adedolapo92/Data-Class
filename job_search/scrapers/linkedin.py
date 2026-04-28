"""LinkedIn job search scraper using the public jobs search page."""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

# Public job search — no login required
SEARCH_URL = "https://www.linkedin.com/jobs/search/"
GUEST_API_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

log = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }
)

_session_warmed = False


def _warm_session() -> None:
    global _session_warmed
    if _session_warmed:
        return
    try:
        SESSION.get("https://www.linkedin.com/", timeout=10)
        _session_warmed = True
        time.sleep(2)
    except requests.RequestException:
        pass


def fetch_jobs(
    keyword: str,
    location: str = "United States",
    remote_only: bool = True,
    max_results: int = 25,
) -> list[dict[str, Any]]:
    """Scrape LinkedIn public jobs search for *keyword* + *location*."""
    _warm_session()
    time.sleep(3)

    params: dict[str, Any] = {
        "keywords": keyword,
        "location": location,
        "f_TPR": "r86400",   # last 24 hours
    }
    if remote_only:
        params["f_WT"] = 2

    jobs = _try_guest_api(params, max_results) or _try_public_search(params)
    log.info("LinkedIn: %d jobs for keyword=%s location=%s", len(jobs), keyword, location)
    return jobs


def _try_guest_api(params: dict, max_results: int) -> list[dict[str, Any]] | None:
    """Try the guest API endpoint first."""
    search_params = {**params, "start": 0, "count": max_results}
    try:
        resp = SESSION.get(
            GUEST_API_URL,
            params=search_params,
            headers={"Referer": "https://www.linkedin.com/jobs/search/"},
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.debug("LinkedIn guest API failed: %s", exc)
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    jobs = _parse_cards(soup)
    return jobs if jobs else None


def _try_public_search(params: dict) -> list[dict[str, Any]]:
    """Fallback: scrape the public /jobs/search/ page."""
    try:
        resp = SESSION.get(
            SEARCH_URL,
            params=params,
            headers={"Referer": "https://www.linkedin.com/"},
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.debug("LinkedIn public search failed: %s", exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    return _parse_cards(soup)


def _parse_cards(soup: BeautifulSoup) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []

    # Try multiple known card selectors (LinkedIn changes these periodically)
    selectors = [
        "li[data-occludable-job-id]",
        "div.job-search-card",
        "li.jobs-search-results__list-item",
        "div.base-card",
    ]

    cards = []
    for sel in selectors:
        cards = soup.select(sel)
        if cards:
            break

    # Last resort: any <li> with a recognisable job link
    if not cards:
        cards = [
            li for li in soup.find_all("li")
            if li.find("a", href=re.compile(r"/jobs/view/\d+"))
        ]

    for card in cards:
        job_id = (
            card.get("data-occludable-job-id")
            or card.get("data-job-id")
            or _extract_job_id_from_card(card)
        )
        if not job_id:
            continue

        title = _text(card, [
            ".base-search-card__title",
            "h3.job-search-card__title",
            "h3",
            ".job-title",
        ])
        company = _text(card, [
            ".base-search-card__subtitle",
            "h4.job-search-card__company-name",
            "h4",
            ".company-name",
        ])
        location = _text(card, [
            ".job-search-card__location",
            ".job-search-card__location",
            "span.job-result-card__location",
            ".location",
        ])
        link_tag = card.find("a", href=re.compile(r"/jobs/view/\d+"))
        url = link_tag["href"].split("?")[0] if link_tag else ""

        if not title:
            continue

        jobs.append(
            {
                "id": f"linkedin_{job_id}",
                "source": "LinkedIn",
                "company": company,
                "title": title,
                "location": location,
                "url": url,
                "description": "",   # detail fetch skipped to avoid rate limits
                "salary_text": "",
            }
        )

    return jobs


def _text(card, selectors: list[str]) -> str:
    for sel in selectors:
        tag = card.select_one(sel)
        if tag:
            return tag.get_text(strip=True)
    return ""


def _extract_job_id_from_card(card) -> str:
    link = card.find("a", href=re.compile(r"/jobs/view/(\d+)"))
    if link:
        m = re.search(r"/jobs/view/(\d+)", link["href"])
        if m:
            return m.group(1)
    for attr in ("data-entity-urn", "data-job-id"):
        val = card.get(attr, "")
        if val:
            m = re.search(r"\d{5,}", val)
            if m:
                return m.group(0)
    return ""
