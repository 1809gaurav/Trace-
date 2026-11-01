import hashlib
import os
import tempfile
import tracemalloc
from pathlib import Path

import pytest

from engine.evidence import (
    EvidenceImage,
    EvidenceNotAFileError,
    EvidenceRangeError,
    EvidenceWriteError,
    hash_file,
    make_read_only,
)


def test_hash_file_matches_sha256_and_is_streaming():
    payload = b"abc" * (1024 * 1024)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "big.bin"
        path.write_bytes(payload)
        tracemalloc.start()
        digest = hash_file(path)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert digest == hashlib.sha256(payload).hexdigest()
        assert peak < 16 * 1024 * 1024


def test_evidence_read_only_and_reverify_detects_changes():
    payload = b"0123456789"
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "img.bin"
        path.write_bytes(payload)
        with EvidenceImage(path) as evidence:
            assert evidence.size == len(payload)
            assert evidence.sha256 == hashlib.sha256(payload).hexdigest()
            assert evidence.read_at(0, 5) == b"01234"
            with pytest.raises(EvidenceWriteError):
                evidence.write(b"nope")
            with pytest.raises(EvidenceWriteError):
                evidence.writelines([b"x"])
            with pytest.raises(EvidenceWriteError):
                evidence.truncate(1)
            result = evidence.reverify()
            assert result.ok is True
            path.write_bytes(b"012345678x")
            result = evidence.reverify()
            assert result.ok is False


def test_bounds_and_empty_file_are_handled():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "empty.bin"
        path.write_bytes(b"")
        with EvidenceImage(path) as evidence:
            assert evidence.size == 0
            assert evidence.read_at(0, 0) == b""
            with pytest.raises(EvidenceRangeError):
                evidence.read_at(-1, 1)
            with pytest.raises(EvidenceRangeError):
                evidence.read_at(0, 1)
            with pytest.raises(EvidenceRangeError):
                evidence.read_at(1, 1)
            assert evidence.mmap_view() == b""

        path2 = Path(td) / "small.bin"
        path2.write_bytes(b"abcd")
        with EvidenceImage(path2) as evidence:
            with pytest.raises(EvidenceRangeError):
                evidence.read_at(3, 2)
            view = evidence.mmap_view()
            with pytest.raises((EvidenceWriteError, TypeError, ValueError)):
                view[0] = 0x00


def test_make_read_only_and_invalid_inputs():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "x.bin"
        path.write_bytes(b"data")
        assert make_read_only(path) is True
        with pytest.raises(EvidenceNotAFileError):
            EvidenceImage(Path(td))

        missing = Path(td) / "missing.bin"
        assert make_read_only(missing) is False


def test_mtime_warning_is_not_a_failure():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "img.bin"
        path.write_bytes(b"hello")
        with EvidenceImage(path) as evidence:
            old = evidence.opened_at_stat["mtime_ns"]
            os.utime(path, ns=(old, old + 1_000))
            result = evidence.reverify()
            assert result.ok is True
            assert result.mtime_changed is True
            assert "mtime" in result.reason.lower()
