"""Core pipeline: scrape → filter → score → deduplicate → output → email."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from job_search.filters import apply_filters
from job_search.output import write_markdown
from job_search.email_digest import send_digest
from job_search.scorer import score_job
from job_search.tracker import JobTracker
from job_search.scrapers import greenhouse, lever, linkedin, workday, ashby

log = logging.getLogger(__name__)


def load_config(path: str | Path = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _scrape_all(cfg: dict) -> list[dict[str, Any]]:
    """Run all scrapers and return the combined raw job list."""
    raw: list[dict[str, Any]] = []

    # Greenhouse
    for company in cfg.get("companies", {}).get("greenhouse", []):
        try:
            raw.extend(greenhouse.fetch_jobs(company))
        except Exception as exc:
            log.error("Greenhouse scraper failed for %s: %s", company, exc)

    # Lever
    for company in cfg.get("companies", {}).get("lever", []):
        try:
            raw.extend(lever.fetch_jobs(company))
        except Exception as exc:
            log.error("Lever scraper failed for %s: %s", company, exc)

    # Workday
    for board in cfg.get("companies", {}).get("workday", []):
        try:
            raw.extend(
                workday.fetch_jobs(
                    tenant=board["tenant"],
                    site_id=board.get("site_id", "External"),
                    company_name=board["name"],
                )
            )
        except Exception as exc:
            log.error("Workday scraper failed for %s: %s", board.get("name"), exc)

    # Ashby
    for slug in cfg.get("companies", {}).get("ashby", []):
        try:
            raw.extend(ashby.fetch_jobs(slug))
        except Exception as exc:
            log.error("Ashby scraper failed for %s: %s", slug, exc)

    # LinkedIn
    li_cfg = cfg.get("linkedin_searches", {})
    remote_only = li_cfg.get("remote_filter", True)
    for keyword in li_cfg.get("keywords", []):
        for location in li_cfg.get("locations", ["United States"]):
            try:
                raw.extend(linkedin.fetch_jobs(keyword, location, remote_only=remote_only))
            except Exception as exc:
                log.error("LinkedIn scraper failed (kw=%s, loc=%s): %s", keyword, location, exc)

    log.info("Total raw jobs scraped: %d", len(raw))
    return raw


def _dedup_within_run(jobs: list[dict]) -> list[dict]:
    """Remove duplicates within the current batch by job ID."""
    seen: set[str] = set()
    unique: list[dict] = []
    for job in jobs:
        if job["id"] not in seen:
            seen.add(job["id"])
            unique.append(job)
    return unique


def run(config_path: str | Path = "config.yaml", dry_run: bool = False) -> list[dict[str, Any]]:
    """
    Execute the full pipeline.
    Returns the list of scored, filtered, new jobs (for testing / inspection).
    dry_run=True skips writing files and sending email.
    """
    cfg = load_config(config_path)

    tracker = JobTracker(cfg["output"]["seen_jobs_file"])

    # 1. Scrape
    raw_jobs = _scrape_all(cfg)

    # 2. Deduplicate within run
    raw_jobs = _dedup_within_run(raw_jobs)

    # 3. Drop already-seen jobs
    new_jobs = tracker.filter_new(raw_jobs)
    log.info("New jobs (not seen before): %d / %d", len(new_jobs), len(raw_jobs))

    # 4. Filter (title / location / salary)
    filtered: list[dict[str, Any]] = []
    for job in new_jobs:
        result = apply_filters(job, cfg)
        if result is not None:
            filtered.append(result)
    log.info("Jobs passing filters: %d / %d", len(filtered), len(new_jobs))

    # 5. Score
    for job in filtered:
        score, note = score_job(job, cfg)
        job["fit_score"] = score
        job["fit_note"] = note

    # 6. Mark all scraped-and-new as seen (even those filtered out — avoids re-processing)
    tracker.add_all(new_jobs)

    if not dry_run:
        tracker.save()

        # 7. Write markdown
        write_markdown(filtered, cfg["output"]["results_dir"])

        # 8. Email digest (only roles >= min_score_to_email)
        min_score = cfg.get("email", {}).get("min_score_to_email", 7)
        high_scoring = [j for j in filtered if j.get("fit_score", 0) >= min_score]
        send_digest(high_scoring, cfg)

    return filtered
