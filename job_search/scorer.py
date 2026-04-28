"""Fit-score calculator and one-line note generator.

Scoring rubric (max 10):
  Base: 5
  +0–3  preferred domain matches in title/description
  +0–1  background keyword density in description
  +0–1  seniority level match (Senior/Staff/Principal/Group)
  -0–2  deprioritised domain hit
  Clamped to [1, 10].
"""

from __future__ import annotations

import re
from typing import Any


def _ci_count(text: str, terms: list[str]) -> int:
    count = 0
    for term in terms:
        if re.search(re.escape(term), text, re.IGNORECASE):
            count += 1
    return count


def score_job(job: dict[str, Any], cfg: dict) -> tuple[int, str]:
    """Return (score: int, note: str)."""
    title: str = job.get("title", "")
    desc: str = job.get("description", "")
    combined = f"{title} {desc}"

    high_fit_domains: list[str] = cfg["domains"]["high_fit"]
    low_fit_domains: list[str] = cfg["domains"]["low_fit"]
    background_kw: list[str] = cfg["keywords"]["background"]

    # ── Domain scoring ─────────────────────────────────────────────────────────
    high_hits = _ci_count(combined, high_fit_domains)
    low_hits = _ci_count(combined, low_fit_domains)

    domain_bonus = min(high_hits, 3)   # cap at +3
    domain_penalty = min(low_hits, 2)  # cap at -2

    # ── Background keyword density ─────────────────────────────────────────────
    bg_hits = _ci_count(combined, background_kw)
    bg_bonus = 1 if bg_hits >= 3 else 0

    # ── Seniority ──────────────────────────────────────────────────────────────
    seniority_terms = ["Senior", "Staff", "Principal", "Group", "Lead", "II", "III"]
    seniority_bonus = 1 if _ci_count(title, seniority_terms) > 0 else 0

    raw_score = 5 + domain_bonus + bg_bonus + seniority_bonus - domain_penalty
    score = max(1, min(10, raw_score))

    # ── Note ───────────────────────────────────────────────────────────────────
    note = _build_note(score, title, high_hits, low_hits, bg_hits, high_fit_domains, combined)

    return score, note


def _build_note(
    score: int,
    title: str,
    high_hits: int,
    low_hits: int,
    bg_hits: int,
    high_fit_domains: list[str],
    combined: str,
) -> str:
    parts: list[str] = []

    matched_domains = [
        d for d in high_fit_domains
        if re.search(re.escape(d), combined, re.IGNORECASE)
    ][:3]

    if score >= 8:
        lead = "Strong fit"
    elif score >= 6:
        lead = "Good fit"
    elif score >= 4:
        lead = "Moderate fit"
    else:
        lead = "Weak fit"

    if matched_domains:
        parts.append(f"aligns with {', '.join(matched_domains)}")
    if bg_hits >= 5:
        parts.append("description closely matches your background")
    elif bg_hits >= 2:
        parts.append("several background keywords present")
    if low_hits > 0:
        parts.append("some deprioritised domain signals")
    if not parts:
        parts.append("limited domain overlap with your background")

    return f"{lead} — {'; '.join(parts)}."
