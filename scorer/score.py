"""Validate and score a recovery result against generator ground truth."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from pydantic import ValidationError

from schemas.models import GroundTruth, Results, Score
from scorer.matching import match_files
from scorer.metrics import completeness, false_positive_rate, precision, ratio, recall

BUCKETS = [(0.0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.0)]


def _time_equal(expected: str | None, actual: str | None, tolerance: int) -> bool:
    if expected is None or actual is None:
        return expected == actual
    try:
        left = datetime.fromisoformat(expected.replace("Z", "+00:00"))
        right = datetime.fromisoformat(actual.replace("Z", "+00:00"))
        if left.tzinfo is None:
            left = left.replace(tzinfo=timezone.utc)
        if right.tzinfo is None:
            right = right.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return abs((left - right).total_seconds()) <= tolerance


def _metadata_counts(
    entry: dict[str, Any], item: dict[str, Any] | None, *,
    deleted_name: bool,
) -> tuple[int, int]:
    correct = total = 0
    expected_name = entry["name"].casefold()
    actual_name = ((item.get("name") or "").casefold()) if item else ""
    valid_names = {expected_name}
    if deleted_name and expected_name:
        valid_names.add("_" + expected_name[1:])
    total += 1
    correct += actual_name in valid_names
    expected_timestamps = entry.get("fs_timestamps") or {}
    got_timestamps = (item.get("timestamps") or {}) if item else {}
    for key, expected in expected_timestamps.items():
        if expected is None:
            continue
        total += 1
        correct += _time_equal(expected, got_timestamps.get(key), 2)
    expected_metadata = entry.get("metadata") or {}
    if entry["type"] == "dvr":
        got_metadata = (item.get("metadata") or {}) if item else {}
        for key in ("frame_count", "start_time", "end_time"):
            if key not in expected_metadata:
                continue
            total += 1
            if key == "frame_count":
                correct += got_metadata.get(key) == expected_metadata[key]
            else:
                correct += _time_equal(expected_metadata[key], got_metadata.get(key), 1)
    return correct, total


def score_case(
    truth_data: dict[str, Any], result_data: dict[str, Any],
    recovered_dir: str | Path, image_path: str | Path,
) -> Score:
    """Validate contracts and calculate all declared recovery metrics."""
    truth = GroundTruth.model_validate(truth_data).model_dump()
    results = Results.model_validate(result_data).model_dump()
    image = Path(image_path).read_bytes()
    matches, false_positive_indices, _ = match_files(
        truth, results, recovered_dir, image
    )
    expected_count = sum(entry["recoverable"] for entry in truth["files"])
    per_file = []
    exact_count = 0
    metadata_correct = metadata_total = 0
    classification_correct = classification_total = 0
    matched_result_indices = {match.result_index for match in matches.values()}
    for truth_index, entry in enumerate(truth["files"]):
        match = matches.get(truth_index)
        if not entry["recoverable"]:
            per_file.append({
                "ground_truth_id": entry["id"], "name": entry["name"], "status": "unrecoverable",
                "completeness": 0.0, "classification_expected": entry["expected_classification"],
                "classification_got": None, "confidence": None, "matched_result_id": None,
            })
            continue
        metadata_ok, metadata_fields = _metadata_counts(
            entry, results["files"][match.result_index] if match else None,
            deleted_name=entry["state"] in (
                "deleted_contiguous", "deleted_fragmented", "dvr_deleted"
            ),
        )
        metadata_correct += metadata_ok
        metadata_total += metadata_fields
        if match is None:
            per_file.append({
                "ground_truth_id": entry["id"], "name": entry["name"], "status": "missed",
                "completeness": 0.0, "classification_expected": entry["expected_classification"],
                "classification_got": None, "confidence": None, "matched_result_id": None,
            })
            continue
        item = results["files"][match.result_index]
        confidence = item["confidence"]
        if match.status == "exact":
            exact_count += 1
        classification_total += 1
        class_correct = item["classification"] in entry["acceptable_classifications"]
        classification_correct += class_correct
        per_file.append({
            "ground_truth_id": entry["id"], "name": entry["name"], "status": match.status,
            "completeness": match.completeness,
            "classification_expected": entry["expected_classification"],
            "classification_got": item["classification"], "confidence": confidence,
            "matched_result_id": item["id"],
        })
    false_positives = len(false_positive_indices)
    recovered_count = len(matches)
    overconfident = sum(
        results["files"][index]["confidence"] >= 0.8
        for index in false_positive_indices
    )
    bucket_data = []
    for lower, upper in BUCKETS:
        indices = [
            index for index, item in enumerate(results["files"])
            if lower <= item["confidence"] < upper or (upper == 1.0 and item["confidence"] == 1.0)
        ]
        correct = sum(index in matched_result_indices for index in indices)
        bucket_data.append({
            "lower": lower, "upper": upper, "count": len(indices),
            "correct_rate": correct / len(indices) if indices else None,
        })
    integrity = hashlib.sha256(image).hexdigest() == truth["image"]["sha256"]
    return Score(
        recovered=recovered_count, expected=expected_count,
        precision=precision(recovered_count, false_positives),
        completeness=completeness(
            [item["completeness"] for item in per_file if item["status"] != "unrecoverable"],
            expected_count,
        ),
        recall=recall(exact_count, expected_count), false_positives=false_positives,
        false_positive_rate=false_positive_rate(false_positives, len(results["files"])),
        metadata_accuracy=ratio(metadata_correct, metadata_total),
        classification_accuracy=ratio(classification_correct, classification_total),
        overconfident_errors=overconfident, image_integrity_ok=integrity,
        per_file=per_file, calibration=bucket_data,
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _print_score(score: Score) -> None:
    print(f"{'ID':<14} {'NAME':<22} {'STATUS':<12} {'COMPLETE':>9} {'CLASSIFICATION':<28} {'CONF':>6}")
    for item in score.per_file:
        got = item.classification_got or "-"
        expected = item.classification_expected
        confidence = "-" if item.confidence is None else f"{item.confidence:.2f}"
        print(
            f"{item.ground_truth_id:<14} {item.name:<22} {item.status:<12} "
            f"{item.completeness:>8.1%} {expected + ' -> ' + got:<28} {confidence:>6}"
        )
    print("\nSummary")
    for label, value in (
        ("Recovered", f"{score.recovered}/{score.expected}"),
        ("Precision", f"{score.precision:.1%}"), ("Recall (exact)", f"{score.recall:.1%}"),
        ("Completeness", f"{score.completeness:.1%}"),
        ("False positives", str(score.false_positives)),
        ("False-positive rate", f"{score.false_positive_rate:.1%}"),
        ("Metadata accuracy", f"{score.metadata_accuracy:.1%}"),
        ("Classification accuracy", f"{score.classification_accuracy:.1%}"),
        ("Overconfident errors", str(score.overconfident_errors)),
        ("Image integrity", "OK" if score.image_integrity_ok else "FAILED"),
    ):
        print(f"  {label:<24} {value}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the scorer CLI and optionally enforce evidence integrity."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--recovered-dir", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--json", type=Path, default=Path("score.json"))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        truth = _load_json(args.truth)
        results = _load_json(args.results)
        score = score_case(truth, results, args.recovered_dir, args.image)
    except ValidationError as error:
        print("Schema validation failed:", file=sys.stderr)
        for issue in error.errors():
            path = ".".join(str(part) for part in issue["loc"])
            print(f"  {path}: {issue['msg']}", file=sys.stderr)
        return 2
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    _print_score(score)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(score.model_dump(), indent=2) + "\n", encoding="utf-8")
    if args.strict and not score.image_integrity_ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
