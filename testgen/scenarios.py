"""Ground-truth scenario construction for the six published test images."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from PIL import __version__ as pillow_version

from schemas.models import GroundTruth
from testgen.content import make_jpeg
from testgen.dvrlike import make_clip
from testgen.fat32_writer import Fat32Image
from testgen.scenario_helpers import (
    CLUSTER, FIXED_TIME, add_file, data_start_offset, entry, fragmented_clusters,
    payload, ranges_for_groups, regular_set, validate_pristine, write_original,
)

SCENARIOS = {
    "clean_deleted": "A", "corrupted_fs": "B", "fragmented": "C",
    "demo_mixed": "D", "empty_fs": "E", "not_fat": "F",
}


def _clean_or_corrupt(out: Path, seed: int, corrupt: bool) -> tuple[Fat32Image, list[dict[str, Any]]]:
    writer = Fat32Image(seed=seed)
    files = []
    for index, (name, kind) in enumerate(regular_set(), 1):
        data = payload(kind, seed + index)
        allocation = writer.write_file(name, data, timestamps={"modified": FIXED_TIME})
        files.append(entry(
            f"gt-{index:03d}", name, kind, data,
            "fs_corrupted_contiguous" if corrupt else ("deleted_contiguous" if index <= 6 else "live"),
            [{"start": allocation.start_offset, "end": allocation.start_offset + len(data)}],
            expected_via="carving" if corrupt else "fat32",
            classification="carved" if corrupt else "intact",
            acceptable=["carved"] if corrupt else ["intact", "carved"],
            dir_entry=not corrupt,
        ))
        write_original(out / "originals" / name, data)
    validate_pristine(writer, out)
    if corrupt:
        root = writer.cluster_offset(2)
        writer.zero_region(root, root + CLUSTER)
        fat1_start = writer.RESERVED_SECTORS * writer.SECTOR_SIZE
        fat_length = writer.fat_sectors * writer.SECTOR_SIZE
        amount = int(fat_length * 0.30)
        writer.corrupt_region(fat1_start, fat1_start + amount, seed=seed + 1)
        writer.corrupt_region(fat1_start + fat_length, fat1_start + fat_length + amount, seed=seed + 1)
    else:
        for item in files[:6]:
            writer.delete_file(item["name"])
    return writer, files


def _fragmented(
    out: Path, seed: int, *, demo: bool = False, writer: Fat32Image | None = None,
    start_cluster: int = 20,
) -> tuple[Fat32Image, list[dict[str, Any]], list[dict[str, Any]]]:
    writer = writer or Fat32Image(seed=seed)
    files: list[dict[str, Any]] = []
    decoys: list[dict[str, Any]] = []
    cursor = start_cluster
    count = 2 if demo else 6
    for index in range(count):
        name = f"FRAG{index + 1:04d}.JPG"
        data = payload("jpeg", seed + index + 30)
        fragmented = index >= (count - (2 if demo else 3))
        if fragmented:
            clusters, groups, cursor = fragmented_clusters(cursor, data, pieces=2)
        else:
            clusters = list(range(cursor, cursor + max(1, (len(data) + CLUSTER - 1) // CLUSTER)))
            groups = [clusters]
            cursor = clusters[-1] + 4
        allocation = writer.write_file(name, data, clusters=clusters, timestamps={"modified": FIXED_TIME})
        ranges = ranges_for_groups(writer, groups, len(data))
        item = entry(
            f"gt-frag-{index + 1:02d}", name, "jpeg",
            data, "deleted_fragmented" if fragmented else "deleted_contiguous", ranges,
            expected_via="reconstruction" if fragmented else "carving",
            classification="reconstructed" if fragmented else "carved",
            acceptable=["reconstructed", "partial"] if fragmented else ["carved", "intact"],
        )
        files.append(item)
        write_original(out / "originals" / name, data)
        if fragmented:
            for gap_index, (left, right) in enumerate(zip(groups, groups[1:])):
                gap_start = writer.cluster_offset(left[-1] + 1)
                gap_end = writer.cluster_offset(right[0])
                rng = random.Random(seed + index * 100 + gap_index)
                writer.image[gap_start:gap_end] = rng.randbytes(gap_end - gap_start)
                decoys.append({
                    "id": f"gap-decoy-{index + 1}-{gap_index + 1}",
                    "kind": "fragment_gap_noise", "start": gap_start, "end": gap_end,
                })
    if not demo:
        name = "THREE001.JPG"
        data = payload("jpeg", seed + 99)
        clusters, groups, _ = fragmented_clusters(cursor, data, pieces=3)
        allocation = writer.write_file(name, data, clusters=clusters, timestamps={"modified": FIXED_TIME})
        files.append(entry(
            "gt-stretch", name, "jpeg", data, "deleted_fragmented",
            ranges_for_groups(writer, groups, len(data)), recoverable=False,
            expected_via="none", classification="partial", acceptable=["partial"],
        ))
        write_original(out / "originals" / name, data)
    return writer, files, decoys


def _demo(out: Path, seed: int) -> tuple[Fat32Image, list[dict[str, Any]], list[dict[str, Any]]]:
    writer = Fat32Image(seed=seed)
    files: list[dict[str, Any]] = []
    names = [(f"INT{i:04d}.JPG", "jpeg") for i in range(1, 4)]
    names += [("INT0004.PDF", "pdf"), ("INT0005.PNG", "png"), ("INT0006.PNG", "png")]
    for index, (name, kind) in enumerate(names):
        data = payload(kind, seed + 100 + index)
        files.append(add_file(writer, out, f"gt-int-{index + 1}", name, kind, data, state="deleted_contiguous"))
    carved = [(f"CARVE{i:04d}.JPG", "jpeg") for i in range(1, 4)]
    carved += [("CARVE001.PDF", "pdf"), ("CARVE002.PDF", "pdf")]
    for index, (name, kind) in enumerate(carved):
        data = payload(kind, seed + 200 + index)
        files.append(add_file(
            writer, out, f"gt-carve-{index + 1}", name, kind, data,
            state="fs_corrupted_contiguous", via="carving", classification="carved",
            acceptable=["carved"],
        ))
    _, fragmented, gap_decoys = _fragmented(
        out, seed + 300, demo=True, writer=writer, start_cluster=5_000
    )
    files.extend(fragmented)
    for channel, state in ((1, "dvr_live"), (2, "dvr_deleted")):
        data, metadata = make_clip(seed + 400 + channel, channel=channel)
        name = f"CH{channel:02d}_{channel:04d}.DVR"
        files.append(add_file(
            writer, out, f"gt-dvr-{channel}", name, "dvr", data,
            state=state, metadata=metadata, acceptable=["intact", "carved"],
        ))
    for index in range(2):
        name = f"OVER{index + 1:04d}.JPG"
        original = payload("jpeg", seed + 500 + index)
        partial = original[: int(len(original) * 0.55)]
        item = add_file(
            writer, out, f"gt-over-{index + 1}", name, "jpeg", partial,
            state="overwritten_partial", recoverable=False, via="none",
            classification="partial", acceptable=["partial"], original=original,
        )
        item["fragments"] = item["fragments"][:]
        item["metadata"] = {"overwritten_fraction": 0.45}
        files.append(item)
    validate_pristine(writer, out)
    for item in files:
        if item["state"] in ("deleted_contiguous", "dvr_deleted", "deleted_fragmented"):
            writer.delete_file(item["name"])
    # Damage a portion of both FAT copies while preserving the boot sector and directory.
    fat_start = writer.RESERVED_SECTORS * writer.SECTOR_SIZE
    fat_bytes = writer.fat_sectors * writer.SECTOR_SIZE
    damage_start = fat_start + 3 * 4
    damage_end = fat_start + int(fat_bytes * 0.30)
    writer.corrupt_region(damage_start, damage_end, seed=seed + 700)
    writer.corrupt_region(
        fat_start + fat_bytes + 3 * 4,
        fat_start + fat_bytes + int(fat_bytes * 0.30),
        seed=seed + 700,
    )
    # Add three non-overlapping, intentionally incomplete/noise decoys.
    decoys: list[dict[str, Any]] = gap_decoys
    for index, (cluster, decoy_bytes, kind) in enumerate((
        (10_000, b"\xff\xd8" + b"J" * 800, "jpeg_header_no_footer"),
        (10_100, b"%PDF-1.7\ntruncated document", "truncated_pdf"),
        (10_200, b"random" + b"\x89PNG\r\n\x1a\n" + b"noise" * 50, "embedded_png_signature"),
    ), 1):
        start = writer.cluster_offset(cluster)
        writer.image[start:start + len(decoy_bytes)] = decoy_bytes
        decoys.append({
            "id": f"decoy-{index}", "kind": kind,
            "start": start, "end": start + len(decoy_bytes),
        })
    return writer, files, decoys


def build_scenario(name: str, output: Path, seed: int) -> dict[str, Any]:
    """Build one named scenario, validate the pristine filesystem, and return ground truth."""
    if name not in SCENARIOS:
        raise ValueError(f"unknown scenario: {name}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "originals").mkdir(exist_ok=True)
    decoys: list[dict[str, Any]] = []
    expected_error = None
    if name == "clean_deleted":
        writer, files = _clean_or_corrupt(output, seed, False)
    elif name == "corrupted_fs":
        writer, files = _clean_or_corrupt(output, seed, True)
    elif name == "fragmented":
        writer, files, decoys = _fragmented(output, seed)
        validate_pristine(writer, output)
        for item in files:
            writer.delete_file(item["name"])
    elif name == "demo_mixed":
        writer, files, decoys = _demo(output, seed)
    elif name == "empty_fs":
        writer, files = Fat32Image(seed=seed), []
        validate_pristine(writer, output)
    else:
        rng = random.Random(seed)
        payload = rng.randbytes(1024 * 1024)
        image_path = output / "disk.img"
        image_path.write_bytes(payload)
        expected_error = "unrecognized_filesystem"
        return _ground_truth(name, seed, payload, [], [], expected_error, output)
    writer.save(output / "disk.img")
    return _ground_truth(name, seed, writer.image, files, decoys, expected_error, output)


def _ground_truth(
    name: str, seed: int, image: bytes | bytearray, files: list[dict[str, Any]],
    decoys: list[dict[str, Any]], expected_error: str | None, output: Path,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": "1.0", "scenario": name, "seed": seed,
        "pillow_version": pillow_version,
        "image": {
            "path": "disk.img", "sha256": hashlib.sha256(image).hexdigest(),
            "size_bytes": len(image), "bytes_per_sector": 512,
            "sectors_per_cluster": 2, "cluster_size": 1024,
            "data_start_offset": 0 if name == "not_fat" else data_start_offset(),
        },
        "files": files, "decoys": decoys,
    }
    if expected_error:
        data["expected_error"] = expected_error
    GroundTruth.model_validate(data)
    (output / "ground_truth.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data
