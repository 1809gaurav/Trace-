"""Read-only evidence access, hashing, and integrity verification."""

from __future__ import annotations

import hashlib
import io
import mmap
import os
import stat
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Any


class EvidenceError(Exception):
    """Base class for evidence-related failures."""


class EvidenceNotFoundError(EvidenceError, FileNotFoundError):
    """The requested image path does not exist."""


class EvidenceNotAFileError(EvidenceError, OSError):
    """The requested evidence path is a directory or special file."""


class EvidencePermissionError(EvidenceError, PermissionError):
    """The evidence file cannot be read or modified as expected."""


class EvidenceWriteError(EvidenceError, OSError):
    """A write attempt was made against a read-only evidence image."""


class EvidenceRangeError(EvidenceError, ValueError):
    """The requested read range is outside the open file."""


@dataclass(frozen=True)
class IntegrityResult:
    """Result of a SHA-256 and size/mtime recheck of a file."""

    ok: bool
    expected_sha256: str
    actual_sha256: str
    size_before: int
    size_after: int
    mtime_changed: bool
    reason: str

    def __bool__(self) -> bool:
        return self.ok


class _ReadOnlyMappedView:
    """Read-only view of mapped file bytes that rejects mutation attempts."""

    def __init__(self, data: bytes | mmap.mmap):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if isinstance(self._data, mmap.mmap):
            self._data.close()

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def __contains__(self, item: object) -> bool:
        return item in self._data

    def __getitem__(self, item):
        return self._data[item]

    def find(self, value: bytes | bytearray | memoryview, start: int = 0, end: int | None = None):
        if end is None:
            return self._data.find(value, start)
        return self._data.find(value, start, end)

    def __setitem__(self, key: Any, value: Any) -> None:
        raise EvidenceWriteError("Evidence images are read-only; the mapped view cannot be written to.")

    def __delitem__(self, key: Any) -> None:
        raise EvidenceWriteError("Evidence images are read-only; the mapped view cannot be written to.")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (bytes, bytearray, memoryview, mmap.mmap, _ReadOnlyMappedView)):
            left = bytes(self._data)
            right = bytes(other._data if isinstance(other, _ReadOnlyMappedView) else other)
            return left == right
        return NotImplemented

    def __repr__(self) -> str:
        return repr(bytes(self._data))

    def tobytes(self) -> bytes:
        return bytes(self._data)

    def hex(self) -> str:
        return bytes(self._data).hex()


_HASH_CHUNK_SIZE = 1 << 20


def _resolve_evidence_path(path: str | os.PathLike[str]) -> Path:
    """Resolve a filesystem path and reject directories and special files."""
    candidate = Path(path).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise EvidenceNotFoundError(f"Evidence file was not found: {candidate}") from exc

    try:
        mode = resolved.stat().st_mode
    except OSError as exc:
        raise EvidencePermissionError(f"The evidence file could not be opened: {resolved}") from exc

    if not stat.S_ISREG(mode):
        raise EvidenceNotAFileError(f"Evidence path must be a regular file: {resolved}")
    return resolved


def _hash_stream(handle: BinaryIO, *, chunk_size: int = _HASH_CHUNK_SIZE) -> str:
    """Hash a stream in bounded chunks without loading the whole file."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    while True:
        chunk = handle.read(chunk_size)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def hash_file(path: str | os.PathLike[str], chunk_size: int = 1 << 20) -> str:
    """Return the SHA-256 hex digest for a file using a streaming loop."""
    resolved = _resolve_evidence_path(path)
    with resolved.open("rb") as handle:
        return _hash_stream(handle, chunk_size=chunk_size)


class EvidenceImage:
    """Read-only evidence handle with recorded size, digest, and stat metadata."""

    def __init__(self, path: str | os.PathLike[str], *, max_read_bytes: int = 1 << 20):
        self.path = _resolve_evidence_path(path)
        self.max_read_bytes = max(1, max_read_bytes)
        self._handle = self.path.open("rb")
        self._mmap: mmap.mmap | None = None
        try:
            stat_info = os.fstat(self._handle.fileno())
            self.size = int(stat_info.st_size)
            self.size_bytes = self.size
            self.sha256 = _hash_stream(self._handle)
            self.opened_at_stat = {"size": self.size, "mtime_ns": int(stat_info.st_mtime_ns)}
            self._handle.seek(0)
        except Exception:
            self.close()
            raise

    def __enter__(self) -> EvidenceImage:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def read(self, size: int = -1) -> bytes:
        """Read bytes from the underlying file object."""
        return self._handle.read(size)

    def read_at(self, offset: int, length: int) -> bytes:
        """Read a bounded range from the evidence image.

        Negative offsets, offsets beyond EOF, and requests that exceed the configured
        read cap raise EvidenceRangeError.
        """
        if offset < 0:
            raise EvidenceRangeError("Evidence read offset cannot be negative.")
        if length < 0:
            raise EvidenceRangeError("Evidence read length cannot be negative.")
        if length > self.max_read_bytes:
            raise EvidenceRangeError(f"Evidence read length exceeds the cap of {self.max_read_bytes} bytes.")
        if offset > self.size:
            raise EvidenceRangeError("Evidence read offset is beyond the end of the file.")
        end = offset + length
        if end > self.size:
            raise EvidenceRangeError("Evidence read range exceeds the end of the file.")
        self._handle.seek(offset)
        return self._handle.read(length)

    def mmap_view(self):
        """Return a read-only mmap or bytes object for the engine.

        The returned object is bytes-like and supports the low-level reads used by the
        FAT32 and signature scanners without allowing writes.
        """
        if self.size == 0:
            return b""
        if self._mmap is None:
            self._mmap = mmap.mmap(self._handle.fileno(), 0, access=mmap.ACCESS_READ)
        return self._mmap

    def map_readonly(self):
        """Compatibility alias for the older pipeline API."""
        return self.mmap_view()

    def reverify(self) -> IntegrityResult:
        """Recompute the current SHA-256 and compare size and mtime against the open-time values.

        A content hash or size mismatch fails, while an mtime-only change is reported as a
        warning field rather than an integrity failure.
        """
        with self.path.open("rb") as handle:
            current_stat = os.fstat(handle.fileno())
            current_size = int(current_stat.st_size)
            actual_hash = _hash_stream(handle)

        mtime_changed = current_stat.st_mtime_ns != self.opened_at_stat["mtime_ns"]
        ok = current_size == self.size and actual_hash == self.sha256
        if ok and mtime_changed:
            reason = "mtime changed but the content hash and file size are unchanged."
        elif not ok:
            reason = "image hash or size changed since the evidence was opened."
        else:
            reason = "image is intact and unchanged."
        return IntegrityResult(
            ok=ok,
            expected_sha256=self.sha256,
            actual_sha256=actual_hash,
            size_before=self.size,
            size_after=current_size,
            mtime_changed=mtime_changed,
            reason=reason,
        )

    def close(self) -> None:
        """Close the open file and release any mapped view."""
        if self._mmap is not None:
            self._mmap.close()
            self._mmap = None
        if not self._handle.closed:
            self._handle.close()

    def write(self, data: bytes) -> int:
        """Reject all write calls against the evidence image."""
        raise EvidenceWriteError("Evidence images are read-only; writes are not permitted.")

    def writelines(self, lines: object) -> None:
        """Reject all line-write calls against the evidence image."""
        raise EvidenceWriteError("Evidence images are read-only; writes are not permitted.")

    def truncate(self, size: int | None = None) -> int:
        """Reject all truncate operations against the evidence image."""
        raise EvidenceWriteError("Evidence images are read-only; writes are not permitted.")

    def flush(self) -> None:
        """Flush is a no-op on a read-only file handle."""
        return None

    def __getattr__(self, name: str) -> Any:
        if name in {"write", "truncate", "writelines"}:
            raise EvidenceWriteError("Evidence images are read-only; writes are not permitted.")
        raise AttributeError(name)


def make_read_only(path: str | os.PathLike[str]) -> bool:
    """Best-effort chmod to remove write bits from a regular file."""
    try:
        candidate = Path(path).expanduser().resolve(strict=False)
    except OSError:
        return False
    if not candidate.exists() or not candidate.is_file():
        return False
    try:
        mode = os.stat(candidate).st_mode
        os.chmod(candidate, mode & ~0o222)
        return True
    except OSError:
        warnings.warn(f"Could not make read-only: {candidate}", RuntimeWarning, stacklevel=2)
        return False
