"""Writer for the documented synthetic DVRX container (not a vendor format)."""

from __future__ import annotations

import struct
import zlib
from datetime import datetime, timedelta, timezone

from testgen.content import make_jpeg, validate_payload

HEADER = struct.Struct("<4sHHI")
FRAME = struct.Struct("<4sIQI")


def iso_utc(timestamp_ms: int) -> str:
    """Format Unix milliseconds as an ISO-8601 UTC timestamp."""
    value = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def make_clip(seed: int, *, channel: int = 1, frame_count: int | None = None) -> tuple[bytes, dict[str, object]]:
    """Create a deterministic 20-40 frame DVRX clip and its public metadata."""
    count = frame_count if frame_count is not None else 20 + seed % 21
    if not 20 <= count <= 40:
        raise ValueError("DVRX clips must contain 20 to 40 frames")
    start = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc) + timedelta(minutes=seed % 60)
    start_ms = int(start.timestamp() * 1000)
    output = bytearray(HEADER.pack(b"DVRX", 1, channel, 0))
    for index in range(count):
        payload = make_jpeg(seed * 100 + index, compact=True)
        validate_payload("jpeg", payload)
        if not 2_000 <= len(payload) <= 4 * 1024:
            raise ValueError(f"DVRX frame payload outside 2-4 KiB: {len(payload)}")
        timestamp = start_ms + index * 1000
        output.extend(FRAME.pack(b"FRM0", index, timestamp, len(payload)))
        output.extend(payload)
        output.extend(struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF))
    metadata: dict[str, object] = {
        "frame_count": count,
        "start_time": iso_utc(start_ms),
        "end_time": iso_utc(start_ms + (count - 1) * 1000),
    }
    return bytes(output), metadata
