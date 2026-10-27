"""Append-only audit trail: output/audit_trail.json.

The file is a JSON list of AuditEntry objects (models.py), one per agent-loop step.
Each write takes a file lock, reads the existing list, appends, and atomically
replaces the file, so earlier runs are never wiped and two writers can't clobber
each other. A file that is not valid JSON is never overwritten.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from datetime import datetime
from typing import Any

from pydantic_core import to_jsonable_python

from backend.config import AUDIT_PATH
from backend.models import AuditEntry

LOCK_PATH = AUDIT_PATH.with_name(".audit_trail.lock")
MAX_TEXT = 6000  # long tool outputs are trimmed so the trail stays readable

_thread_lock = threading.Lock()


def _trim(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_TEXT:
        return value[:MAX_TEXT] + f"... [trimmed {len(value) - MAX_TEXT} chars]"
    if isinstance(value, dict):
        return {k: _trim(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_trim(v) for v in value]
    return value


def append_entry(entry: AuditEntry) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = _trim(to_jsonable_python(entry.model_dump()))
    with _thread_lock, open(LOCK_PATH, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        entries: list = []
        if AUDIT_PATH.exists() and AUDIT_PATH.stat().st_size:
            try:
                entries = json.loads(AUDIT_PATH.read_text())
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"{AUDIT_PATH} is not valid JSON; refusing to overwrite it.") from exc
            if not isinstance(entries, list):
                raise RuntimeError(f"{AUDIT_PATH} is not a JSON list; refusing to overwrite it.")
        entries.append(record)
        fd, tmp = tempfile.mkstemp(dir=AUDIT_PATH.parent, prefix=".audit_trail.", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(entries, f, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o644)  # mkstemp creates owner-only files
        os.replace(tmp, AUDIT_PATH)


def read_run(run_id: str) -> list[dict]:
    """Every entry for one run, in order."""
    if not AUDIT_PATH.exists() or not AUDIT_PATH.stat().st_size:
        return []
    return [e for e in json.loads(AUDIT_PATH.read_text()) if e.get("run_id") == run_id]


def log(
    *,
    run_id: str,
    ticket_id: int | None,
    agent: str,
    step: int,
    event: str,
    parent_agent: str | None = None,
    depth: int = 0,
    model: str | None = None,
    **detail: Any,
) -> None:
    append_entry(
        AuditEntry(
            timestamp=datetime.now().astimezone().isoformat(timespec="milliseconds"),
            run_id=run_id,
            ticket_id=ticket_id,
            agent=agent,
            parent_agent=parent_agent,
            depth=depth,
            step=step,
            event=event,
            model=model,
            detail=detail,
        )
    )
