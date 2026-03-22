"""Minimal local .env loading without external dependencies."""

from __future__ import annotations

import os
import shlex
from pathlib import Path


def load_local_env(path: Path | None = None, *, override: bool = False) -> list[str]:
    env_path = path or Path(".env")
    if not env_path.exists():
        return []

    loaded_keys: list[str] = []
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if not override and key in os.environ:
            continue

        value = value.strip()
        if value:
            try:
                parsed = shlex.split(value, comments=True, posix=True)
                if parsed:
                    value = parsed[0]
            except ValueError:
                pass
        os.environ[key] = value
        loaded_keys.append(key)
    return loaded_keys
