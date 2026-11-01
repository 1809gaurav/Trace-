"""Parser for the documented synthetic DVRX container format."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from engine.config import DVR_MAX_FRAME_BYTES


HEADER_SIZE = 12
FRAME_HEADER_SIZE = 20
CRC_SIZE = 4


@dataclass(frozen=True)
class DvrParseResult:
    """Valid frame prefix and metadata parsed from a DVRX byte sequence."""

    ok: bool
    frame_count: int
    metadata: dict[str, int | str | None]
    frame_payloads: tuple[bytes, ...]
    bytes_consumed: int
    warnings: tuple[str, ...]


@runtime_checkable
class ContainerParser(Protocol):
    """Minimal interface implemented by supported container parsers."""

    def detect(self, data: bytes) -> bool:
        """Return whether ``data`` begins with this container signature."""

    def parse(self, data: bytes) -> DvrParseResult:
        """Parse valid content and retain the prefix before the first error."""


def _iso_utc(timestamp_ms: int) -> str | None:
    try:
        value = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class DVRXParser:
    """Validate DVRX headers, frame continuity, and per-frame CRC-32."""

    def detect(self, data: bytes) -> bool:
        """Recognize the synthetic DVRX magic without implying validity."""
        return data.startswith(b"DVRX")  # header magic @0x00, 4 bytes

    def parse(self, data: bytes) -> DvrParseResult:
        """Return valid frames before EOF or the first malformed record."""
        if len(data) < HEADER_SIZE:
            return self._invalid("truncated DVRX header")
        magic = data[0:4]  # header magic @0x00, 4 bytes
        version, _channel = struct.unpack_from("<HH", data, 4)  # version/channel @0x04, 2 bytes each LE
        reserved = struct.unpack_from("<I", data, 8)[0]  # reserved @0x08, 4 bytes LE
        if magic != b"DVRX" or version != 1 or reserved != 0:
            return self._invalid("invalid DVRX header")

        payloads: list[bytes] = []
        timestamps: list[int] = []
        warnings: list[str] = []
        offset = HEADER_SIZE
        expected_index = 0
        while offset < len(data):
            if len(data) - offset < FRAME_HEADER_SIZE + CRC_SIZE:
                warnings.append(f"truncated frame header at byte {offset}")
                break
            magic = data[offset:offset + 4]  # frame magic @record+0x00, 4 bytes
            frame_index = struct.unpack_from("<I", data, offset + 4)[0]  # frame index @record+0x04, 4 bytes LE
            timestamp_ms = struct.unpack_from("<Q", data, offset + 8)[0]  # timestamp_ms @record+0x08, 8 bytes LE
            payload_length = struct.unpack_from("<I", data, offset + 16)[0]  # payload_len @record+0x10, 4 bytes LE
            if magic != b"FRM0":
                warnings.append(f"invalid frame magic at byte {offset}")
                break
            if frame_index != expected_index:
                warnings.append(f"frame index discontinuity at byte {offset}")
                break
            if payload_length > DVR_MAX_FRAME_BYTES:
                warnings.append(f"frame payload exceeds limit at byte {offset}")
                break
            payload_start = offset + FRAME_HEADER_SIZE
            payload_end = payload_start + payload_length
            record_end = payload_end + CRC_SIZE
            if record_end > len(data):
                warnings.append(f"truncated frame payload at byte {offset}")
                break
            if timestamps and timestamp_ms <= timestamps[-1]:
                warnings.append(f"non-increasing timestamp at byte {offset}")
                break
            payload = data[payload_start:payload_end]
            expected_crc = struct.unpack_from("<I", data, payload_end)[0]  # frame CRC @payload end, 4 bytes LE
            actual_crc = zlib.crc32(payload) & 0xFFFFFFFF
            if actual_crc != expected_crc:
                warnings.append(f"frame CRC mismatch at byte {offset}")
                break
            payloads.append(payload)
            timestamps.append(timestamp_ms)
            expected_index += 1
            offset = record_end

        metadata: dict[str, int | str | None] = {
            "frame_count": len(payloads),
            "start_time": _iso_utc(timestamps[0]) if timestamps else None,
            "end_time": _iso_utc(timestamps[-1]) if timestamps else None,
        }
        return DvrParseResult(
            ok=bool(payloads), frame_count=len(payloads), metadata=metadata,
            frame_payloads=tuple(payloads), bytes_consumed=offset, warnings=tuple(warnings),
        )

    @staticmethod
    def _invalid(reason: str) -> DvrParseResult:
        return DvrParseResult(
            ok=False, frame_count=0,
            metadata={"frame_count": 0, "start_time": None, "end_time": None},
            frame_payloads=(), bytes_consumed=0, warnings=(reason,),
        )


PARSERS: tuple[ContainerParser, ...] = (DVRXParser(),)
