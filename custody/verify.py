"""Verification and tampering helpers for custody chains.

The chain can only prove continuity and integrity for entries it contains. If the
last entries are removed, a verifier can detect the truncation only with an anchor
such as the expected head hash or expected count.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from schemas.models import compute_entry_hash

from custody.chain import CustodyChain, GENESIS_HASH, head_hash


@dataclass(frozen=True)
class VerifyResult:
    """Verification outcome for a custody chain."""

    ok: bool
    first_failing_index: int | None
    code: str | None
    reason: str
    checked: int
    untrusted_from_index: int | None
    warnings: list[str]
    head_hash: str
    checked_at: str

    def __bool__(self) -> bool:
        return self.ok

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "first_failing_index": self.first_failing_index,
            "code": self.code,
            "reason": self.reason,
            "checked": self.checked,
            "untrusted_from_index": self.untrusted_from_index,
            "warnings": list(self.warnings),
            "head_hash": self.head_hash,
            "checked_at": self.checked_at,
        }


@dataclass(frozen=True)
class TamperResult:
    """Tampering description for a single entry."""

    chain: list[dict[str, Any]]
    entry_index: int
    field_path: str
    before: Any
    after: Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_entries(entries: CustodyChain | Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(entries, CustodyChain):
        items = entries.to_list()
    else:
        items = [dict(entry) for entry in entries]
    return items


def _inspect_step(step: Any) -> bool:
    return isinstance(step, str) and bool(step.strip()) and len(step.strip()) <= 64


def _format_reason(code: str, index: int) -> str:
    messages = {
        "malformed": f"Entry {index} is malformed. It does not have the expected custody fields.",
        "index_gap": f"Entry {index} does not link to the entry before it. An entry may have been removed or reordered.",
        "duplicate_index": f"Entry {index} has a duplicate index. An entry may have been duplicated or reordered.",
        "bad_genesis": "Entry 0 does not begin with the zero hash. The chain may have been replaced.",
        "prev_hash_mismatch": f"Entry {index} does not link to the entry before it. An entry may have been removed or reordered.",
        "hash_mismatch": f"Entry {index} was changed. Everything after it can no longer be trusted.",
        "head_mismatch": "The observed head hash does not match the expected anchor.",
        "count_mismatch": "The chain length does not match the expected count anchor.",
    }
    return messages.get(code, f"Entry {index} failed verification.")


def verify(
    entries: CustodyChain | Sequence[Mapping[str, Any]],
    *,
    expected_head: str | None = None,
    expected_count: int | None = None,
    clock: Any = None,
) -> VerifyResult:
    """Verify a custody chain and return a dict-like verification result."""
    del clock
    chain = _normalize_entries(entries)
    warnings: list[str] = []
    if not chain:
        warnings.append("Empty chain: there is nothing to verify.")
        return VerifyResult(
            ok=True,
            first_failing_index=None,
            code=None,
            reason="Empty chain: nothing to verify.",
            checked=0,
            untrusted_from_index=None,
            warnings=warnings,
            head_hash=GENESIS_HASH,
            checked_at=_utc_now(),
        )

    seen_indexes: set[int] = set()
    previous_hash = GENESIS_HASH
    checked = 0
    for index, entry in enumerate(chain):
        checked = index + 1
        if not isinstance(entry, Mapping):
            return VerifyResult(
                ok=False,
                first_failing_index=index,
                code="malformed",
                reason=_format_reason("malformed", index),
                checked=checked,
                untrusted_from_index=index,
                warnings=warnings,
                head_hash=head_hash(chain[:index]),
                checked_at=_utc_now(),
            )
        required = {"index", "time", "step", "details", "prev_hash", "hash"}
        if not required.issubset(entry):
            return VerifyResult(
                ok=False,
                first_failing_index=index,
                code="malformed",
                reason=_format_reason("malformed", index),
                checked=checked,
                untrusted_from_index=index,
                warnings=warnings,
                head_hash=head_hash(chain[:index]),
                checked_at=_utc_now(),
            )

        entry_index = entry.get("index")
        if not isinstance(entry_index, int):
            return VerifyResult(False, index, "malformed", _format_reason("malformed", index), checked, index, warnings, head_hash(chain[:index]), _utc_now())
        if entry_index in seen_indexes:
            return VerifyResult(False, index, "duplicate_index", _format_reason("duplicate_index", index), checked, index, warnings, head_hash(chain[:index]), _utc_now())
        seen_indexes.add(entry_index)
        if index != entry_index:
            code = "index_gap" if entry_index > index else "index_gap"
            return VerifyResult(False, index, code, _format_reason(code, index), checked, index, warnings, head_hash(chain[:index]), _utc_now())
        if index == 0 and entry.get("prev_hash") != GENESIS_HASH:
            return VerifyResult(False, index, "bad_genesis", _format_reason("bad_genesis", index), checked, index, warnings, head_hash(chain[:index]), _utc_now())
        if index > 0 and entry.get("prev_hash") != chain[index - 1].get("hash"):
            return VerifyResult(False, index, "prev_hash_mismatch", _format_reason("prev_hash_mismatch", index), checked, index, warnings, head_hash(chain[:index]), _utc_now())

        details = entry.get("details")
        step = entry.get("step")
        if not isinstance(details, Mapping) or not isinstance(step, str):
            return VerifyResult(False, index, "malformed", _format_reason("malformed", index), checked, index, warnings, head_hash(chain[:index]), _utc_now())
        details = dict(details)
        if not _inspect_step(step):
            warnings.append(f"Entry {index} has an unusual step name: {step!r}.")
        if not isinstance(entry.get("time"), str):
            return VerifyResult(False, index, "malformed", _format_reason("malformed", index), checked, index, warnings, head_hash(chain[:index]), _utc_now())
        if index > 0:
            prior_time = chain[index - 1].get("time")
            if isinstance(prior_time, str) and isinstance(entry.get("time"), str):
                try:
                    if datetime.fromisoformat(entry["time"].replace("Z", "+00:00")) < datetime.fromisoformat(prior_time.replace("Z", "+00:00")):
                        warnings.append(f"Entry {index} has a timestamp earlier than the entry before it.")
                except ValueError:
                    pass

        expected_hash = compute_entry_hash(str(entry.get("prev_hash", previous_hash)), str(entry.get("step", "")), details)
        if entry.get("hash") != expected_hash:
            return VerifyResult(False, index, "hash_mismatch", _format_reason("hash_mismatch", index), checked, index, warnings, head_hash(chain[:index]), _utc_now())
        previous_hash = str(entry.get("hash"))

    if expected_head is not None and head_hash(chain) != expected_head:
        return VerifyResult(False, len(chain), "head_mismatch", _format_reason("head_mismatch", len(chain)), checked, len(chain), warnings, head_hash(chain), _utc_now())
    if expected_count is not None and len(chain) != expected_count:
        return VerifyResult(False, len(chain), "count_mismatch", _format_reason("count_mismatch", len(chain)), checked, len(chain), warnings, head_hash(chain), _utc_now())

    return VerifyResult(
        ok=True,
        first_failing_index=None,
        code=None,
        reason="Chain verification succeeded.",
        checked=len(chain),
        untrusted_from_index=None,
        warnings=warnings,
        head_hash=head_hash(chain),
        checked_at=_utc_now(),
    )


def _tamper_first_string(value: Any) -> tuple[str, Any, Any] | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str):
                before = item
                value[key] = f"{item}!"
                return key, before, value[key]
            nested = _tamper_first_string(item)
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, str):
                before = item
                value[index] = f"{item}!"
                return f"[{index}]", before, value[index]
            nested = _tamper_first_string(item)
            if nested is not None:
                return nested
    return None


def tamper(entries: Sequence[Mapping[str, Any]], index: int, *, seed: int = 0) -> list[dict[str, Any]]:
    """Return a copied chain with a single entry value modified at the given index."""
    del seed
    modified = copy.deepcopy([dict(entry) for entry in entries])
    if index < 0 or index >= len(modified):
        raise IndexError("custody entry index is out of range")
    details = modified[index].get("details")
    if not isinstance(details, Mapping):
        raise ValueError("custody entry details must be an object")
    if not _tamper_first_string(details):
        details["_tampered"] = True
    return modified


def tamper_detailed(entries: Sequence[Mapping[str, Any]], index: int, *, seed: int = 0) -> TamperResult:
    """Return a descriptive tamper result for the supplied chain and entry index."""
    modified = copy.deepcopy([dict(entry) for entry in entries])
    if index < 0 or index >= len(modified):
        raise IndexError("custody entry index is out of range")
    target = modified[index]
    field_path = "details"
    before = None
    after = None
    if isinstance(target.get("details"), dict):
        mutation = _tamper_first_string(target["details"])
        if mutation is not None:
            field_path = f"details.{mutation[0]}"
            before = mutation[1]
            after = mutation[2]
        else:
            before = target["details"].copy()
            target["details"]["_tampered"] = True
            after = target["details"].copy()
    else:
        before = target.get("hash")
        target["hash"] = f"{target.get('hash', '0')[:-1]}0"
        after = target["hash"]
        field_path = "hash"
    return TamperResult(modified, index, field_path, before, after)


def tamper_variant(entries: Sequence[Mapping[str, Any]], index: int, kind: str) -> list[dict[str, Any]]:
    """Create a copy of the chain with one variant tamper applied."""
    modified = copy.deepcopy([dict(entry) for entry in entries])
    if index < 0 or index >= len(modified):
        raise IndexError("custody entry index is out of range")
    variant = kind.lower()
    if variant == "delete":
        del modified[index]
    elif variant == "reorder":
        if len(modified) > 1:
            modified[index], modified[(index + 1) % len(modified)] = modified[(index + 1) % len(modified)], modified[index]
    elif variant == "edit_prev_hash":
        modified[index]["prev_hash"] = "1" * 64
    elif variant == "edit_hash":
        modified[index]["hash"] = "f" * 64
    else:
        raise ValueError("kind must be one of: delete, reorder, edit_prev_hash, edit_hash")
    return modified


def _parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a custody chain and optionally tamper it in memory.")
    parser.add_argument("path", help="Path to a custody JSON file")
    parser.add_argument("--expected-head", dest="expected_head", help="Expected ending head hash for the chain")
    parser.add_argument("--expected-count", dest="expected_count", type=int, help="Expected number of entries in the chain")
    parser.add_argument("--tamper", dest="tamper_index", type=int, help="Tamper an entry in memory to demonstrate verification failure")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    return parser.parse_args()


def _main() -> int:
    args = _parse_cli()
    try:
        with open(args.path, "r", encoding="utf-8") as handle:
            entries = json.load(handle)
    except FileNotFoundError:
        print(f"File not found: {args.path}")
        return 1
    if args.tamper_index is not None:
        entries = tamper(entries, args.tamper_index)
    result = verify(entries, expected_head=args.expected_head, expected_count=args.expected_count)
    if args.json:
        print(json.dumps(result.to_dict(), sort_keys=True))
    else:
        status = "OK" if result.ok else "FAIL"
        print(f"{status}: checked={result.checked}; first_failing_index={result.first_failing_index}; code={result.code}; reason={result.reason}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
