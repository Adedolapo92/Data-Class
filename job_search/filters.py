"""Title, location, and compensation filters."""

from __future__ import annotations

import re
from typing import Any


def _ci_contains(text: str, phrase: str) -> bool:
    """True if *phrase* appears as a whole word / phrase in *text* (case-insensitive)."""
    return bool(re.search(re.escape(phrase), text, re.IGNORECASE))


# ── Title filtering ────────────────────────────────────────────────────────────

def title_matches_include(title: str, include_patterns: list[str]) -> bool:
    """True if the title matches at least one inclusion pattern."""
    for pattern in include_patterns:
        if _ci_contains(title, pattern):
            return True
    return False


def title_matches_exclude(title: str, exclude_patterns: list[str]) -> bool:
    """True if the title matches any exclusion pattern (role should be dropped)."""
    for pattern in exclude_patterns:
        if _ci_contains(title, pattern):
            return True
    return False


# ── Location classification ────────────────────────────────────────────────────

def classify_location(location: str, cfg: dict) -> dict[str, Any]:
    """
    Return:
      {
        "label": "Remote" | "Austin TX" | "Relocation Required" | "On-site" | "Unknown",
        "remote": True/False,
        "relocation_required": True/False,
        "include": True/False,  # False only for roles that are strictly on-site in undesirable cities (not filtered here — included with flag)
      }
    """
    loc = location or ""
    preferred = [p.lower() for p in cfg.get("preferred", [])]
    flag_list = [f.lower() for f in cfg.get("flag_relocation", [])]

    loc_lower = loc.lower()

    is_remote = any(p in loc_lower for p in ("remote", "anywhere", "distributed"))
    is_preferred = any(p in loc_lower for p in preferred)
    is_flagged = any(f in loc_lower for f in flag_list)

    if is_remote or is_preferred:
        label = "Remote (US)" if is_remote else _preferred_label(loc, cfg["preferred"])
        return {"label": label, "remote": is_remote, "relocation_required": False, "include": True}

    if is_flagged:
        return {
            "label": f"{loc} — Relocation Required",
            "remote": False,
            "relocation_required": True,
            "include": True,
        }

    # Unknown / other on-site — still include, just label it
    if not loc:
        return {"label": "Location Unknown", "remote": False, "relocation_required": False, "include": True}

    return {"label": loc, "remote": False, "relocation_required": False, "include": True}


def _preferred_label(loc: str, preferred: list[str]) -> str:
    for p in preferred:
        if p.lower() in loc.lower():
            return p
    return loc


# ── Salary parsing & filtering ─────────────────────────────────────────────────

_SALARY_PATTERNS = [
    # "$130,000 - $180,000"
    re.compile(r"\$\s*([\d,]+)\s*[-–to]+\s*\$\s*([\d,]+)", re.IGNORECASE),
    # "$180k" or "$180,000"
    re.compile(r"\$\s*([\d,]+)\s*k?\b", re.IGNORECASE),
    # "130000 to 180000" (no $)
    re.compile(r"\b([\d,]{5,})\s*[-–to]+\s*([\d,]{5,})\b"),
]


def parse_salary(salary_text: str) -> tuple[int | None, int | None]:
    """Return (min_salary, max_salary) as integers. Either may be None."""
    if not salary_text:
        return None, None

    def _clean(s: str) -> int:
        s = s.replace(",", "").strip()
        val = int(s)
        # Handle shorthand like "$130k"
        if val < 1000 and "k" in salary_text.lower():
            val *= 1000
        return val

    for pat in _SALARY_PATTERNS:
        m = pat.search(salary_text)
        if m:
            groups = m.groups()
            if len(groups) == 2 and groups[1]:
                return _clean(groups[0]), _clean(groups[1])
            return None, _clean(groups[0])

    return None, None


def salary_passes(salary_text: str, min_max: int) -> tuple[bool, str]:
    """
    Returns (passes: bool, display_label: str).
    - If no salary listed: passes=True, label="comp unknown"
    - If max >= min_max: passes=True
    - If max < min_max: passes=False
    """
    if not salary_text:
        return True, "comp unknown"

    lo, hi = parse_salary(salary_text)
    effective_max = hi if hi is not None else lo

    if effective_max is None:
        return True, salary_text.strip() + " (unverified)"

    if effective_max >= min_max:
        return True, _format_salary(lo, hi)

    return False, _format_salary(lo, hi)


def _format_salary(lo: int | None, hi: int | None) -> str:
    if lo and hi:
        return f"${lo:,} – ${hi:,}"
    if hi:
        return f"up to ${hi:,}"
    if lo:
        return f"from ${lo:,}"
    return "salary listed"


# ── Main filter pass ───────────────────────────────────────────────────────────

def apply_filters(job: dict[str, Any], cfg: dict) -> dict[str, Any] | None:
    """
    Return an enriched job dict if the role passes all filters, else None.
    Adds keys: location_label, remote, relocation_required, salary_display.
    """
    title = job.get("title", "")

    # Title inclusion
    if not title_matches_include(title, cfg["keywords"]["title_include"]):
        return None

    # Title exclusion
    if title_matches_exclude(title, cfg["keywords"]["title_exclude"]):
        return None

    # Location
    loc_info = classify_location(job.get("location", ""), cfg["locations"])

    # Salary
    passes, salary_display = salary_passes(
        job.get("salary_text", ""),
        cfg["compensation"]["minimum_max_salary"],
    )
    if not passes:
        return None

    return {
        **job,
        "location_label": loc_info["label"],
        "remote": loc_info["remote"],
        "relocation_required": loc_info["relocation_required"],
        "salary_display": salary_display,
    }
