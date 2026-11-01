"""8.3 and VFAT long-name directory entry serialization."""

from __future__ import annotations

import math
import struct
from datetime import datetime
from pathlib import Path


def short_name(name: str, existing: set[bytes]) -> bytes:
    """Create a valid unique 8.3 alias for an ASCII filename."""
    path = Path(name)
    base, extension = path.stem.upper(), path.suffix[1:].upper()
    allowed = "$%'-_@~`!(){}^#&"
    if not base or not base.isascii() or not extension.isascii() or any(
        not (character.isalnum() or character in allowed) for character in base + extension
    ):
        raise ValueError(f"invalid FAT short name: {name}")
    base = "".join(character for character in base if character.isalnum() or character in allowed)
    extension = "".join(
        character for character in extension if character.isalnum() or character in allowed
    )
    if len(base) <= 8 and len(extension) <= 3:
        candidate = base.ljust(8).encode("ascii") + extension.ljust(3).encode("ascii")
        if candidate not in existing:
            return candidate
    for suffix in range(1, 10_000):
        tail = f"~{suffix}"
        alias = base[:8 - len(tail)] + tail
        candidate = alias.ljust(8).encode("ascii") + extension[:3].ljust(3).encode("ascii")
        if candidate not in existing:
            return candidate
    raise ValueError("could not create a unique FAT short name")


def long_name_entry_count(name: str, short: bytes) -> int:
    """Return the number of VFAT entries needed for this name."""
    long_name = Path(name).name
    alias = short[:8].decode().rstrip() + (
        "." + short[8:].decode().rstrip() if short[8:].strip() else ""
    )
    if long_name.upper() == alias.upper():
        return 0
    return math.ceil((len(long_name.encode("utf-16le")) // 2 + 1) / 13)


def write_long_name_entries(image: bytearray, name: str, short: bytes, entry_offset: int) -> None:
    """Write the ordered VFAT entries immediately before the short entry."""
    count = long_name_entry_count(name, short)
    if not count:
        return
    units_bytes = Path(name).name.encode("utf-16le")
    units = [units_bytes[index] | units_bytes[index + 1] << 8
             for index in range(0, len(units_bytes), 2)]
    units.append(0)
    units.extend([0xFFFF] * (count * 13 - len(units)))
    checksum = 0
    for value in short:
        checksum = (((checksum & 1) << 7) + (checksum >> 1) + value) & 0xFF
    positions = (1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30)
    for sequence in range(count, 0, -1):
        offset = entry_offset - (count - sequence + 1) * 32
        item = bytearray(32)
        item[0] = sequence | (0x40 if sequence == count else 0)  # LDIR_Ord @0x00, 1 byte
        item[11] = 0x0F  # LDIR_Attr @0x0B, 1 byte
        item[12] = 0  # LDIR_Type @0x0C, 1 byte
        item[13] = checksum  # LDIR_Chksum @0x0D, 1 byte
        struct.pack_into("<H", item, 26, 0)  # LDIR_FstClusLO @0x1A, 2 bytes LE
        for field_offset, unit in zip(positions, units[(sequence - 1) * 13:sequence * 13]):
            struct.pack_into(
                "<H", item, field_offset, unit
            )  # LDIR_Name1/2/3 @field_offset, 2 bytes LE
        image[offset:offset + 32] = item  # LDIR directory entry @offset, 32 bytes


def make_file_entry(
    short: bytes, first_cluster: int, size: int, timestamps: dict[str, str],
) -> bytearray:
    """Build a standard FAT32 short directory entry."""
    entry = bytearray(32)
    entry[:11] = short  # DIR_Name @0x00, 11 bytes
    entry[11] = 0x20  # DIR_Attr @0x0B, 1 byte
    modified = timestamps.get("modified", "2026-01-01T10:00:00")
    created_date, created_time = _fat_date_time(timestamps.get("created", modified))
    modified_date, modified_time = _fat_date_time(modified)
    accessed_date, _ = _fat_date_time(timestamps.get("accessed", modified))
    struct.pack_into("<H", entry, 14, created_time)  # DIR_CrtTime @0x0E, 2 bytes LE
    struct.pack_into("<H", entry, 16, created_date)  # DIR_CrtDate @0x10, 2 bytes LE
    struct.pack_into("<H", entry, 18, accessed_date)  # DIR_LastAccessDate @0x12, 2 bytes LE
    struct.pack_into("<H", entry, 22, modified_time)  # DIR_WrtTime @0x16, 2 bytes LE
    struct.pack_into("<H", entry, 24, modified_date)  # DIR_WrtDate @0x18, 2 bytes LE
    struct.pack_into("<H", entry, 20, first_cluster >> 16)  # DIR_FstClusHI @0x14, 2 bytes LE
    struct.pack_into("<H", entry, 26, first_cluster & 0xFFFF)  # DIR_FstClusLO @0x1A, 2 bytes LE
    struct.pack_into("<I", entry, 28, size)  # DIR_FileSize @0x1C, 4 bytes LE
    return entry


def _fat_date_time(value: str) -> tuple[int, int]:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    date = ((parsed.year - 1980) << 9) | (parsed.month << 5) | parsed.day
    time_value = (parsed.hour << 11) | (parsed.minute << 5) | (parsed.second // 2)
    return date, time_value


def mark_deleted(image: bytearray, entry_offset: int, root_offset: int) -> None:
    """Set the short name's first byte and its preceding VFAT entries to deleted."""
    short = bytes(image[entry_offset:entry_offset + 11])
    checksum = 0
    for value in short:
        checksum = (((checksum & 1) << 7) + (checksum >> 1) + value) & 0xFF
    image[entry_offset] = 0xE5  # DIR_Name[0] @0x00, 1 byte: deleted marker
    offset = entry_offset - 32
    while offset >= root_offset:
        if image[offset + 11] != 0x0F or image[offset + 13] != checksum:
            break
        image[offset] = 0xE5  # LDIR_Ord @0x00, 1 byte: deleted marker
        offset -= 32
