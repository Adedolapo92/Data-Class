"""LinkedIn job search scraper using the guest jobs API."""

import logging
import re
import time
from typing import Any
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

log = logging.getLogger(__name__)


def fetch_jobs(
    keyword: str,
    location: str = "United States",
    remote_only: bool = True,
    max_results: int = 25,
) -> list[dict[str, Any]]:
    """Scrape LinkedIn guest API for *keyword* + *location*."""
    params: dict[str, Any] = {
        "keywords": keyword,
        "location": location,
        "start": 0,
        "count": max_results,
    }
    if remote_only:
        params["f_WT"] = 2  # 2 = remote

    try:
        resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("LinkedIn search failed (keyword=%s): %s", keyword, exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    cards = soup.find_all("li")
    jobs: list[dict[str, Any]] = []

    for card in cards:
        job_id = card.get("data-occludable-job-id") or _extract_job_id(card)
        if not job_id:
            continue

        title_tag = card.find(class_="base-search-card__title")
        company_tag = card.find(class_="base-search-card__subtitle")
        location_tag = card.find(class_="job-search-card__location")
        link_tag = card.find("a", class_="base-card__full-link")

        title = title_tag.get_text(strip=True) if title_tag else ""
        company = company_tag.get_text(strip=True) if company_tag else ""
        location = location_tag.get_text(strip=True) if location_tag else ""
        url = link_tag["href"].split("?")[0] if link_tag else ""

        if not title:
            continue

        description, salary_text = _fetch_job_detail(job_id)
        time.sleep(0.5)  # be polite

        jobs.append(
            {
                "id": f"linkedin_{job_id}",
                "source": "LinkedIn",
                "company": company,
                "title": title,
                "location": location,
                "url": url,
                "description": description,
                "salary_text": salary_text,
            }
        )

    log.info("LinkedIn: %d jobs fetched for keyword=%s, location=%s", len(jobs), keyword, location)
    return jobs


def _extract_job_id(card) -> str:
    for attr in ("data-entity-urn", "data-job-id"):
        val = card.get(attr, "")
        if val:
            m = re.search(r"\d{5,}", val)
            if m:
                return m.group(0)
    link = card.find("a", href=True)
    if link:
        m = re.search(r"/(\d{5,})/?", link["href"])
        if m:
            return m.group(1)
    return ""


def _fetch_job_detail(job_id: str) -> tuple[str, str]:
    """Return (description_text, salary_text) for a single LinkedIn job."""
    try:
        resp = requests.get(DETAIL_URL.format(job_id=job_id), headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        desc_tag = soup.find(class_="show-more-less-html__markup")
        description = desc_tag.get_text(" ", strip=True) if desc_tag else ""

        salary_tag = soup.find(class_="compensation__salary") or soup.find(
            "span", string=re.compile(r"\$[\d,]+")
        )
        salary_text = ""
        if salary_tag:
            salary_text = salary_tag.get_text(strip=True)
        else:
            m = re.search(
                r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:\s*/?\s*(?:yr|year|annual|k))?",
                description,
                re.IGNORECASE,
            )
            salary_text = m.group(0) if m else ""

        return description, salary_text

    except requests.RequestException as exc:
        log.debug("LinkedIn detail fetch failed for job_id=%s: %s", job_id, exc)
        return "", ""
