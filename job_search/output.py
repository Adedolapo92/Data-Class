"""Markdown output writer."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCORE_EMOJI = {
    range(9, 11): "🔥",
    range(7, 9):  "✅",
    range(5, 7):  "🟡",
    range(1, 5):  "🔴",
}


def _score_icon(score: int) -> str:
    for rng, icon in _SCORE_EMOJI.items():
        if score in rng:
            return icon
    return ""


def write_markdown(jobs: list[dict[str, Any]], results_dir: str | Path) -> Path:
    """Write all jobs to a dated markdown file. Returns the file path."""
    today = date.today().isoformat()
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)
    out_file = results_path / f"jobs_{today}.md"

    # Group by fit score (descending)
    sorted_jobs = sorted(jobs, key=lambda j: j.get("fit_score", 0), reverse=True)

    lines: list[str] = [
        f"# Job Search Results — {today}",
        "",
        f"**Total roles found:** {len(jobs)}",
        "",
        "---",
        "",
    ]

    if not jobs:
        lines.append("_No new roles matching your criteria today._")
    else:
        for job in sorted_jobs:
            lines.extend(_format_job(job))
            lines.append("")

    text = "\n".join(lines)
    out_file.write_text(text, encoding="utf-8")
    log.info("Results written to %s (%d jobs)", out_file, len(jobs))
    return out_file


def _format_job(job: dict[str, Any]) -> list[str]:
    score = job.get("fit_score", 0)
    icon = _score_icon(score)
    reloc = " *(relocation required)*" if job.get("relocation_required") else ""
    remote_tag = " `Remote`" if job.get("remote") else ""

    lines = [
        f"## {icon} [{job['title']}]({job['url']}) — {job['company']}",
        "",
        f"| Field       | Value |",
        f"|-------------|-------|",
        f"| **Source**  | {job.get('source', '')} |",
        f"| **Location**| {job.get('location_label', job.get('location', ''))}{reloc}{remote_tag} |",
        f"| **Salary**  | {job.get('salary_display', 'comp unknown')} |",
        f"| **Fit Score** | {score}/10 |",
        "",
        f"> **Fit note:** {job.get('fit_note', '')}",
        "",
        "---",
    ]
    return lines
