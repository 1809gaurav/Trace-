"""Budgeted reconstruction of exactly two JPEG fragments.

For a known deleted-file start, the search tries each possible contiguous
prefix length and each permitted gap, then checks only unclaimed continuation
clusters at the corresponding physical locations. Each attempted join is a
full JPEG decode, so the worst-case work is bounded by the per-file candidate
budget and does not scale with every possible pair of image clusters.
"""

from __future__ import annotations

import hashlib
import mmap
import math
from dataclasses import dataclass
from typing import Iterable

from engine.config import (
    FRAGMENT_MAX_CANDIDATES_PER_FILE,
    FRAGMENT_CONTINUATION_REJECTION_FRACTION,
    FRAGMENT_MAX_FILE_BYTES,
    FRAGMENT_MAX_GAP_CLUSTERS,
    FRAGMENT_MAX_UNKNOWN_FILE_BYTES,
    FRAGMENT_MAX_UNKNOWN_HINTS,
    FRAGMENT_MAX_UNKNOWN_PREFIX_CLUSTERS,
    FRAGMENT_UNKNOWN_CONTINUATION_REJECTION_FRACTION,
    FRAGMENT_UNKNOWN_CANDIDATES_PER_FILE,
)
from engine.fat32 import FragmentHint
from engine.validators import (
    jpeg_entropy_chunk_prefix_length,
    jpeg_entropy_prefix_is_plausible,
    validate_jpeg,
)


ImageBuffer = bytes | bytearray | mmap.mmap


@dataclass(frozen=True)
class ReconstructedFile:
    """A fully decoded JPEG assembled from two non-contiguous ranges."""

    name: str | None
    data: bytes
    offsets: list[dict[str, int]]
    sha256: str
    search_cost: int
    clusters: tuple[int, ...]
    timestamps: dict[str, str | None]
    source: str = "fragments"
    file_type: str = "jpeg"


def _cluster_offset(cluster: int, data_start: int, cluster_size: int) -> int:
    # Data cluster offset derives from BPB_DataStart and the FAT cluster number.
    return data_start + (cluster - 2) * cluster_size


def _header_hints(
    image: ImageBuffer, data_start: int, cluster_size: int,
    cluster_count: int, known: Iterable[FragmentHint],
    claimed_clusters: set[int],
) -> list[FragmentHint]:
    hints = list(known)
    unknown_count = 0
    starts = {hint.start_cluster for hint in hints}
    cursor = 0
    while True:
        offset = image.find(b"\xff\xd8\xff", cursor)
        if offset < 0:
            break
        cursor = offset + 1
        delta = offset - data_start
        if delta < 0 or delta % cluster_size:
            continue
        cluster = delta // cluster_size + 2
        if cluster >= cluster_count + 2 or cluster in starts or cluster in claimed_clusters:
            continue
        if unknown_count >= FRAGMENT_MAX_UNKNOWN_HINTS:
            break
        hints.append(FragmentHint(
            name=None, file_type="jpeg", size_bytes=None,
            start_cluster=cluster, timestamps={},
        ))
        starts.add(cluster)
        unknown_count += 1
    return hints


def _candidate_clusters(
    first_cluster: int,
    first_count: int,
    second_cluster: int,
    second_count: int,
) -> tuple[int, ...]:
    return (
        tuple(range(first_cluster, first_cluster + first_count))
        + tuple(range(second_cluster, second_cluster + second_count))
    )


def _search_hint(
    image: ImageBuffer,
    hint: FragmentHint,
    *,
    data_start: int,
    cluster_size: int,
    cluster_count: int,
    claimed_clusters: set[int],
    max_gap_clusters: int,
) -> ReconstructedFile | None:
    if hint.file_type != "jpeg":
        return None
    first_cluster = hint.start_cluster
    if first_cluster < 2 or first_cluster >= cluster_count + 2:
        return None
    if hint.size_bytes is not None and hint.size_bytes > FRAGMENT_MAX_FILE_BYTES:
        return None
    known_size = hint.size_bytes is not None
    max_first_count = (
        math.ceil(hint.size_bytes / cluster_size) - 1
        if known_size and hint.size_bytes is not None
        else min(
            FRAGMENT_MAX_UNKNOWN_PREFIX_CLUSTERS,
            FRAGMENT_MAX_UNKNOWN_FILE_BYTES // cluster_size,
        )
    )
    candidate_budget = (
        FRAGMENT_MAX_CANDIDATES_PER_FILE
        if known_size else FRAGMENT_UNKNOWN_CANDIDATES_PER_FILE
    )
    tried = 0
    unknown_trials = 0
    for first_count in range(1, max_first_count + 1):
        first_end_cluster = first_cluster + first_count
        if first_end_cluster >= cluster_count + 2:
            break
        first_clusters = range(first_cluster, first_end_cluster)
        if any(cluster in claimed_clusters for cluster in first_clusters):
            continue
        first_offset = _cluster_offset(first_cluster, data_start, cluster_size)
        first_bytes = bytes(image[first_offset:first_offset + first_count * cluster_size])
        if len(first_bytes) != first_count * cluster_size:
            break
        first_prefix_plausible = jpeg_entropy_prefix_is_plausible(first_bytes)

        candidates: list[tuple[bool, int, int]] = []
        for gap in range(1, max_gap_clusters + 1):
            second_cluster = first_end_cluster + gap
            if second_cluster >= cluster_count + 2:
                break
            if hint.size_bytes is not None:
                second_count = math.ceil((hint.size_bytes - len(first_bytes)) / cluster_size)
                if second_count <= 0 or second_cluster + second_count > cluster_count + 2:
                    continue
                second_clusters = range(second_cluster, second_cluster + second_count)
                if any(cluster in claimed_clusters for cluster in second_clusters):
                    continue
                second_offset = _cluster_offset(second_cluster, data_start, cluster_size)
                remaining = hint.size_bytes - len(first_bytes)
                tail = bytes(image[second_offset:second_offset + remaining])
                ends_with_eoi = tail.endswith(b"\xff\xd9")
            else:
                second_offset = _cluster_offset(second_cluster, data_start, cluster_size)
                tail_end = min(
                    len(image),
                    second_offset + max(0, FRAGMENT_MAX_UNKNOWN_FILE_BYTES - len(first_bytes)),
                )
                ends_with_eoi = image.find(b"\xff\xd9", second_offset, tail_end) >= 0
            candidates.append((ends_with_eoi, gap, second_cluster))

        candidates.sort(key=lambda candidate: (not candidate[0], candidate[1]))
        for _ends_with_eoi, _gap, second_cluster in candidates:
            if not known_size:
                if unknown_trials >= candidate_budget:
                    return None
                unknown_trials += 1
            second_offset = _cluster_offset(second_cluster, data_start, cluster_size)
            gap_offset = _cluster_offset(first_cluster + first_count, data_start, cluster_size)
            gap_bytes = bytes(image[gap_offset:second_offset])
            plausible_gap = jpeg_entropy_chunk_prefix_length(
                gap_bytes, first_bytes.endswith(b"\xff")
            )
            minimum_noise_start = int(
                len(gap_bytes) * (
                    FRAGMENT_CONTINUATION_REJECTION_FRACTION
                    if known_size
                    else FRAGMENT_UNKNOWN_CONTINUATION_REJECTION_FRACTION
                )
            )
            if first_prefix_plausible and plausible_gap >= minimum_noise_start:
                continue
            if hint.size_bytes is not None:
                if tried >= candidate_budget:
                    return None
                tried += 1
                if not _ends_with_eoi:
                    continue
                second_length = hint.size_bytes - len(first_bytes)
                second_count = math.ceil(second_length / cluster_size)
                second_end_cluster = second_cluster + second_count
                clusters = _candidate_clusters(first_cluster, first_count, second_cluster, second_count)
                if any(cluster in claimed_clusters for cluster in clusters):
                    continue
                second_bytes = bytes(image[second_offset:second_offset + second_length])
                data = first_bytes + second_bytes
                if len(data) != hint.size_bytes:
                    continue
                valid = validate_jpeg(data).ok
                end_offset = second_offset + second_length
            else:
                maximum = min(
                    len(image) - second_offset,
                    FRAGMENT_MAX_UNKNOWN_FILE_BYTES - len(first_bytes),
                )
                search_offset = 0
                found_footer = False
                data = b""
                end_offset = second_offset
                second_end_cluster = second_cluster
                while True:
                    footer = image.find(b"\xff\xd9", second_offset + search_offset, second_offset + maximum)
                    if footer < 0:
                        break
                    if tried >= candidate_budget:
                        return None
                    tried += 1
                    second_length = footer + 2 - second_offset
                    second_count = math.ceil(second_length / cluster_size)
                    second_end_cluster = second_cluster + second_count
                    clusters = _candidate_clusters(
                        first_cluster, first_count, second_cluster, second_count
                    )
                    if (
                        second_end_cluster <= cluster_count + 2
                        and not any(cluster in claimed_clusters for cluster in clusters)
                    ):
                        candidate = first_bytes + bytes(image[second_offset:footer + 2])
                        if validate_jpeg(candidate).ok:
                            data = candidate
                            end_offset = footer + 2
                            found_footer = True
                            break
                    search_offset = footer + 2 - second_offset
                valid = found_footer
            if valid:
                first_length = len(first_bytes)
                first_actual_length = (
                    min(first_length, hint.size_bytes) if hint.size_bytes is not None else first_length
                )
                first_range_end = first_offset + first_actual_length
                offsets = [
                    {"start": first_offset, "end": first_range_end},
                    {"start": second_offset, "end": end_offset},
                ]
                used_clusters = _candidate_clusters(
                    first_cluster, first_count, second_cluster,
                    second_end_cluster - second_cluster,
                )
                return ReconstructedFile(
                    name=hint.name, data=data, offsets=offsets,
                    sha256=hashlib.sha256(data).hexdigest(),
                    search_cost=tried, clusters=used_clusters,
                    timestamps=hint.timestamps,
                )
    return None


def reconstruct_fragments(
    image: ImageBuffer,
    hints: Iterable[FragmentHint],
    *,
    data_start: int,
    cluster_size: int,
    cluster_count: int,
    claimed_clusters: set[int],
    max_gap_clusters: int = FRAGMENT_MAX_GAP_CLUSTERS,
) -> list[ReconstructedFile]:
    """Recover validated two-piece JPEGs from known starts and aligned headers."""
    if not 1 <= max_gap_clusters <= 64:
        raise ValueError("max_gap_clusters must be between 1 and 64")
    candidates = _header_hints(
        image, data_start, cluster_size, cluster_count, hints, claimed_clusters
    )
    recovered: list[ReconstructedFile] = []
    claimed = set(claimed_clusters)
    for hint in sorted(candidates, key=lambda item: item.start_cluster):
        result = _search_hint(
            image, hint, data_start=data_start, cluster_size=cluster_size,
            cluster_count=cluster_count, claimed_clusters=claimed,
            max_gap_clusters=max_gap_clusters,
        )
        if result is not None:
            recovered.append(result)
            claimed.update(result.clusters)
    return sorted(recovered, key=lambda item: item.offsets[0]["start"])
