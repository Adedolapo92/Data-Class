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

# Signals that definitively indicate a non-US location — roles matching any of
# these are dropped immediately regardless of other settings.
_INTERNATIONAL_SIGNALS = [
    # Countries
    "ireland", "india", "uk", "united kingdom", "england", "canada", "australia",
    "germany", "france", "netherlands", "spain", "italy", "poland", "sweden",
    "singapore", "japan", "china", "brazil", "mexico", "israel", "switzerland",
    "belgium", "denmark", "finland", "norway", "austria", "portugal", "romania",
    "czechia", "czech republic", "hungary", "colombia", "argentina", "chile",
    # Cities that are clearly non-US
    "dublin", "london", "berlin", "paris", "amsterdam", "toronto", "vancouver",
    "montreal", "sydney", "melbourne", "bangalore", "bengaluru", "hyderabad",
    "mumbai", "delhi", "pune", "tel aviv", "zurich", "stockholm", "copenhagen",
    "oslo", "helsinki", "vienna", "barcelona", "madrid", "lisbon", "warsaw",
    "prague", "budapest", "bucharest", "singapore",
    # Generic international markers
    "emea", "apac", "latam",
]

# US states and cities that are clearly domestic — used as a positive signal
# when a location doesn't say "remote" but is still US-based.
_US_SIGNALS = [
    "united states", "usa", "u.s.", "u.s.a", ", us", "(us)",
    "california", "new york", "texas", "washington", "illinois", "georgia",
    "massachusetts", "florida", "colorado", "oregon", "virginia", "ohio",
    "north carolina", "michigan", "arizona", "minnesota", "tennessee",
    "san francisco", "new york city", "nyc", "los angeles", "chicago",
    "boston", "austin", "seattle", "denver", "atlanta", "miami", "portland",
    "san jose", "san diego", "dallas", "houston", "phoenix", "raleigh",
    "nashville", "salt lake city", "minneapolis",
]


def classify_location(location: str, cfg: dict) -> dict[str, Any]:
    """
    Return a location classification dict with an `include` flag.

    include=False  → non-US location, drop the role
    include=True   → US or remote, keep the role

    Label hierarchy:
      Remote (US) > Austin TX > <City> — Relocation Required > US On-site > Location Unknown
    """
    loc = location or ""
    loc_lower = loc.lower()

    preferred = [p.lower() for p in cfg.get("preferred", [])]
    flag_list = [f.lower() for f in cfg.get("flag_relocation", [])]

    # ── 1. Reject clearly international roles ──────────────────────────────────
    if any(signal in loc_lower for signal in _INTERNATIONAL_SIGNALS):
        return {"label": loc, "remote": False, "relocation_required": False, "include": False}

    # ── 2. Remote — accept (assume US unless international signal above caught it)
    is_remote = any(p in loc_lower for p in ("remote", "anywhere", "distributed", "work from home", "wfh"))
    if is_remote:
        return {"label": "Remote (US)", "remote": True, "relocation_required": False, "include": True}

    # ── 3. Preferred US locations (Austin, etc.) ───────────────────────────────
    is_preferred = any(p in loc_lower for p in preferred)
    if is_preferred:
        label = _preferred_label(loc, cfg["preferred"])
        return {"label": label, "remote": False, "relocation_required": False, "include": True}

    # ── 4. Any other recognisable US location → include but flag relocation ──────
    is_us = (
        any(f in loc_lower for f in flag_list)
        or any(signal in loc_lower for signal in _US_SIGNALS)
    )
    if is_us:
        return {
            "label": f"{loc} — Relocation Required",
            "remote": False,
            "relocation_required": True,
            "include": True,
        }

    # ── 5. Blank / truly unknown — include with flag ───────────────────────────
    if not loc:
        return {"label": "Location Unknown", "remote": False, "relocation_required": False, "include": True}

    # ── 6. Location present but unrecognised — exclude to be safe ─────────────
    return {"label": loc, "remote": False, "relocation_required": False, "include": False}


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

    # Location — drop non-US roles immediately
    loc_info = classify_location(job.get("location", ""), cfg["locations"])
    if not loc_info["include"]:
        return None

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
