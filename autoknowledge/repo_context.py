"""Helpers for loading repo-local policy and skill context."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def read_repo_text(relative_path: str, *, root: Path | None = None, missing_ok: bool = False) -> str:
    base_root = root or repo_root()
    path = base_root / relative_path
    if missing_ok and not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def build_context_bundle(
    relative_paths: list[str],
    *,
    root: Path | None = None,
    max_chars: int | None = None,
) -> str:
    chunks: list[str] = []
    total_chars = 0
    for relative_path in relative_paths:
        text = read_repo_text(relative_path, root=root, missing_ok=True).strip()
        if not text:
            continue
        chunk = f"FILE: {relative_path}\n{text}"
        if max_chars is not None and chunks and total_chars + len(chunk) > max_chars:
            break
        chunks.append(chunk)
        total_chars += len(chunk)
    return "\n\n".join(chunks).strip()
