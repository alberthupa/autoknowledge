"""Runtime configuration loading for AutoKnowledge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_runtime_config(config_root: Path | None = None) -> dict[str, Any]:
    config_root = config_root or Path("config")
    return _load_json(config_root / "runtime.json")


def load_model_profiles(config_root: Path | None = None) -> dict[str, Any]:
    config_root = config_root or Path("config")
    return _load_json(config_root / "model_profiles.json")


def resolve_profile(
    *,
    input_kind: str,
    profile_name: str | None = None,
    model_override: str | None = None,
    config_root: Path | None = None,
) -> dict[str, Any]:
    runtime = load_runtime_config(config_root)
    resolved_name = profile_name or runtime.get("default_profiles", {}).get(input_kind)
    if not resolved_name:
        raise ValueError(f"No profile configured for input kind: {input_kind}")
    return resolve_named_profile(
        profile_name=resolved_name,
        model_override=model_override,
        config_root=config_root,
    )


def resolve_named_profile(
    *,
    profile_name: str,
    model_override: str | None = None,
    config_root: Path | None = None,
) -> dict[str, Any]:
    profiles = load_model_profiles(config_root).get("profiles", {})
    if profile_name not in profiles:
        raise ValueError(f"Unknown profile: {profile_name}")

    profile = dict(profiles[profile_name])
    profile["name"] = profile_name
    if model_override:
        profile["model"] = model_override
    return profile


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
