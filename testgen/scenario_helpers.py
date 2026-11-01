"""Reusable file, fragment, and pristine-volume helpers for scenarios."""

from __future__ import annotations

import hashlib
import math
import tempfile
from pathlib import Path
from typing import Any

from testgen.content import make_jpeg, make_pdf, make_png, validate_payload, write_original
from testgen.fat32_writer import Fat32Image

FIXED_TIME = "2026-01-01T10:00:00Z"
CLUSTER = Fat32Image.CLUSTER_SIZE


def data_start_offset() -> int:
    """Calculate the raw image offset of the first data sector."""
    sectors = 1
    while True:
        clusters = (Fat32Image.TOTAL_SECTORS - Fat32Image.RESERVED_SECTORS
                    - Fat32Image.FAT_COUNT * sectors) // Fat32Image.SECTORS_PER_CLUSTER
        needed = math.ceil((clusters + 2) * 4 / Fat32Image.SECTOR_SIZE)
        if sectors == needed:
            return (Fat32Image.RESERVED_SECTORS + Fat32Image.FAT_COUNT * sectors) * Fat32Image.SECTOR_SIZE
        sectors = needed


def payload(file_type: str, seed: int) -> bytes:
    """Generate and return a supported media payload."""
    if file_type == "jpeg":
        result = make_jpeg(seed)
    elif file_type == "png":
        result = make_png(seed)
    elif file_type == "pdf":
        result = make_pdf(seed)
    else:
        raise ValueError(f"unsupported payload type: {file_type}")
    validate_payload(file_type, result)
    return result


def entry(
    identifier: str, name: str, file_type: str, data: bytes, state: str,
    ranges: list[dict[str, int]], *, recoverable: bool = True,
    expected_via: str = "fat32", classification: str = "intact",
    acceptable: list[str] | None = None, dir_entry: bool = True,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create one ground-truth file record."""
    return {
        "id": identifier, "name": name, "type": file_type,
        "original_sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data), "state": state, "recoverable": recoverable,
        "fragments": ranges, "dir_entry_present": dir_entry,
        "fs_timestamps": {
            "created": FIXED_TIME, "modified": FIXED_TIME,
            "accessed": "2026-01-01T00:00:00Z",
        },
        "expected_via": expected_via, "expected_classification": classification,
        "acceptable_classifications": acceptable or [classification],
        "metadata": metadata or {},
    }


def add_file(
    writer: Fat32Image, out: Path, identifier: str, name: str, file_type: str,
    data: bytes, *, clusters: list[int] | None = None,
    metadata: dict[str, Any] | None = None, state: str = "live",
    recoverable: bool = True, via: str = "fat32", classification: str = "intact",
    acceptable: list[str] | None = None, dir_entry: bool = True,
    original: bytes | None = None,
) -> dict[str, Any]:
    """Write a file and construct its matching ground-truth record."""
    if original is None and file_type in ("jpeg", "png", "pdf"):
        validate_payload(file_type, data)
    source = original if original is not None else data
    allocation = writer.write_file(
        name, data, clusters=clusters, timestamps={"modified": FIXED_TIME}
    )
    ranges = [{"start": allocation.start_offset, "end": allocation.start_offset + len(data)}]
    write_original(out / "originals" / name, source)
    return entry(
        identifier, name, file_type, source, state, ranges, recoverable=recoverable,
        expected_via=via, classification=classification, acceptable=acceptable,
        dir_entry=dir_entry, metadata=metadata,
    )


def fragmented_clusters(
    cursor: int, data: bytes, *, pieces: int,
) -> tuple[list[int], list[list[int]], int]:
    """Choose deterministic file-order cluster groups with noise gaps."""
    count = max(3, (len(data) + CLUSTER - 1) // CLUSTER)
    sizes = [count // pieces] * pieces
    for index in range(count % pieces):
        sizes[index] += 1
    groups = []
    current = cursor
    for index, size in enumerate(sizes):
        groups.append(list(range(current, current + size)))
        current += size
        if index < pieces - 1:
            current += 3 + index % 4
    return [cluster for group in groups for cluster in group], groups, current + 4


def ranges_for_groups(
    writer: Fat32Image, groups: list[list[int]], size: int,
) -> list[dict[str, int]]:
    """Map logical fragments to absolute image byte ranges."""
    remaining = size
    result = []
    for group in groups:
        start = writer.cluster_offset(group[0])
        used = min(remaining, len(group) * CLUSTER)
        result.append({"start": start, "end": start + used})
        remaining -= used
    return result


def validate_pristine(writer: Fat32Image, scenario_dir: Path) -> None:
    """Run internal and optional external checks before a scenario is damaged."""
    writer.validate()
    with tempfile.NamedTemporaryFile(
        prefix=".pristine-", suffix=".img", dir=scenario_dir, delete=False
    ) as handle:
        path = Path(handle.name)
    try:
        writer.save(path)
        writer.validate_saved(path)
    finally:
        path.unlink(missing_ok=True)


def regular_set() -> list[tuple[str, str]]:
    """Return the common 8 JPEG, 3 PDF, and 2 PNG fixture set."""
    return (
        [(f"IMG_{index:04d}.JPG", "jpeg") for index in range(1, 9)]
        + [(f"DOC{index:04d}.PDF", "pdf") for index in range(1, 4)]
        + [(f"PIC{index:04d}.PNG", "png") for index in range(1, 3)]
    )
