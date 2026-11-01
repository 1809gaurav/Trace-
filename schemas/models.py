"""Pydantic contracts shared by the generator, recovery engine, and scorer."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

FileType = Literal["jpeg", "png", "pdf", "mp4", "dvr", "unknown"]
Source = Literal["fat32", "carver", "fragments", "dvrlike"]
Classification = Literal["intact", "carved", "reconstructed", "partial"]
FileState = Literal[
    "live", "deleted_contiguous", "deleted_fragmented",
    "fs_corrupted_contiguous", "overwritten_partial", "dvr_live", "dvr_deleted",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Offset(Contract):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def end_not_before_start(self) -> Offset:
        """Ensure byte ranges are ordered and end-exclusive."""
        if self.end < self.start:
            raise ValueError("end must be greater than or equal to start")
        return self


class Timestamps(Contract):
    created: str | None = None
    modified: str | None = None
    accessed: str | None = None


class ResultImage(Contract):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class RecoveredFile(Contract):
    id: str
    name: str | None
    type: FileType
    source: Source
    stage: str
    classification: Classification
    confidence: float = Field(ge=0, le=1)
    reason: str
    offsets: list[Offset]
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_path: str
    timestamps: Timestamps
    metadata: dict[str, Any]
    warnings: list[str]


class ResultsSummary(Contract):
    total: int = Field(ge=0)
    by_classification: dict[str, int]


class Results(Contract):
    schema_version: Literal["1.0"]
    case_id: str
    tool_version: str
    generated_at: str
    image: ResultImage
    files: list[RecoveredFile]
    summary: ResultsSummary


class CustodyEntry(Contract):
    index: int = Field(ge=0)
    time: str
    step: str
    details: dict[str, Any]
    prev_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class CustodyLog(RootModel[list[CustodyEntry]]):
    """Top-level custody.json list."""

    @model_validator(mode="after")
    def validate_hash_chain(self) -> CustodyLog:
        """Verify the zero-rooted hash chain represented by the entry list."""
        previous = "0" * 64
        for entry in self.root:
            if entry.prev_hash != previous:
                raise ValueError(f"custody entry {entry.index} has an invalid prev_hash")
            expected = compute_entry_hash(previous, entry.step, entry.details)
            if entry.hash != expected:
                raise ValueError(f"custody entry {entry.index} has an invalid hash")
            previous = entry.hash
        return self


class GroundTruthImage(Contract):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    bytes_per_sector: int = Field(gt=0)
    sectors_per_cluster: int = Field(gt=0)
    cluster_size: int = Field(gt=0)
    data_start_offset: int = Field(ge=0)


class GroundTruthFile(Contract):
    id: str
    name: str
    type: FileType
    original_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    state: FileState
    recoverable: bool
    fragments: list[Offset]
    dir_entry_present: bool
    fs_timestamps: Timestamps
    expected_via: Literal["fat32", "carving", "reconstruction", "none"]
    expected_classification: Classification
    acceptable_classifications: list[Classification]
    metadata: dict[str, Any]


class Decoy(Contract):
    id: str
    kind: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class GroundTruth(Contract):
    schema_version: Literal["1.0"]
    scenario: str
    seed: int
    pillow_version: str
    image: GroundTruthImage
    files: list[GroundTruthFile]
    decoys: list[Decoy] = Field(default_factory=list)
    expected_error: str | None = None


class PerFileScore(Contract):
    ground_truth_id: str
    name: str
    status: Literal["exact", "partial", "missed", "unrecoverable"]
    completeness: float = Field(ge=0, le=1)
    classification_expected: str
    classification_got: str | None
    confidence: float | None = Field(default=None, ge=0, le=1)
    matched_result_id: str | None = None


class CalibrationBucket(Contract):
    lower: float = Field(ge=0, le=1)
    upper: float = Field(ge=0, le=1)
    count: int = Field(ge=0)
    correct_rate: float | None = Field(default=None, ge=0, le=1)


class Score(Contract):
    recovered: int = Field(ge=0)
    expected: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    false_positives: int = Field(ge=0)
    false_positive_rate: float = Field(ge=0, le=1)
    metadata_accuracy: float = Field(ge=0, le=1)
    classification_accuracy: float = Field(ge=0, le=1)
    overconfident_errors: int = Field(ge=0)
    image_integrity_ok: bool
    per_file: list[PerFileScore]
    calibration: list[CalibrationBucket]


def compute_entry_hash(prev_hash: str, step: str, details: dict[str, Any]) -> str:
    """Return the SHA-256 chain hash for a custody event."""
    canonical = json.dumps(details, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{prev_hash}{step}{canonical}".encode("utf-8")).hexdigest()


def export_json_schemas(directory: str = "schemas") -> None:
    """Write all public JSON Schema contracts into the given directory."""
    from pathlib import Path

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    for model, filename in (
        (Results, "results.schema.json"),
        (CustodyLog, "custody.schema.json"),
        (GroundTruth, "ground_truth.schema.json"),
        (Score, "score.schema.json"),
    ):
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        (root / filename).write_text(
            json.dumps(schema, indent=1) + "\n", encoding="utf-8"
        )
