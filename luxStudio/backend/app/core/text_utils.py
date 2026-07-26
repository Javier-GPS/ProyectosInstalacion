"""Text normalization and field extraction utilities.

This module centralises the small string helpers that were previously
duplicated across the catalog and admin services. Keeping them in one
place means future tweaks (e.g. accepting lowercase ``k`` instead of
``K`` for the CCT) land in one spot instead of being scattered across
``routers/ldt.py``, ``services/luminaire_catalog.py``,
``services/ldt_matcher.py``, ``services/admin_service.py`` and
``services/ldt_loader.py``.

All helpers are pure: they have no DB or HTTP dependencies, which makes
them trivial to unit-test in isolation.
"""
from __future__ import annotations

import re

# Tokens considered "model family" identifiers when parsing LDT names.
# Order matters: more specific tokens must come before less specific ones
# (e.g. "TECEO" before a generic alphanumeric prefix).
_MODEL_FAMILY_TOKENS: tuple[str, ...] = (
    "KRONOS",
    "CLAP",
    "SIL",
    "TECEO",
    "TERESA",
    "FRANCESCO",
)

# Match an Fxxx optic code, e.g. F151, F2M2, F2MD. Allows at least one
# alphanumeric char after the F so we still match tokens like "F1A".
# Note: ``\b`` treats ``_`` as a word char, so LDT names like
# "CLAP_M_C35_30K_F151" only match the fallback pattern. Behaviour
# matches the pre-refactor implementation.
_RE_OPTIC_FAMILY = re.compile(r"\b(F[0-9A-Z]{2,4})\b")
# Fallback pattern: any F[alnum]{1-6} so very short or longer codes
# are still recovered.
_RE_OPTIC_FAMILY_FALLBACK = re.compile(r"\b(F[A-Z0-9]{1,6})\b")

# Match an explicit CCT indicator, e.g. "30K", "40K".
_RE_CCT_KELVIN = re.compile(r"\b(\d{2})K\b")

# Split on non-alphanumerics for the generic "first token" fallback.
_RE_ALNUM = re.compile(r"[A-Z0-9]+")


def norm(value: str | None) -> str:
    """Return the canonical string form: stripped and uppercased.

    ``None`` and empty strings return ``""``. Non-string inputs are
    coerced via ``str()`` first (the catalog code uses ``str(value)``
    in one place; this matches that behaviour for backwards compat).
    """
    if not value:
        return ""
    return str(value).strip().upper()


def extract_optic_family(name: str) -> str:
    """Extract the optic family code (e.g. ``F151``) from a luminaire name.

    Returns ``"UNKNOWN"`` when no code can be recovered.
    """
    match = _RE_OPTIC_FAMILY.search(name or "")
    if not match:
        match = _RE_OPTIC_FAMILY_FALLBACK.search(name or "")
    return match.group(1) if match else "UNKNOWN"


def extract_model_family(text: str) -> str:
    """Extract the model family token (e.g. ``KRONOS``) from a name.

    Looks for known Salvi tokens first, then falls back to the first
    alphanumeric token in the uppercased name. Returns ``"UNKNOWN"`` if
    the name has no alphanumeric content.
    """
    normalized = (text or "").upper().replace("_", " ")
    for token in _MODEL_FAMILY_TOKENS:
        if token in normalized:
            return token
    parts = _RE_ALNUM.findall(normalized)
    return parts[0] if parts else "UNKNOWN"


def extract_cct(text: str) -> int:
    """Extract the CCT in Kelvin from a token like ``30K`` or ``40K``.

    Defaults to 4000 K when no indicator is found.
    """
    match = _RE_CCT_KELVIN.search((text or "").upper())
    return int(match.group(1)) * 100 if match else 4000
