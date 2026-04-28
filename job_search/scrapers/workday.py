"""Workday jobs API scraper.

Workday exposes a REST endpoint at:
  POST https://{tenant}.wd5.myworkdayjobs.com/wday/cxs/{tenant}/{site_id}/jobs
Some tenants use wd1/wd2/wd3 instead of wd5; we try each in sequence.
"""

import logging
import re
import time
from typing import Any

import requests

WORKDAY_VERSIONS = ["wd5", "wd3", "wd1"]
SEARCH_PATH = "wday/cxs/{tenant}/{site_id}/jobs"
PAGE_SIZE = 20

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
        "Content-Type": "application/json",
        "X-Workday-Client": "2023.43.8",
    }
)


def _base_url(tenant: str, version: str) -> str:
    return f"https://{tenant}.{version}.myworkdayjobs.com"


def _post(url: str, body: dict, tenant: str) -> dict | None:
    try:
        resp = SESSION.post(
            url,
            json=body,
            headers={"Referer": f"https://{tenant}.wd5.myworkdayjobs.com/"},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        log.debug("Workday POST failed %s: %s", url, exc)
        return None


def fetch_jobs(
    tenant: str,
    site_id: str,
    company_name: str,
    search_text: str = "",
) -> list[dict[str, Any]]:
    """Return normalised job dicts from a Workday board."""
    path = SEARCH_PATH.format(tenant=tenant, site_id=site_id)
    body = {"searchText": search_text, "limit": PAGE_SIZE, "offset": 0}

    base = None
    data = None
    for version in WORKDAY_VERSIONS:
        url = f"{_base_url(tenant, version)}/{path}"
        data = _post(url, body, tenant)
        if data is not None:
            base = _base_url(tenant, version)
            break

    if data is None:
        log.info("Workday: could not reach board for tenant=%s", tenant)
        return []

    postings = data.get("jobPostings") or []
    total = data.get("total", len(postings))

    offset = PAGE_SIZE
    while offset < total and len(postings) < 200:
        body["offset"] = offset
        more = _post(f"{base}/{path}", body, tenant)
        if not more:
            break
        batch = more.get("jobPostings") or []
        if not batch:
            break
        postings.extend(batch)
        offset += PAGE_SIZE
        time.sleep(0.3)

    jobs: list[dict[str, Any]] = []
    for raw in postings:
        ext_path = raw.get("externalPath", "").strip("/")
        job_id = ext_path.split("/")[-1] if ext_path else raw.get("title", "")
        job_url = f"{base}/{ext_path}" if ext_path else ""

        loc_tag = raw.get("locationsText") or raw.get("primaryLocation") or ""
        if isinstance(loc_tag, dict):
            loc_tag = loc_tag.get("descriptor", "")

        jobs.append(
            {
                "id": f"workday_{tenant}_{job_id}",
                "source": "Workday",
                "company": company_name,
                "title": raw.get("title", ""),
                "location": loc_tag,
                "url": job_url,
                "description": raw.get("jobDescription") or raw.get("briefDescription") or "",
                "salary_text": _extract_salary_text(raw),
            }
        )

    log.info("Workday: %d jobs for %s (tenant=%s)", len(jobs), company_name, tenant)
    return jobs


def _extract_salary_text(raw: dict) -> str:
    for key in ("salaryRange", "compensation", "pay"):
        val = raw.get(key)
        if val:
            return str(val) if not isinstance(val, dict) else val.get("descriptor", "")
    text = raw.get("jobDescription") or raw.get("briefDescription") or ""
    m = re.search(
        r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:\s*/?\s*(?:yr|year|annual|k))?",
        text,
        re.IGNORECASE,
    )
    return m.group(0) if m else ""
