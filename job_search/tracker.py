"""Persistent deduplication tracker backed by a local JSON file."""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class JobTracker:
    def __init__(self, filepath: str | Path):
        self.path = Path(filepath)
        self._seen: set[str] = self._load()

    # ── Public API ─────────────────────────────────────────────────────────────

    def is_new(self, job_id: str) -> bool:
        return job_id not in self._seen

    def mark_seen(self, job_id: str) -> None:
        self._seen.add(job_id)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(sorted(self._seen), fh, indent=2)
        log.debug("Tracker saved %d seen job IDs to %s", len(self._seen), self.path)

    def filter_new(self, jobs: list[dict]) -> list[dict]:
        """Return only jobs whose IDs have not been seen before."""
        return [j for j in jobs if self.is_new(j["id"])]

    def add_all(self, jobs: list[dict]) -> None:
        for job in jobs:
            self.mark_seen(job["id"])

    # ── Internal ───────────────────────────────────────────────────────────────

    def _load(self) -> set[str]:
        if not self.path.exists():
            return set()
        try:
            with self.path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            return set(data) if isinstance(data, list) else set()
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not load tracker file %s: %s", self.path, exc)
            return set()
