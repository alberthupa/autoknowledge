"""Simple JSONL experiment ledger."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_record(
    ledger_path: Path,
    *,
    kind: str,
    status: str,
    summary: str,
    details_path: str | None = None,
    metrics_path: str | None = None,
) -> dict[str, Any]:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "status": status,
        "summary": summary,
        "details_path": details_path,
        "metrics_path": metrics_path,
    }
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def tail_records(ledger_path: Path, limit: int = 20) -> list[dict[str, Any]]:
    if not ledger_path.exists():
        return []
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines[-limit:]]

