"""Candidate normalization and result classification for the recovery pipeline."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from PIL import Image
from pypdf import PdfReader

from engine.carver import CarvedFile
from engine.classifier import classify_file
from engine.dvrlike import DVRXParser
from engine.fat32 import RecoveryCandidate
from engine.fragments import ReconstructedFile


@dataclass(frozen=True)
class _Candidate:
    source: str
    file_type: str
    data: bytes
    offsets: list[dict[str, int]]
    name: str | None
    state: str
    timestamps: dict[str, str | None]
    metadata: dict[str, Any]
    dir_entry_present: bool
    full_chain: bool
    search_cost: int = 0


def _candidate_from_fat(item: RecoveryCandidate) -> _Candidate:
    return _Candidate(
        source="fat32", file_type=item.file_type, data=item.data,
        offsets=item.offsets, name=item.name, state=item.state,
        timestamps=item.timestamps, metadata={}, dir_entry_present=True,
        full_chain=item.state == "live",
    )


def _candidate_from_carver(item: CarvedFile) -> _Candidate:
    return _Candidate(
        source="carver", file_type=item.file_type, data=item.data,
        offsets=item.offsets, name=None, state="carved",
        timestamps={"created": None, "modified": None, "accessed": None},
        metadata={}, dir_entry_present=False, full_chain=False,
    )


def _candidate_from_fragments(item: ReconstructedFile) -> _Candidate:
    return _Candidate(
        source="fragments", file_type=item.file_type, data=item.data,
        offsets=item.offsets, name=item.name, state="deleted_fragmented",
        timestamps=item.timestamps,
        metadata={"search_cost": item.search_cost},
        dir_entry_present=item.name is not None, full_chain=False,
        search_cost=item.search_cost,
    )


def _media_metadata(candidate: _Candidate) -> tuple[dict[str, Any], list[str]]:
    metadata = dict(candidate.metadata)
    warnings: list[str] = []
    timestamp: datetime | None = None
    label = ""
    if candidate.file_type == "jpeg":
        with Image.open(io.BytesIO(candidate.data)) as image:
            value = image.getexif().get(36867)
        if value:
            label = "exif_datetime_original"
            timestamp = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
    elif candidate.file_type == "pdf":
        value = PdfReader(io.BytesIO(candidate.data)).metadata
        creation_date = value.creation_date if value else None
        if creation_date:
            label = "pdf_creation_date"
            timestamp = creation_date
    if timestamp is not None:
        metadata[label] = timestamp.isoformat().replace("+00:00", "Z")
        fat_modified = candidate.timestamps.get("modified")
        if timestamp.year < 1980 or timestamp > datetime.now(timezone.utc):
            warnings.append(f"timestamp_out_of_range:{label}")
        if fat_modified:
            fat_time = datetime.fromisoformat(fat_modified.replace("Z", "+00:00"))
            if abs((timestamp - fat_time).total_seconds()) > 2:
                warnings.append("fat_time_disagrees_with_media_timestamp")
    return metadata, warnings


def _classify(
    candidates: list[_Candidate],
    on_classified: Callable[[dict[str, Any], int, int], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    files = []
    counts = {name: 0 for name in ("intact", "carved", "reconstructed", "partial")}
    seen_hashes: set[str] = set()
    for index, candidate in enumerate(
        sorted(candidates, key=lambda item: item.offsets[0]["start"]), 1
    ):
        digest = hashlib.sha256(candidate.data).hexdigest()
        duplicate = digest in seen_hashes
        seen_hashes.add(digest)
        classification = classify_file(
            candidate.source, state=candidate.state,
            dir_entry_present=candidate.dir_entry_present,
            validation_ok=True, full_chain=candidate.full_chain,
            search_cost=candidate.search_cost, duplicate=duplicate,
            unusually_small=len(candidate.data) <= 512,
        )
        counts[classification.classification] += 1
        extension = {"jpeg": "jpg", "dvr": "dvr"}.get(candidate.file_type, candidate.file_type)
        output_path = f"f-{index:03d}.{extension}"
        metadata, warnings = _media_metadata(candidate)
        if candidate.file_type == "dvr":
            metadata.update(DVRXParser().parse(candidate.data).metadata)
        file_data = {
            "id": f"f-{index:03d}",
            "name": candidate.name,
            "type": candidate.file_type,
            "source": candidate.source,
            "stage": {"fat32": "fat32", "carver": "carving", "fragments": "fragments"}[candidate.source],
            "classification": classification.classification,
            "confidence": classification.confidence,
            "reason": classification.reason,
            "offsets": candidate.offsets,
            "size_bytes": len(candidate.data),
            "sha256": digest,
            "output_path": output_path,
            "timestamps": candidate.timestamps,
            "metadata": metadata,
            "warnings": warnings,
        }
        files.append(file_data)
        if on_classified is not None:
            on_classified(file_data, index, len(candidates))
    return files, counts
