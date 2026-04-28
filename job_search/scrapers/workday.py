"""Workday jobs API scraper.

Workday exposes a private-but-consistent REST endpoint at:
  POST https://{tenant}.wd5.myworkdayjobs.com/wday/cxs/{tenant}/{site_id}/jobs
with a JSON body of {"searchText": "", "limit": N, "offset": 0}.
Some tenants use wd1/wd2/wd3 instead of wd5; we try each in sequence.
"""

import logging
import re
import time
from typing import Any

import requests

WORKDAY_VERSIONS = ["wd5", "wd3", "wd1"]
SEARCH_PATH = "wday/cxs/{tenant}/{site_id}/jobs"
JOB_DETAIL_PATH = "wday/cxs/{tenant}/{site_id}/jobs/{job_id}"
PAGE_SIZE = 20

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}

log = logging.getLogger(__name__)


def _post(url: str, body: dict) -> dict | None:
    try:
        resp = requests.post(url, json=body, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        log.debug("Workday POST failed %s: %s", url, exc)
        return None


def _base_url(tenant: str, version: str) -> str:
    return f"https://{tenant}.{version}.myworkdayjobs.com"


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
        data = _post(url, body)
        if data is not None:
            base = _base_url(tenant, version)
            break

    if data is None:
        log.info("Workday: could not reach board for tenant=%s", tenant)
        return []

    postings = data.get("jobPostings") or []
    total = data.get("total", len(postings))

    # paginate
    offset = PAGE_SIZE
    while offset < total and len(postings) < 200:
        body["offset"] = offset
        more = _post(f"{base}/{path}", body)
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
        ext_id = raw.get("externalPath", "").strip("/").split("/")[-1]
        job_url = f"{base}/{SEARCH_PATH.format(tenant=tenant, site_id=site_id)}/{ext_id}" if ext_id else ""
        loc_tag = raw.get("locationsText") or raw.get("primaryLocation") or ""
        if isinstance(loc_tag, dict):
            loc_tag = loc_tag.get("descriptor", "")

        salary_text = _extract_salary_text(raw)

        jobs.append(
            {
                "id": f"workday_{tenant}_{ext_id or raw.get('title', '')}",
                "source": "Workday",
                "company": company_name,
                "title": raw.get("title", ""),
                "location": loc_tag,
                "url": job_url,
                "description": raw.get("jobDescription") or raw.get("briefDescription") or "",
                "salary_text": salary_text,
            }
        )

    log.info("Workday: %d jobs fetched for %s (tenant=%s)", len(jobs), company_name, tenant)
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
