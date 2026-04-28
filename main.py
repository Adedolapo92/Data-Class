#!/usr/bin/env python3
"""
Job Search Pipeline — entry point.

Usage:
  python main.py             # run once immediately
  python main.py --schedule  # run now and then daily at 08:00
  python main.py --dry-run   # run pipeline but skip file writes and email
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import schedule

from job_search.pipeline import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("job_search.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


def _run_pipeline(dry_run: bool = False) -> None:
    log.info("─── Pipeline starting ───────────────────────────────────────────")
    try:
        jobs = run(dry_run=dry_run)
        log.info("─── Pipeline complete — %d roles found after filtering ──────", len(jobs))
    except Exception as exc:
        log.exception("Pipeline failed with an unhandled error: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Automated job search pipeline")
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Keep running and execute the pipeline daily at 08:00",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the pipeline but skip file writes and email",
    )
    args = parser.parse_args()

    if args.schedule:
        log.info("Scheduler mode: running now, then every day at 08:00")
        _run_pipeline(dry_run=args.dry_run)
        schedule.every().day.at("08:00").do(_run_pipeline, dry_run=args.dry_run)
        while True:
            schedule.run_pending()
            time.sleep(30)
    else:
        _run_pipeline(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
