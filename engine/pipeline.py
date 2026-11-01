"""Recovery orchestrator and command-line interface."""

from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import sys
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from pydantic import ValidationError

from custody.chain import CustodyChain
from custody.verify import verify
from engine.candidates import (
    _Candidate,
    _candidate_from_carver,
    _candidate_from_fat,
    _candidate_from_fragments,
    _classify,
)
from engine.carver import CarvedFile, SignatureCarver
from engine.evidence import EvidenceImage
from engine.fat32 import Fat32Reader, RecoveryCandidate
from engine.fragments import ReconstructedFile, reconstruct_fragments
from engine.validators import validate_media
from schemas.models import CustodyLog, Results


Clock = Callable[[], datetime]
ProgressCallback = Callable[[dict[str, Any]], None]
ImageBuffer = bytes | mmap.mmap


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class PipelineOutcome:
    """Validated results and operational metrics returned by one pipeline run."""

    results: dict[str, Any]
    custody: list[dict[str, Any]]
    warnings: list[str]
    timings: dict[str, float]
    source_counts: dict[str, int]


def _output_path(out_dir: Path, requested: str | Path) -> Path:
    path = Path(requested)
    if not path.is_absolute():
        path = out_dir / path
    resolved = path.resolve()
    if not resolved.is_relative_to(out_dir.resolve()):
        raise ValueError("results and custody files must be inside the output directory")
    return resolved


def _has_signatures(image: ImageBuffer) -> bool:
    return any(image.find(signature) >= 0 for signature in (
        b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"%PDF-", b"DVRX",
    ))


def _claimed_clusters(
    candidates: list[CarvedFile],
    *,
    data_start: int,
    cluster_size: int,
    cluster_count: int,
) -> set[int]:
    result: set[int] = set()
    for candidate in candidates:
        for offset in candidate.offsets:
            first = (offset["start"] - data_start) // cluster_size + 2
            last = (offset["end"] - 1 - data_start) // cluster_size + 2
            if first < 2:
                continue
            result.update(
                cluster for cluster in range(first, last + 1)
                if cluster < cluster_count + 2
            )
    return result


def _write_json(path: Path, value: object) -> bytes:
    payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def run_pipeline(
    image_path: str | Path,
    out_dir: str | Path,
    results_name: str | Path = "results.json",
    custody_name: str | Path = "custody.json",
    *,
    progress: ProgressCallback | None = None,
    clock: Clock = _utc_now,
) -> PipelineOutcome:
    """Recover, classify, validate, and write results without modifying evidence."""
    source_path = Path(image_path)
    output_dir = Path(out_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = _output_path(output_dir, results_name)
    custody_path = _output_path(output_dir, custody_name)
    if results_path == custody_path:
        raise ValueError("results and custody paths must be different")

    timings: dict[str, float] = {}
    warnings: list[str] = []
    candidates: list[_Candidate] = []
    source_counts = {"fat32": 0, "carver": 0, "fragments": 0}
    chain = CustodyChain(clock=clock)

    def emit(
        stage: str,
        message: str,
        found_so_far: int,
        *,
        percent: int,
        event_type: str = "stage",
        file: dict[str, Any] | None = None,
    ) -> None:
        if progress is not None:
            event: dict[str, Any] = {
                "type": event_type,
                "stage": stage,
                "message": message,
                "found_so_far": found_so_far,
                "percent": percent,
            }
            if file is not None:
                event["file"] = file
            progress(event)

    evidence_started = time.perf_counter()
    with EvidenceImage(source_path) as evidence:
        timings["evidence"] = time.perf_counter() - evidence_started
        emit("evidence", f"Opened read-only image ({evidence.size_bytes} bytes)", 0, percent=2)
        mapped = evidence.map_readonly() if evidence.size_bytes else None
        image_context = mapped if mapped is not None else nullcontext(b"")
        with image_context as image:
            fs_started = time.perf_counter()
            reader: Fat32Reader | None = None
            fat_files: list[RecoveryCandidate] = []
            fs_type = "unrecognized_filesystem"
            if evidence.size_bytes:
                try:
                    reader = Fat32Reader(
                        image, lambda kind, data: validate_media(kind, data).ok
                    )
                    fat_files = reader.recover()
                    fs_type = "FAT32"
                except ValueError as error:
                    warnings.append("unrecognized_filesystem")
                    warnings.append(str(error))
            else:
                warnings.append("unrecognized_filesystem")
            timings["filesystem"] = time.perf_counter() - fs_started
            opened_details: dict[str, Any] = {
                "path": source_path.name,
                "size_bytes": evidence.size_bytes,
                "sha256": evidence.sha256,
            }
            if fs_type != "FAT32":
                opened_details["warning"] = "unrecognized_filesystem"
            chain.append("IMAGE_OPENED", opened_details)
            chain.append("FILESYSTEM_PARSED", {
                "fs_type": fs_type,
                "live_count": reader.live_count if reader else 0,
                "deleted_count": reader.deleted_count if reader else 0,
                "warnings": list(reader.warnings) if reader else [],
            })
            if reader is not None:
                warnings.extend(reader.warnings)
                candidates.extend(_candidate_from_fat(item) for item in fat_files)
                source_counts["fat32"] = len(fat_files)
            emit("filesystem", f"Parsed {fs_type}", len(candidates), percent=15)

            carving_started = time.perf_counter()
            claimed_ranges = [
                offset for item in fat_files for offset in item.offsets
            ]
            excluded_ranges = []
            if reader is not None:
                excluded_ranges = [
                    {
                        "start": reader.bpb.data_start
                        + (hint.start_cluster - 2) * reader.bpb.cluster_size,
                        "end": reader.bpb.data_start
                        + (hint.start_cluster - 2) * reader.bpb.cluster_size + 3,
                    }
                    for hint in reader.hints
                ]
            should_carve = fs_type == "FAT32" or _has_signatures(image)
            carved = SignatureCarver(
                claimed_ranges=claimed_ranges, excluded_ranges=excluded_ranges
            ).carve(image) if should_carve else []
            timings["carving"] = time.perf_counter() - carving_started
            chain.append("CARVING_DONE", {"files_found": len(carved)})
            candidates.extend(_candidate_from_carver(item) for item in carved)
            source_counts["carver"] = len(carved)
            emit("carving", f"Carving found {len(carved)} file(s)", len(candidates), percent=40)

            fragments_started = time.perf_counter()
            fragments: list[ReconstructedFile] = []
            if reader is not None:
                claimed = set(reader.claimed_clusters)
                claimed.update(_claimed_clusters(
                    carved, data_start=reader.bpb.data_start,
                    cluster_size=reader.bpb.cluster_size,
                    cluster_count=reader.bpb.cluster_count,
                ))
                fragments = reconstruct_fragments(
                    image, reader.hints, data_start=reader.bpb.data_start,
                    cluster_size=reader.bpb.cluster_size,
                    cluster_count=reader.bpb.cluster_count,
                    claimed_clusters=claimed,
                )
            timings["fragments"] = time.perf_counter() - fragments_started
            chain.append("FRAGMENTS_JOINED", {
                "files_found": len(fragments),
                "search_cost": sum(item.search_cost for item in fragments),
            })
            candidates.extend(_candidate_from_fragments(item) for item in fragments)
            source_counts["fragments"] = len(fragments)
            emit("fragments", f"Fragment search found {len(fragments)} file(s)", len(candidates), percent=60)

        classification_started = time.perf_counter()

        def emit_classified(item: dict[str, Any], index: int, total: int) -> None:
            percent = 65 + round(30 * index / max(total, 1))
            emit(
                "classification",
                f"Classified {item['name'] or item['id']}",
                index,
                percent=percent,
                event_type="file_found",
                file={
                    "id": item["id"],
                    "name": item["name"],
                    "type": item["type"],
                    "classification": item["classification"],
                    "confidence": item["confidence"],
                },
            )

        classified, class_counts = _classify(candidates, emit_classified)
        timings["classification"] = time.perf_counter() - classification_started

        generated_at = clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        result_data = {
            "schema_version": "1.0",
            "case_id": f"case-{evidence.sha256[:12]}",
            "tool_version": "0.1.0",
            "generated_at": generated_at,
            "image": {
                "path": source_path.name,
                "sha256": evidence.sha256,
                "size_bytes": evidence.size_bytes,
            },
            "files": classified,
            "summary": {
                "total": len(classified),
                "by_classification": class_counts,
            },
        }

        write_started = time.perf_counter()
        chain.append("FILES_CLASSIFIED", class_counts)
        for item, candidate in zip(
            classified,
            sorted(candidates, key=lambda item: item.offsets[0]["start"]),
        ):
            output_file = output_dir / item["output_path"]
            output_file.write_bytes(candidate.data)
        validated_results = Results.model_validate(result_data).model_dump(mode="json")
        results_bytes = _write_json(results_path, validated_results)
        chain.append("RESULTS_WRITTEN", {
            "path": results_path.relative_to(output_dir).as_posix(),
            "sha256": hashlib.sha256(results_bytes).hexdigest(),
        })
        timings["write"] = time.perf_counter() - write_started
        emit("classification", f"Classified {len(classified)} file(s)", len(classified), percent=96)

        reverify_started = time.perf_counter()
        hash_equal = evidence.reverify()
        chain.append("IMAGE_REVERIFIED", {"hash_equal": hash_equal})
        verified_chain = chain.entries
        custody_model = CustodyLog.model_validate(verified_chain)
        if not verify(verified_chain)["ok"]:
            raise RuntimeError("generated custody chain failed self-verification")
        _write_json(custody_path, custody_model.model_dump(mode="json"))
        timings["reverification"] = time.perf_counter() - reverify_started
        emit("reverification", f"Evidence hash unchanged: {hash_equal}", len(classified), percent=100)
        if not hash_equal:
            raise RuntimeError("evidence image changed during recovery")

    return PipelineOutcome(
        results=validated_results,
        custody=verified_chain,
        warnings=warnings,
        timings=timings,
        source_counts=source_counts,
    )


def _print_event(event: dict[str, str | int], jsonl: bool) -> None:
    if jsonl:
        print(json.dumps(event, sort_keys=True))
    else:
        print(
            f"{event['stage']}: {event['message']} "
            f"(found {event['found_so_far']})"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the recovery pipeline CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--results", default="results.json")
    parser.add_argument("--custody", default="custody.json")
    parser.add_argument("--progress", choices=("jsonl",))
    args = parser.parse_args(argv)
    try:
        outcome = run_pipeline(
            args.image, args.out, args.results, args.custody,
            progress=lambda event: _print_event(event, args.progress == "jsonl"),
        )
    except (OSError, ValueError, ValidationError, RuntimeError) as error:
        print(f"recovery failed: {error}", file=sys.stderr)
        return 2
    for warning in outcome.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for stage, seconds in outcome.timings.items():
        print(f"{stage} took {seconds:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
