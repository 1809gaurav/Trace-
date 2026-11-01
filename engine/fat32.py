"""Read-only FAT32 boot-sector, FAT-chain, and directory recovery helpers."""

from __future__ import annotations

import math
import mmap
import struct
from dataclasses import dataclass
from typing import Callable

from engine.fat32_directory import (
    DirectoryEntry,
    _decode_lfn,
    _file_type,
    decode_directory_entry,
)


FAT32_EOC_MIN = 0x0FFFFFF8
FAT32_BAD_CLUSTER = 0x0FFFFFF7
MAX_FILE_SIZE = 128 * 1024 * 1024
ImageBuffer = bytes | bytearray | mmap.mmap


@dataclass(frozen=True)
class BootParameters:
    """Validated FAT32 parameters derived from a BIOS Parameter Block."""

    bytes_per_sector: int
    sectors_per_cluster: int
    reserved_sectors: int
    fat_count: int
    fat_size_sectors: int
    total_sectors: int
    root_cluster: int
    cluster_count: int
    data_start: int

    @property
    def cluster_size(self) -> int:
        return self.bytes_per_sector * self.sectors_per_cluster


@dataclass(frozen=True)
class RecoveryCandidate:
    """A validated file recovered from a FAT directory entry."""

    name: str
    file_type: str
    data: bytes
    offsets: list[dict[str, int]]
    state: str
    timestamps: dict[str, str | None]
    clusters: tuple[int, ...]
    source: str = "fat32"


@dataclass(frozen=True)
class FragmentHint:
    """Directory metadata retained when deleted contiguous data fails validation."""

    name: str | None
    file_type: str
    size_bytes: int | None
    start_cluster: int
    timestamps: dict[str, str | None]


def parse_boot_sector(boot: bytes | bytearray | memoryview, image_size: int) -> BootParameters:
    """Validate a boot sector and calculate the FAT32 data area."""
    if len(boot) < 512:
        raise ValueError("boot sector is shorter than 512 bytes")
    if bytes(boot[510:512]) != b"\x55\xaa":  # BS_Signature @0x1FE, 2 bytes
        raise ValueError("invalid BS_Signature at offset 0x1FE (expected 0xAA55)")
    bytes_per_sector = struct.unpack_from("<H", boot, 0x0B)[0]  # BPB_BytsPerSec @0x0B, 2 bytes LE
    sectors_per_cluster = boot[0x0D]  # BPB_SecPerClus @0x0D, 1 byte
    reserved_sectors = struct.unpack_from("<H", boot, 0x0E)[0]  # BPB_RsvdSecCnt @0x0E, 2 bytes LE
    fat_count = boot[0x10]  # BPB_NumFATs @0x10, 1 byte
    total_sectors = struct.unpack_from("<I", boot, 0x20)[0]  # BPB_TotSec32 @0x20, 4 bytes LE
    fat_size = struct.unpack_from("<I", boot, 0x24)[0]  # BPB_FATSz32 @0x24, 4 bytes LE
    root_cluster = struct.unpack_from("<I", boot, 0x2C)[0] & 0x0FFFFFFF  # BPB_RootClus @0x2C, 4 bytes LE

    if bytes_per_sector not in (512, 1024, 2048, 4096):
        raise ValueError(f"invalid BPB_BytsPerSec={bytes_per_sector} at offset 0x0B")
    if not 1 <= sectors_per_cluster <= 128 or sectors_per_cluster & (sectors_per_cluster - 1):
        raise ValueError(f"invalid BPB_SecPerClus={sectors_per_cluster} at offset 0x0D")
    if reserved_sectors < 1:
        raise ValueError(f"invalid BPB_RsvdSecCnt={reserved_sectors} at offset 0x0E")
    if fat_count not in (1, 2):
        raise ValueError(f"invalid BPB_NumFATs={fat_count} at offset 0x10")
    if fat_size < 1:
        raise ValueError(f"invalid BPB_FATSz32={fat_size} at offset 0x24")
    if total_sectors < 1 or total_sectors * bytes_per_sector > image_size:
        raise ValueError(
            f"invalid BPB_TotSec32={total_sectors} at offset 0x20 for "
            f"image_size={image_size} and BPB_BytsPerSec={bytes_per_sector}"
        )

    data_sectors = total_sectors - reserved_sectors - fat_count * fat_size
    if data_sectors <= 0:
        raise ValueError(
            f"BPB_RsvdSecCnt={reserved_sectors} and BPB_NumFATs={fat_count} * "
            f"BPB_FATSz32={fat_size} exceed BPB_TotSec32={total_sectors}"
        )
    cluster_count = data_sectors // sectors_per_cluster
    if cluster_count < 65_525:
        raise ValueError(
            f"FAT32 requires at least 65525 data clusters; BPB_TotSec32="
            f"{total_sectors}, BPB_RsvdSecCnt={reserved_sectors}, "
            f"BPB_NumFATs={fat_count}, BPB_FATSz32={fat_size}, "
            f"BPB_SecPerClus={sectors_per_cluster} yield only {cluster_count}"
        )
    if root_cluster < 2 or root_cluster >= cluster_count + 2:
        raise ValueError(
            f"invalid BPB_RootClus={root_cluster} at offset 0x2C "
            f"(valid range 2..{cluster_count + 1})"
        )
    if fat_size * bytes_per_sector < (cluster_count + 2) * 4:
        raise ValueError(
            f"BPB_FATSz32={fat_size} is too small for {cluster_count} data clusters "
            f"with BPB_BytsPerSec={bytes_per_sector}"
        )

    data_start = (reserved_sectors + fat_count * fat_size) * bytes_per_sector
    return BootParameters(
        bytes_per_sector=bytes_per_sector,
        sectors_per_cluster=sectors_per_cluster,
        reserved_sectors=reserved_sectors,
        fat_count=fat_count,
        fat_size_sectors=fat_size,
        total_sectors=total_sectors,
        root_cluster=root_cluster,
        cluster_count=cluster_count,
        data_start=data_start,
    )


def select_boot_sector(
    image: ImageBuffer, image_size: int,
) -> tuple[BootParameters, str]:
    """Use a valid primary boot sector or fall back to its backup."""
    if len(image) >= 512 and bytes(image[510:512]) == b"\x55\xaa":
        for offset in range(446, 510, 16):
            partition_type = image[offset + 4]
            start_sector = struct.unpack_from("<I", image, offset + 8)[0]  # MBR partition start LBA @entry+8, 4 bytes LE
            sector_count = struct.unpack_from("<I", image, offset + 12)[0]  # MBR partition size @entry+12, 4 bytes LE
            if (
                partition_type
                and start_sector
                and sector_count
                and (start_sector + sector_count) * 512 <= image_size
            ):
                raise ValueError(
                    f"partitioned disk image detected: MBR partition type "
                    f"0x{partition_type:02X} starts at sector {start_sector}; "
                    "provide the FAT32 partition image, not the whole disk"
                )
    primary_error: ValueError | None = None
    try:
        return parse_boot_sector(image[:512], image_size), "primary"
    except ValueError as error:
        primary_error = error

    backup_sector = 6
    if len(image) >= 0x34:
        declared = struct.unpack_from("<H", image, 0x32)[0]  # BPB_BkBootSec @0x32, 2 bytes LE
        if declared:
            backup_sector = declared
    for sector_size in (512, 1024, 2048, 4096):
        offset = backup_sector * sector_size
        if offset + 512 > len(image):
            continue
        try:
            return parse_boot_sector(image[offset:offset + 512], image_size), "backup"
        except ValueError:
            continue
    raise ValueError(f"unrecognized_filesystem: {primary_error}")


def follow_fat_chain(
    fat: bytes | bytearray | memoryview, first_cluster: int, cluster_count: int,
) -> tuple[list[int], list[str]]:
    """Follow a FAT chain without looping or trusting out-of-range entries."""
    clusters: list[int] = []
    warnings: list[str] = []
    current = first_cluster
    visited: set[int] = set()
    while True:
        if current < 2 or current >= cluster_count + 2:
            warnings.append(f"cluster {current} is out of range")
            break
        if current in visited:
            warnings.append(f"loop detected at cluster {current}")
            break
        if current * 4 + 4 > len(fat):
            warnings.append(f"FAT entry for cluster {current} is unavailable")
            break
        visited.add(current)
        clusters.append(current)
        next_cluster = struct.unpack_from("<I", fat, current * 4)[0] & 0x0FFFFFFF  # FAT entry @cluster*4, 4 bytes LE
        if next_cluster >= FAT32_EOC_MIN:
            break
        if next_cluster == FAT32_BAD_CLUSTER or next_cluster >= 0x0FFFFFF0:
            warnings.append(f"invalid FAT value 0x{next_cluster:07x} at cluster {current}")
            break
        current = next_cluster
    return clusters, warnings


class Fat32Reader:
    """Recover validated files from a FAT32 image buffer without modifying it."""

    def __init__(
        self, image: ImageBuffer,
        validator: Callable[[str, bytes], bool],
    ):
        self.image = image
        self.validator = validator
        self.bpb, self.boot_source = select_boot_sector(image, len(image))
        fat_start = self.bpb.reserved_sectors * self.bpb.bytes_per_sector
        fat_length = self.bpb.fat_size_sectors * self.bpb.bytes_per_sector
        self.fat = bytes(image[fat_start:fat_start + fat_length])
        self.warnings: list[str] = []
        self.claimed_clusters: set[int] = set()
        self.hints: list[FragmentHint] = []
        self.live_count = 0
        self.deleted_count = 0

    def _cluster_offset(self, cluster: int) -> int:
        if not 2 <= cluster < self.bpb.cluster_count + 2:
            raise ValueError(f"cluster {cluster} is out of range")
        return self.bpb.data_start + (cluster - 2) * self.bpb.cluster_size

    def _lfn_name(self, records: list[bytes], raw: bytes, deleted: bool) -> str | None:
        return _decode_lfn(records, raw, deleted)

    def _directory_entries(self, first_cluster: int) -> list[DirectoryEntry]:
        clusters, chain_warnings = follow_fat_chain(self.fat, first_cluster, self.bpb.cluster_count)
        self.warnings.extend(chain_warnings)
        entries: list[DirectoryEntry] = []
        pending_lfn: list[bytes] = []
        for cluster in clusters:
            start = self._cluster_offset(cluster)
            end = min(start + self.bpb.cluster_size, len(self.image))
            for offset in range(start, end - 31, 32):
                raw = bytes(self.image[offset:offset + 32])
                if raw[0] == 0:  # DIR_Name[0] @0x00, end-of-directory marker
                    return entries
                if raw[11] == 0x0F:  # LDIR_Attr @0x0B, long-name entry marker
                    pending_lfn.append(raw)
                    continue
                record = decode_directory_entry(raw)
                long_name = self._lfn_name(pending_lfn, raw, record.deleted)
                pending_lfn = []
                if long_name:
                    record = DirectoryEntry(
                        name=long_name, attributes=record.attributes,
                        start_cluster=record.start_cluster, size_bytes=record.size_bytes,
                        deleted=record.deleted, timestamps=record.timestamps,
                    )
                entries.append(record)
        return entries

    def _offsets_for_clusters(self, clusters: list[int], size: int) -> list[dict[str, int]]:
        offsets: list[dict[str, int]] = []
        remaining = size
        group: list[int] = []
        for cluster in clusters:
            if group and cluster != group[-1] + 1:
                used = min(remaining, len(group) * self.bpb.cluster_size)
                start = self._cluster_offset(group[0])
                offsets.append({"start": start, "end": start + used})
                remaining -= used
                group = []
            group.append(cluster)
        if group and remaining > 0:
            used = min(remaining, len(group) * self.bpb.cluster_size)
            start = self._cluster_offset(group[0])
            offsets.append({"start": start, "end": start + used})
        return offsets

    def recover(self) -> list[RecoveryCandidate]:
        """Walk root and subdirectories and return only validator-confirmed files."""
        recovered: list[RecoveryCandidate] = []
        pending_directories = [self.bpb.root_cluster]
        visited_directories: set[int] = set()
        while pending_directories:
            directory_cluster = pending_directories.pop()
            if directory_cluster in visited_directories:
                self.warnings.append(f"directory loop at cluster {directory_cluster}")
                continue
            visited_directories.add(directory_cluster)
            try:
                entries = self._directory_entries(directory_cluster)
            except ValueError as error:
                self.warnings.append(str(error))
                continue
            for record in entries:
                if record.is_volume_label:
                    continue
                if record.is_directory:
                    if record.name not in (".", "..") and record.start_cluster >= 2:
                        pending_directories.append(record.start_cluster)
                    continue
                if record.size_bytes <= 0 or record.size_bytes > min(MAX_FILE_SIZE, len(self.image)):
                    if record.size_bytes > 0:
                        self.warnings.append(f"ignored unreasonable file size for {record.name}")
                    continue
                kind = _file_type(record.name)
                if kind == "unknown":
                    continue
                needed = max(1, math.ceil(record.size_bytes / self.bpb.cluster_size))
                if record.deleted:
                    clusters = list(range(record.start_cluster, record.start_cluster + needed))
                    if not clusters or clusters[-1] >= self.bpb.cluster_count + 2:
                        self.warnings.append(f"deleted allocation for {record.name} is out of range")
                        continue
                    state = "deleted_contiguous"
                else:
                    clusters, chain_warnings = follow_fat_chain(
                        self.fat, record.start_cluster, self.bpb.cluster_count
                    )
                    self.warnings.extend(chain_warnings)
                    if len(clusters) < needed:
                        self.warnings.append(f"short FAT chain for {record.name}")
                        continue
                    clusters = clusters[:needed]
                    state = "live"

                pieces = []
                for cluster in clusters:
                    start = self._cluster_offset(cluster)
                    pieces.append(bytes(self.image[start:start + self.bpb.cluster_size]))
                data = b"".join(pieces)[:record.size_bytes]
                if len(data) != record.size_bytes or not self.validator(kind, data):
                    if record.deleted and record.start_cluster >= 2:
                        self.hints.append(FragmentHint(
                            name=record.name, file_type=kind,
                            size_bytes=record.size_bytes,
                            start_cluster=record.start_cluster,
                            timestamps=record.timestamps,
                        ))
                    else:
                        self.warnings.append(f"validator rejected FAT entry {record.name}")
                    continue
                self.claimed_clusters.update(clusters)
                if record.deleted:
                    self.deleted_count += 1
                else:
                    self.live_count += 1
                recovered.append(RecoveryCandidate(
                    name=record.name, file_type=kind, data=data,
                    offsets=self._offsets_for_clusters(clusters, record.size_bytes),
                    state=state, timestamps=record.timestamps, clusters=tuple(clusters),
                ))
        self.hints.sort(key=lambda hint: hint.start_cluster)
        return sorted(recovered, key=lambda item: item.offsets[0]["start"] if item.offsets else 0)
