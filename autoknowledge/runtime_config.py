"""Runtime configuration loading for AutoKnowledge."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_runtime_config(
    config_root: Path | None = None,
    runtime_config_path: Path | None = None,
) -> dict[str, Any]:
    config_root = config_root or Path("config")
    runtime = _load_json(config_root / "runtime.json")
    local_path = runtime_config_path or (config_root / "runtime.local.json")
    if local_path.exists():
        runtime = _deep_merge(runtime, _load_json(local_path))
    return runtime


def load_model_profiles(config_root: Path | None = None) -> dict[str, Any]:
    config_root = config_root or Path("config")
    return _load_json(config_root / "model_profiles.json")


def load_vault_profiles(config_root: Path | None = None) -> dict[str, Any]:
    config_root = config_root or Path("config")
    return _load_json(config_root / "vault_profiles.json")


def resolve_profile(
    *,
    input_kind: str,
    profile_name: str | None = None,
    model_override: str | None = None,
    config_root: Path | None = None,
    runtime_config_path: Path | None = None,
) -> dict[str, Any]:
    runtime = load_runtime_config(config_root, runtime_config_path=runtime_config_path)
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


def resolve_runtime_vault_path(
    *,
    vault_path: str | None = None,
    config_root: Path | None = None,
    runtime_config_path: Path | None = None,
) -> Path:
    if vault_path:
        return _expand_path(vault_path)
    runtime = load_runtime_config(config_root, runtime_config_path=runtime_config_path)
    configured = str(runtime.get("vault", {}).get("path", "")).strip()
    if configured:
        return _expand_path(configured)
    raise ValueError("No vault path provided and no runtime vault.path configured")


def resolve_runtime_vault_profile(
    *,
    vault_profile_name: str | None = None,
    config_root: Path | None = None,
    runtime_config_path: Path | None = None,
) -> str | None:
    if vault_profile_name:
        return vault_profile_name
    runtime = load_runtime_config(config_root, runtime_config_path=runtime_config_path)
    configured = str(runtime.get("vault", {}).get("profile", "")).strip()
    if configured:
        return configured
    configured = str(runtime.get("default_vault_profile", "")).strip()
    return configured or None


def resolve_runtime_backup_dir(
    *,
    backup_dir: str | None = None,
    config_root: Path | None = None,
    runtime_config_path: Path | None = None,
    apply_requested: bool = False,
) -> Path | None:
    if backup_dir:
        return _expand_path(backup_dir)
    if not apply_requested:
        return None
    runtime = load_runtime_config(config_root, runtime_config_path=runtime_config_path)
    vault_settings = runtime.get("vault", {})
    configured = str(vault_settings.get("backup_dir", "")).strip()
    if configured:
        return _expand_path(configured)
    if bool(vault_settings.get("require_backup_on_apply", False)):
        raise ValueError("Applying requires a backup directory, but no runtime vault.backup_dir is configured")
    return None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = _deep_merge(merged.get(key), value)
        return merged
    return override


def _expand_path(value: str) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(str(value).strip()))
    return Path(expanded)
