"""FAT32 boot-sector and FSInfo serialization helpers."""

from __future__ import annotations

import struct


def write_fsinfo(
    image: bytearray, sector_size: int, sector: int, free_count: int, next_free: int,
) -> None:
    """Write one FSInfo or backup-FSInfo sector."""
    offset = sector * sector_size
    struct.pack_into("<I", image, offset, 0x41615252)  # FSI_LeadSig @0x00, 4 bytes LE
    struct.pack_into("<I", image, offset + 484, 0x61417272)  # FSI_StrucSig @0x1E4, 4 bytes LE
    struct.pack_into("<I", image, offset + 488, free_count)  # FSI_Free_Count @0x1E8, 4 bytes LE
    struct.pack_into("<I", image, offset + 492, next_free)  # FSI_Nxt_Free @0x1EC, 4 bytes LE
    struct.pack_into("<I", image, offset + 508, 0xAA550000)  # FSI_TrailSig @0x1FC, 4 bytes LE


def format_volume(
    image: bytearray, *, sector_size: int, sectors_per_cluster: int,
    reserved_sectors: int, fat_count: int, total_sectors: int,
    fat_sectors: int, seed: int, cluster_count: int,
) -> None:
    """Write the FAT32 primary/backup boot sectors and FSInfo structures."""
    boot = memoryview(image)[:sector_size]
    boot[0:3] = b"\xeb\x58\x90"  # BS_jmpBoot @0x00, 3 bytes
    boot[3:11] = b"MSWIN4.1"  # BS_OEMName @0x03, 8 bytes
    struct.pack_into("<H", boot, 0x0B, sector_size)  # BPB_BytsPerSec @0x0B, 2 bytes LE
    boot[0x0D] = sectors_per_cluster  # BPB_SecPerClus @0x0D, 1 byte
    struct.pack_into("<H", boot, 0x0E, reserved_sectors)  # BPB_RsvdSecCnt @0x0E, 2 bytes LE
    boot[0x10] = fat_count  # BPB_NumFATs @0x10, 1 byte
    struct.pack_into("<H", boot, 0x11, 0)  # BPB_RootEntCnt @0x11, 2 bytes LE
    struct.pack_into("<H", boot, 0x13, 0)  # BPB_TotSec16 @0x13, 2 bytes LE
    boot[0x15] = 0xF8  # BPB_Media @0x15, 1 byte
    struct.pack_into("<H", boot, 0x16, 0)  # BPB_FATSz16 @0x16, 2 bytes LE
    struct.pack_into("<H", boot, 0x18, 63)  # BPB_SecPerTrk @0x18, 2 bytes LE
    struct.pack_into("<H", boot, 0x1A, 255)  # BPB_NumHeads @0x1A, 2 bytes LE
    struct.pack_into("<I", boot, 0x1C, 0)  # BPB_HiddSec @0x1C, 4 bytes LE
    struct.pack_into("<I", boot, 0x20, total_sectors)  # BPB_TotSec32 @0x20, 4 bytes LE
    struct.pack_into("<I", boot, 0x24, fat_sectors)  # BPB_FATSz32 @0x24, 4 bytes LE
    struct.pack_into("<H", boot, 0x28, 0)  # BPB_ExtFlags @0x28, 2 bytes LE
    struct.pack_into("<H", boot, 0x2A, 0)  # BPB_FSVer @0x2A, 2 bytes LE
    struct.pack_into("<I", boot, 0x2C, 2)  # BPB_RootClus @0x2C, 4 bytes LE
    struct.pack_into("<H", boot, 0x30, 1)  # BPB_FSInfo @0x30, 2 bytes LE
    struct.pack_into("<H", boot, 0x32, 6)  # BPB_BkBootSec @0x32, 2 bytes LE
    boot[0x40] = 0x80  # BS_DrvNum @0x40, 1 byte
    boot[0x41] = 0  # BS_Reserved1 @0x41, 1 byte
    boot[0x42] = 0x29  # BS_BootSig @0x42, 1 byte
    struct.pack_into("<I", boot, 0x43, seed & 0xFFFFFFFF)  # BS_VolID @0x43, 4 bytes LE
    boot[0x47:0x52] = b"TRACE TEST "  # BS_VolLab @0x47, 11 bytes
    boot[0x52:0x5A] = b"FAT32   "  # BS_FilSysType @0x52, 8 bytes
    boot[510:512] = b"\x55\xaa"  # BS_Signature @0x1FE, 2 bytes LE
    image[6 * sector_size:7 * sector_size] = boot  # backup boot sector @sector 6
    write_fsinfo(image, sector_size, 1, cluster_count - 1, 3)
    write_fsinfo(image, sector_size, 7, cluster_count - 1, 3)
