import copy
from datetime import datetime, timezone

import pytest

from custody.chain import GENESIS_HASH, CustodyChain, EVIDENCE_RECEIVED, make_entry, next_entry
from custody.verify import tamper, tamper_detailed, tamper_variant, verify
from schemas.models import compute_entry_hash


def make_chain():
    clock = iter([
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
        datetime(2026, 1, 3, tzinfo=timezone.utc),
    ])
    chain = CustodyChain(clock=lambda: next(clock))
    for step in (EVIDENCE_RECEIVED, "IMAGE_OPENED", "RESULTS_WRITTEN"):
        chain.append(step, {"message": step})
    return chain


def test_make_entry_and_chain_round_trip():
    first = make_entry(None, EVIDENCE_RECEIVED, {"sha256": "abc"}, time="2026-01-01T00:00:00Z")
    assert first["index"] == 0
    assert first["prev_hash"] == GENESIS_HASH
    assert first["details"] == {"sha256": "abc"}
    second = next_entry([first], "IMAGE_OPENED", {"path": "/tmp/test.img"}, clock=lambda: datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert second["index"] == 1
    assert second["prev_hash"] == first["hash"]

    chain = make_chain()
    assert verify(chain.to_list()).ok is True


def test_details_are_copied_and_invalid_details_are_rejected():
    client = {"nested": {"value": 1}}
    chain = CustodyChain(clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    chain.append("IMAGE_OPENED", client)
    client["nested"]["value"] = 99
    assert chain.to_list()[0]["details"]["nested"]["value"] == 1

    with pytest.raises(ValueError):
        chain.append("IMAGE_OPENED", {"bad": float("nan")})

    with pytest.raises(ValueError):
        chain.append("IMAGE_OPENED", {"bad": set([1, 2])})


def test_verify_detects_first_tamper_and_anchors():
    chain = make_chain()
    altered = copy.deepcopy(chain.to_list())
    altered[1]["details"]["message"] = "MODIFIED"
    result = verify(altered)
    assert result.ok is False
    assert result.first_failing_index == 1
    assert result.code == "hash_mismatch"

    truncated = copy.deepcopy(chain.to_list()[:-1])
    assert verify(truncated).ok is True
    result = verify(truncated, expected_count=len(chain.to_list()))
    assert result.ok is False
    assert result.code == "count_mismatch"
    result = verify(truncated, expected_head=chain.head)
    assert result.ok is False
    assert result.code == "head_mismatch"


@pytest.mark.xfail(strict=True, reason="schema v1.0 hash does not cover time")
def test_time_is_not_in_hash_contract():
    prev = GENESIS_HASH
    step = "IMAGE_OPENED"
    details = {"path": "/tmp/test.img"}
    first = compute_entry_hash(prev, step, details)
    entry_a = {"index": 0, "time": "2026-01-01T00:00:00Z", "step": step, "details": details, "prev_hash": prev, "hash": first}
    entry_b = {"index": 0, "time": "2026-01-02T00:00:00Z", "step": step, "details": details, "prev_hash": prev, "hash": first}
    assert entry_a["hash"] != entry_b["hash"]


def test_tamper_variants_and_invalid_index():
    entries = make_chain().to_list()
    modified = tamper(entries, 1)
    assert modified != entries
    assert len(modified) == len(entries)
    assert verify(modified).ok is False

    for variant in ("delete", "reorder", "edit_prev_hash", "edit_hash"):
        copy_entries = tamper_variant(entries, 1, variant)
        assert len(copy_entries) in {len(entries), len(entries) - 1}

    with pytest.raises(IndexError):
        tamper(entries, 99)

    detailed = tamper_detailed(entries, 1)
    assert detailed.entry_index == 1
    assert detailed.field_path
    assert detailed.before != detailed.after
