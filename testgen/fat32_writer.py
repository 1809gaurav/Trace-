"""Minimal deterministic FAT32 image formatter with explicit cluster allocation."""

from __future__ import annotations

import math
import random
import struct
from dataclasses import dataclass
from pathlib import Path

from testgen.fat32_directory import (
    long_name_entry_count, make_file_entry, mark_deleted, short_name,
    write_long_name_entries,
)
from testgen.fat32_layout import format_volume, write_fsinfo
from testgen.fat32_tools import validate_saved as validate_saved_tools


@dataclass(frozen=True)
class Allocation:
    """Clusters occupied by a file, in logical file order."""

    clusters: list[int]
    start_offset: int
    size_bytes: int


class Fat32Image:
    """Create and edit a raw FAT32 volume without mounting it."""

    SECTOR_SIZE = 512
    SECTORS_PER_CLUSTER = 2
    CLUSTER_SIZE = SECTOR_SIZE * SECTORS_PER_CLUSTER
    TOTAL_SECTORS = 128 * 1024 * 1024 // SECTOR_SIZE
    RESERVED_SECTORS = 32
    FAT_COUNT = 2

    def __init__(self, *, size_bytes: int = 128 * 1024 * 1024, seed: int = 1337):
        if size_bytes % self.CLUSTER_SIZE:
            raise ValueError("image size must be divisible by the cluster size")
        self.seed = seed
        self.total_sectors = size_bytes // self.SECTOR_SIZE
        self.fat_sectors = 1
        while True:
            data_sectors = (
                self.total_sectors - self.RESERVED_SECTORS - self.FAT_COUNT * self.fat_sectors
            )
            clusters = data_sectors // self.SECTORS_PER_CLUSTER
            needed = math.ceil((clusters + 2) * 4 / self.SECTOR_SIZE)
            if needed == self.fat_sectors:
                break
            self.fat_sectors = needed
        self.cluster_count = clusters
        if self.cluster_count < 65_525:
            raise ValueError("volume is too small to qualify as FAT32")
        self.data_start_offset = (
            self.RESERVED_SECTORS + self.FAT_COUNT * self.fat_sectors
        ) * self.SECTOR_SIZE
        self.size_bytes = size_bytes
        self.format()

    def format(self) -> None:
        """Create a fresh FAT32 volume, clearing prior files and image content."""
        self.image = bytearray(self.size_bytes)
        self.files: dict[str, Allocation] = {}
        self.entries: dict[str, int] = {}
        self._originals: dict[str, bytes] = {}
        self._short_names: dict[str, bytes] = {}
        self._used_clusters = {2}
        self._fat = [0] * (self.cluster_count + 2)
        self._fat[0], self._fat[1] = 0x0FFFFFF8, 0x0FFFFFFF
        self._fat[2] = 0x0FFFFFFF
        format_volume(
            self.image, sector_size=self.SECTOR_SIZE,
            sectors_per_cluster=self.SECTORS_PER_CLUSTER,
            reserved_sectors=self.RESERVED_SECTORS, fat_count=self.FAT_COUNT,
            total_sectors=self.total_sectors, fat_sectors=self.fat_sectors,
            seed=self.seed, cluster_count=self.cluster_count,
        )
        self._flush_fats()

    @property
    def cluster_size(self) -> int:
        """Bytes in one allocation unit."""
        return self.CLUSTER_SIZE

    def _flush_fats(self) -> None:
        first = self.RESERVED_SECTORS * self.SECTOR_SIZE
        fat_bytes = self.fat_sectors * self.SECTOR_SIZE
        packed = bytearray(fat_bytes)
        for index, value in enumerate(self._fat):
            struct.pack_into(
                "<I", packed, index * 4, value & 0x0FFFFFFF
            )  # FAT entry @index*4, 4 bytes LE
        self.image[first:first + fat_bytes] = packed  # FAT1 entries @BPB_RsvdSecCnt, full FAT
        second = first + fat_bytes
        self.image[second:second + fat_bytes] = packed  # FAT2 entries, full FAT
        free = [cluster for cluster in range(3, self.cluster_count + 2) if self._fat[cluster] == 0]
        for sector in (1, 7):
            write_fsinfo(
                self.image, self.SECTOR_SIZE, sector, len(free),
                free[0] if free else 0xFFFFFFFF,
            )

    def cluster_offset(self, cluster: int) -> int:
        """Map a data cluster number to its absolute image byte offset."""
        if not 2 <= cluster < self.cluster_count + 2:
            raise ValueError(f"invalid data cluster {cluster}")
        return self.data_start_offset + (cluster - 2) * self.CLUSTER_SIZE

    def write_file(
        self,
        name: str,
        data: bytes,
        *,
        clusters: list[int] | None = None,
        timestamps: dict[str, str] | None = None,
    ) -> Allocation:
        """Write a file, optionally specifying clusters in file order."""
        if name in self.files:
            raise ValueError(f"file already exists: {name}")
        short = short_name(name, set(self._short_names.values()))
        lfn_count = long_name_entry_count(name, short)
        root = self.cluster_offset(2)
        used = next(
            (offset for offset in range(root, root + self.CLUSTER_SIZE, 32)
             if self.image[offset] == 0),
            None,
        )
        if used is None or used + (lfn_count + 1) * 32 > root + self.CLUSTER_SIZE:
            raise ValueError("root directory is full")
        entry_offset = used + lfn_count * 32
        required = max(1, math.ceil(len(data) / self.CLUSTER_SIZE))
        if clusters is None:
            clusters = []
            candidate = 3
            while len(clusters) < required:
                while candidate in self._used_clusters:
                    candidate += 1
                clusters.append(candidate)
                candidate += 1
        if len(clusters) != required:
            raise ValueError(f"{name} requires exactly {required} clusters")
        if len(set(clusters)) != len(clusters) or any(
            cluster in self._used_clusters or not 3 <= cluster < self.cluster_count + 2
            for cluster in clusters
        ):
            raise ValueError("clusters must be unique, free data clusters")
        self._used_clusters.update(clusters)
        padded = data.ljust(required * self.CLUSTER_SIZE, b"\x00")
        for index, cluster in enumerate(clusters):
            start = self.cluster_offset(cluster)
            self.image[start:start + self.CLUSTER_SIZE] = padded[
                index * self.CLUSTER_SIZE:(index + 1) * self.CLUSTER_SIZE
            ]
            self._fat[cluster] = clusters[index + 1] if index + 1 < len(clusters) else 0x0FFFFFFF
        entry = make_file_entry(
            short, clusters[0], len(data), timestamps or {}
        )
        self.image[entry_offset:entry_offset + 32] = entry
        write_long_name_entries(self.image, name, short, entry_offset)
        allocation = Allocation(clusters.copy(), self.cluster_offset(clusters[0]), len(data))
        self.files[name] = allocation
        self.entries[name] = entry_offset
        self._originals[name] = bytes(data)
        self._short_names[name] = short
        self._flush_fats()
        return allocation

    def delete_file(self, name: str) -> None:
        """Mark the short entry deleted and release its FAT chain, retaining data."""
        if name not in self.files:
            raise KeyError(name)
        mark_deleted(self.image, self.entries[name], self.cluster_offset(2))
        for cluster in self.files[name].clusters:
            self._fat[cluster] = 0
        self._flush_fats()

    def zero_region(self, start: int, end: int) -> None:
        """Zero an absolute, end-exclusive byte range."""
        self._check_range(start, end)
        self.image[start:end] = bytes(end - start)

    def corrupt_region(
        self, start: int, end: int, *, seed: int | None = None,
        rng: random.Random | None = None,
    ) -> None:
        """Replace an absolute byte range with deterministic pseudo-random bytes."""
        self._check_range(start, end)
        if rng is not None and seed is not None:
            raise ValueError("provide either rng or seed, not both")
        source = rng if rng is not None else random.Random(self.seed if seed is None else seed)
        self.image[start:end] = source.randbytes(end - start)

    def _check_range(self, start: int, end: int) -> None:
        if not 0 <= start <= end <= len(self.image):
            raise ValueError("image range is out of bounds")

    def read_cluster(self, cluster: int) -> bytes:
        """Return one complete data cluster."""
        start = self.cluster_offset(cluster)
        return bytes(self.image[start:start + self.CLUSTER_SIZE])

    def read_file(self, name: str) -> bytes:
        """Read a file using the writer's allocation metadata."""
        allocation = self.files[name]
        output = b"".join(self.read_cluster(cluster) for cluster in allocation.clusters)
        return output[:allocation.size_bytes]

    def fat_entry(self, cluster: int) -> int:
        """Return a cluster's current FAT entry."""
        return self._fat[cluster]

    def directory_entry_first_byte(self, name: str) -> int:
        """Return the first byte of a file's short directory entry."""
        return self.image[self.entries[name]]

    def validate(self) -> None:
        """Check boot parameters, FAT copies, chains, directory entries, and file bytes."""
        boot = self.image[:self.SECTOR_SIZE]
        if boot[510:512] != b"\x55\xaa":  # BS_Signature @0x1FE, 2 bytes LE
            raise ValueError("invalid boot signature")
        if struct.unpack_from("<H", boot, 0x0B)[0] != self.SECTOR_SIZE:  # BPB_BytsPerSec @0x0B
            raise ValueError("invalid bytes-per-sector field")
        if boot[0x0D] != self.SECTORS_PER_CLUSTER:  # BPB_SecPerClus @0x0D, 1 byte
            raise ValueError("invalid sectors-per-cluster field")
        if struct.unpack_from("<I", boot, 0x24)[0] != self.fat_sectors:  # BPB_FATSz32 @0x24
            raise ValueError("invalid FAT size field")
        if struct.unpack_from("<I", boot, 0x2C)[0] != 2:  # BPB_RootClus @0x2C
            raise ValueError("invalid root cluster")
        fat_start = self.RESERVED_SECTORS * self.SECTOR_SIZE
        fat_size = self.fat_sectors * self.SECTOR_SIZE
        fat1 = self.image[fat_start:fat_start + fat_size]
        if fat1 != self.image[
            fat_start + fat_size:fat_start + 2 * fat_size
        ]:
            raise ValueError("FAT copies differ")
        if self.image[6 * self.SECTOR_SIZE:7 * self.SECTOR_SIZE] != boot:  # backup BS @sector 6
            raise ValueError("backup boot sector differs")
        for sector in (1, 7):
            fsinfo = sector * self.SECTOR_SIZE
            if struct.unpack_from("<I", self.image, fsinfo)[0] != 0x41615252:  # FSI_LeadSig @0x00
                raise ValueError("invalid FSInfo lead signature")
            if struct.unpack_from("<I", self.image, fsinfo + 484)[0] != 0x61417272:  # FSI_StrucSig @0x1E4
                raise ValueError("invalid FSInfo structure signature")
        for name, allocation in self.files.items():
            entry_offset = self.entries[name]
            entry = self.image[entry_offset:entry_offset + 32]
            if entry[:11] != self._short_names[name] or entry[11] != 0x20:  # DIR_Name/Attr @0x00/0x0B
                raise ValueError(f"invalid directory attributes: {name}")
            first_cluster = (
                struct.unpack_from("<H", entry, 20)[0] << 16  # DIR_FstClusHI @0x14
            ) | struct.unpack_from("<H", entry, 26)[0]  # DIR_FstClusLO @0x1A
            size = struct.unpack_from("<I", entry, 28)[0]  # DIR_FileSize @0x1C
            if first_cluster != allocation.clusters[0] or size != allocation.size_bytes:
                raise ValueError(f"invalid directory allocation metadata: {name}")
            data = bytearray()
            cluster = first_cluster
            for index, expected_cluster in enumerate(allocation.clusters):
                if cluster != expected_cluster:
                    raise ValueError(f"invalid FAT chain for {name}")
                start = self.cluster_offset(cluster)
                data.extend(self.image[start:start + self.CLUSTER_SIZE])
                fat_value = struct.unpack_from(
                    "<I", fat1, cluster * 4
                )[0] & 0x0FFFFFFF  # FAT entry @cluster*4, 4 bytes LE
                expected_next = (
                    allocation.clusters[index + 1]
                    if index + 1 < len(allocation.clusters) else 0x0FFFFFFF
                )
                if fat_value != expected_next:
                    raise ValueError(f"invalid FAT chain for {name}")
                cluster = fat_value
            if bytes(data[:size]) != self._originals[name]:
                raise ValueError(f"file data mismatch: {name}")

    def save(self, path: str | Path) -> None:
        """Write the full image bytes to disk."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(self.image)

    def validate_saved(self, path: str | Path) -> None:
        """Run optional fsck.fat/mtools checks; missing tools are explicitly warned."""
        validate_saved_tools(path, list(self.files), self.read_file, self.validate)
