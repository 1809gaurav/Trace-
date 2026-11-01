"""Append-only SHA-256 custody chain generation and persistence."""

from __future__ import annotations

import copy
import json
import math
import os
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from schemas.models import compute_entry_hash

GENESIS_HASH = "0" * 64
ZERO_HASH = GENESIS_HASH
Clock = Callable[[], datetime]

EVIDENCE_RECEIVED = "EVIDENCE_RECEIVED"
IMAGE_OPENED = "IMAGE_OPENED"
FILESYSTEM_PARSED = "FILESYSTEM_PARSED"
CARVING_DONE = "CARVING_DONE"
FRAGMENTS_JOINED = "FRAGMENTS_JOINED"
FILES_CLASSIFIED = "FILES_CLASSIFIED"
RESULTS_WRITTEN = "RESULTS_WRITTEN"
IMAGE_REVERIFIED = "IMAGE_REVERIFIED"
REPORT_GENERATED = "REPORT_GENERATED"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc_iso(value: datetime | str | None) -> str:
    if value is None:
        value = _utc_now()
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not isinstance(value, datetime):
        raise TypeError("time must be a datetime or ISO-8601 string")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("custody clock must return a timezone-aware datetime")
    dt = value.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_json_value(value: Any) -> Any:
    """Recursively coerce dataclass and mapping values into JSON-safe primitives."""
    if is_dataclass(value):
        return _normalize_json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, (set, frozenset, bytes, bytearray)):
        raise ValueError("details cannot contain sets or raw bytes")
    return value


def _validate_step(step: str) -> str:
    if not isinstance(step, str):
        raise ValueError("step must be a non-empty string")
    cleaned = step.strip()
    if not cleaned:
        raise ValueError("step must be a non-empty string")
    if len(cleaned) > 64:
        raise ValueError("step cannot exceed 64 characters")
    return cleaned


def _validate_details(details: Any) -> dict[str, Any]:
    normalized = _normalize_json_value(details)
    if not isinstance(normalized, dict):
        raise ValueError("details must be a JSON-serializable dictionary")
    for key in normalized:
        if not isinstance(key, str):
            raise ValueError("details keys must be strings")
    try:
        json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("details must be JSON-serializable and finite") from exc
    for value in _flatten_values(normalized):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise ValueError("details cannot contain NaN or Infinity")
        if isinstance(value, (set, frozenset, bytes, bytearray)):
            raise ValueError("details cannot contain sets or raw bytes")
    return copy.deepcopy(normalized)


def _flatten_values(value: Any):
    if isinstance(value, dict):
        for child in value.values():
            yield from _flatten_values(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _flatten_values(child)
    else:
        yield value


def make_entry(prev_entry: Mapping[str, Any] | None, step: str, details: dict[str, Any], *, time: datetime | str | None) -> dict[str, Any]:
    """Return the next chain entry for a supplied previous entry and payload."""
    prev_hash = prev_entry["hash"] if prev_entry is not None else GENESIS_HASH
    cleaned_step = _validate_step(step)
    details_copy = _validate_details(details)
    time_text = _as_utc_iso(time)
    entry = {
        "index": (prev_entry["index"] + 1) if prev_entry is not None else 0,
        "time": time_text,
        "step": cleaned_step,
        "details": copy.deepcopy(details_copy),
        "prev_hash": prev_hash,
        "hash": compute_entry_hash(prev_hash, cleaned_step, details_copy),
    }
    return entry


def next_entry(entries: Sequence[Mapping[str, Any]], step: str, details: dict[str, Any], *, clock: Clock | None = None) -> dict[str, Any]:
    """Create the next entry after an existing sequence using a supplied clock."""
    if clock is None:
        clock = _utc_now
    last = entries[-1] if entries else None
    return make_entry(last, step, details, time=clock())


def head_hash(entries: Sequence[Mapping[str, Any]]) -> str:
    """Return the latest hash in the chain or the genesis hash for an empty chain."""
    if not entries:
        return GENESIS_HASH
    return str(entries[-1].get("hash", GENESIS_HASH))


class CustodyChain:
    """Append-only hash-chained custody log."""

    def __init__(self, *, clock: Clock | None = None):
        self._clock = _utc_now if clock is None else clock
        self._entries: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    @property
    def entries(self) -> tuple[dict[str, Any], ...]:
        """Return an immutable snapshot of the appended entries."""
        return tuple(copy.deepcopy(entry) for entry in self._entries)

    def to_list(self) -> list[dict[str, Any]]:
        """Return a deep-copied list of the current chain."""
        return [copy.deepcopy(entry) for entry in self._entries]

    @property
    def head(self) -> str:
        return head_hash(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def append(self, step: str, details: dict[str, Any]) -> dict[str, Any]:
        """Append a new event and return a detached copy of the stored entry."""
        with self._lock:
            last_entry = self._entries[-1] if self._entries else None
            entry = make_entry(last_entry, step, details, time=self._clock())
            self._entries.append(copy.deepcopy(entry))
            return copy.deepcopy(entry)

    @classmethod
    def from_list(cls, entries: Sequence[Mapping[str, Any]], *, verify: bool = True) -> CustodyChain:
        """Rehydrate a chain from a list of serialized entries."""
        from custody.verify import verify as verify_chain

        normalized = [copy.deepcopy(dict(entry)) for entry in entries]
        if verify and not verify_chain(normalized).ok:
            raise ValueError("the supplied chain does not verify")
        chain = cls()
        chain._entries = normalized
        return chain

    def save(self, path: str | Path) -> Path:
        """Atomically save the chain to disk as JSON."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path = destination.parent / f".{destination.name}.tmp"
        payload = json.dumps(self.to_list(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, destination)
        return destination

    @classmethod
    def load(cls, path: str | Path, *, verify: bool = True) -> CustodyChain:
        """Load a chain from disk and verify it unless disabled."""
        destination = Path(path)
        with destination.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return cls.from_list(payload, verify=verify)


def image_opened_details(evidence: Any) -> dict[str, Any]:
    """Build a details payload for an image-opened custody record."""
    try:
        size = int(getattr(evidence, "size", getattr(evidence, "size_bytes", 0)))
        sha256 = getattr(evidence, "sha256", "")
        path = str(getattr(evidence, "path", ""))
    except Exception:
        path = ""
        size = 0
        sha256 = ""
    return {"path": path, "size_bytes": size, "sha256": sha256}


def image_reverified_details(result: Any) -> dict[str, Any]:
    """Build a details payload for an image-reverified custody record."""
    return {
        "hash_equal": bool(getattr(result, "ok", False)),
        "expected_sha256": getattr(result, "expected_sha256", ""),
        "actual_sha256": getattr(result, "actual_sha256", ""),
        "size_before": getattr(result, "size_before", 0),
        "size_after": getattr(result, "size_after", 0),
        "mtime_changed": bool(getattr(result, "mtime_changed", False)),
    }
