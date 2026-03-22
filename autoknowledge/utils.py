"""Utility helpers for AutoKnowledge."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"\s+", "-", value.strip())
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-") or "untitled"


def stable_short_hash(*parts: str, length: int = 8) -> str:
    joined = "\n".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:length]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def date_prefix_from_iso(value: str | None) -> str:
    if value and len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return value[:10]
    return utc_now_iso()[:10]


def year_from_date(date_value: str) -> str:
    return date_value[:4]


def title_from_path(path: Path) -> str:
    stem = path.stem.replace("_", " ").replace("-", " ")
    return " ".join(token.capitalize() for token in stem.split()) or "Untitled"

