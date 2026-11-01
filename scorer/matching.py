"""One-to-one matching of recovered items against image-derived ground truth."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FileMatch:
    """A recovered-to-ground-truth assignment and its measured completeness."""

    truth_index: int
    result_index: int
    status: str
    completeness: float


def _read_recovered(item: dict[str, Any], root: Path) -> bytes | None:
    output = item.get("output_path")
    if not output:
        return None
    base = root.resolve()
    path = (base / output).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        return None
    return path.read_bytes()


def _expected_bytes(entry: dict[str, Any], image: bytes) -> bytes:
    pieces = []
    for fragment in entry["fragments"]:
        start, end = fragment["start"], fragment["end"]
        if end > len(image):
            return b""
        pieces.append(image[start:end])
    return b"".join(pieces)[:entry["size_bytes"]]


def block_completeness(expected: bytes, recovered: bytes) -> float:
    """Hash 512-byte blocks and count same-index, in-order original block matches."""
    if not expected:
        return 0.0
    expected_hashes: dict[bytes, list[int]] = {}
    for index, start in enumerate(range(0, len(expected), 512)):
        digest = hashlib.sha256(expected[start:start + 512]).digest()
        expected_hashes.setdefault(digest, []).append(index)
    matched = 0
    previous_position = -1
    for recovered_index, start in enumerate(range(0, len(recovered), 512)):
        digest = hashlib.sha256(recovered[start:start + 512]).digest()
        positions = expected_hashes.get(digest, [])
        if recovered_index in positions and recovered_index > previous_position:
            matched += 1
            previous_position = recovered_index
    return matched / ((len(expected) + 511) // 512)


def _overlap_bytes(offsets: list[dict[str, int]], fragments: list[dict[str, int]]) -> int:
    intersections = []
    for offset in offsets:
        for fragment in fragments:
            start = max(offset["start"], fragment["start"])
            end = min(offset["end"], fragment["end"])
            if end > start:
                intersections.append((start, end))
    intersections.sort()
    merged: list[list[int]] = []
    for start, end in intersections:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(end - start for start, end in merged)


def match_files(
    truth: dict[str, Any], results: dict[str, Any], recovered_dir: str | Path, image: bytes,
) -> tuple[dict[int, FileMatch], set[int], list[bytes | None]]:
    """Assign result items to recoverable ground-truth files at most once."""
    root = Path(recovered_dir)
    original_indices = [
        index for index, item in enumerate(truth["files"]) if item["recoverable"]
    ]
    entries = [truth["files"][index] for index in original_indices]
    recovered = results["files"]
    recovered_bytes = [_read_recovered(item, root) for item in recovered]
    expectations = [_expected_bytes(item, image) for item in entries]
    possibilities = []
    for local_truth_index, (entry, expected) in enumerate(zip(entries, expectations)):
        if hashlib.sha256(expected).hexdigest() != entry["original_sha256"]:
            # A corrupted/unavailable source range cannot establish content equality.
            expected = b""
            expectations[local_truth_index] = expected
        for result_index, (item, content) in enumerate(zip(recovered, recovered_bytes)):
            if content is None or hashlib.sha256(content).hexdigest() != item["sha256"]:
                continue
            exact = hashlib.sha256(content).hexdigest() == entry["original_sha256"]
            completeness = block_completeness(expected, content)
            overlap = _overlap_bytes(item["offsets"], entry["fragments"])
            offset_match = overlap >= 0.5 * entry["size_bytes"] if entry["size_bytes"] else False
            if exact or offset_match or completeness >= 0.5:
                possibilities.append((
                    0 if exact else 1, -completeness, -overlap,
                    local_truth_index, result_index, "exact" if exact else "partial",
                    1.0 if exact else completeness,
                ))
    possibilities.sort()
    matched_truth: set[int] = set()
    matched_results: set[int] = set()
    matches: dict[int, FileMatch] = {}
    for _, _, _, local_index, result_index, status, completeness in possibilities:
        if local_index in matched_truth or result_index in matched_results:
            continue
        truth_index = original_indices[local_index]
        matched_truth.add(local_index)
        matched_results.add(result_index)
        matches[truth_index] = FileMatch(truth_index, result_index, status, completeness)
    return matches, set(range(len(recovered))) - matched_results, recovered_bytes
