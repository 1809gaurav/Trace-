"""Append-only custody chain operations."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import CustodyEntry

ROOT_HASH = "root"


def _entry_hash(previous: str, at: datetime, step: str, details: dict[str, Any]) -> str:
    normalized_time = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    timestamp = normalized_time.astimezone(timezone.utc).isoformat()
    payload = f"{previous}|{timestamp}|{step}|{json.dumps(details, sort_keys=True, separators=(',', ':'))}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_entry(
    session: Session,
    case_id: str,
    step: str,
    details: dict[str, Any],
    run_id: str | None = None,
) -> CustodyEntry:
    """Append one hash-linked custody entry without updating prior rows."""
    previous_entry = session.scalar(
        select(CustodyEntry).where(CustodyEntry.case_id == case_id).order_by(CustodyEntry.idx.desc()).limit(1)
    )
    index = previous_entry.idx + 1 if previous_entry else 1
    previous_hash = previous_entry.hash if previous_entry else ROOT_HASH
    timestamp = datetime.now(timezone.utc)
    entry = CustodyEntry(
        case_id=case_id,
        run_id=run_id,
        idx=index,
        time=timestamp,
        step=step,
        details=details,
        prev_hash=previous_hash,
        hash=_entry_hash(previous_hash, timestamp, step, details),
    )
    session.add(entry)
    return entry


def verify_entries(entries: list[CustodyEntry]) -> dict[str, object]:
    """Validate sequential indexes, links, and hashes without modifying records."""
    previous_hash = ROOT_HASH
    for expected_index, entry in enumerate(entries, start=1):
        if entry.idx != expected_index or entry.prev_hash != previous_hash:
            return {"ok": False, "first_failing_index": expected_index, "reason": "The seal sequence or previous hash does not match."}
        if _entry_hash(previous_hash, entry.time, entry.step, entry.details) != entry.hash:
            return {"ok": False, "first_failing_index": expected_index, "reason": "This entry's contents no longer match its recorded seal."}
        previous_hash = entry.hash
    return {"ok": True, "first_failing_index": None, "reason": "All custody entries are in sequence and their seals match."}


def custody_payload(entry: CustodyEntry) -> dict[str, object]:
    """Serialize a custody entry using the frontend's mapped API fields."""
    time_value = entry.time
    return {
        "index": entry.idx,
        "time": time_value.isoformat(),
        "step": entry.step,
        "details": entry.details,
        "prev_hash": entry.prev_hash,
        "hash": entry.hash,
    }
