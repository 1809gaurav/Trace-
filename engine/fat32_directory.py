"""FAT32 directory-entry decoding and filename helpers."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class DirectoryEntry:
    """Decoded FAT short directory entry."""

    name: str
    attributes: int
    start_cluster: int
    size_bytes: int
    deleted: bool
    timestamps: dict[str, str | None]

    @property
    def is_directory(self) -> bool:
        return bool(self.attributes & 0x10)

    @property
    def is_volume_label(self) -> bool:
        return bool(self.attributes & 0x08)


def _decode_timestamp(date_value: int, time_value: int, tenth: int = 0) -> str | None:
    year = 1980 + ((date_value >> 9) & 0x7F)
    month = (date_value >> 5) & 0x0F
    day = date_value & 0x1F
    hour = (time_value >> 11) & 0x1F
    minute = (time_value >> 5) & 0x3F
    second = (time_value & 0x1F) * 2 + tenth // 100
    microsecond = (tenth % 100) * 10_000
    try:
        value = datetime(
            year, month, day, hour, minute, second, microsecond, tzinfo=timezone.utc
        )
    except ValueError:
        return None
    precision = "microseconds" if microsecond else "seconds"
    return value.isoformat(timespec=precision).replace("+00:00", "Z")


def decode_directory_entry(raw: bytes | bytearray | memoryview) -> DirectoryEntry:
    """Decode a 32-byte short entry, including FAT timestamps and deletion state."""
    if len(raw) != 32:
        raise ValueError("FAT directory entry must be exactly 32 bytes")
    deleted = raw[0] == 0xE5  # DIR_Name[0] @0x00, deleted-entry marker
    base = bytes(raw[0:8])  # DIR_Name @0x00, 8 bytes
    extension = bytes(raw[8:11])  # DIR_Name extension @0x08, 3 bytes
    if deleted:
        base_name = "_" + base[1:].decode("ascii", "replace").rstrip()
    else:
        if base[:1] == b"\x05":
            base = b"\xe5" + base[1:]
        base_name = base.decode("ascii", "replace").rstrip()
    extension_name = extension.decode("ascii", "replace").rstrip()
    name = f"{base_name}.{extension_name}" if extension_name else base_name

    attributes = raw[11]  # DIR_Attr @0x0B, 1 byte
    created_time = struct.unpack_from("<H", raw, 14)[0]  # DIR_CrtTime @0x0E, 2 bytes LE
    created_date = struct.unpack_from("<H", raw, 16)[0]  # DIR_CrtDate @0x10, 2 bytes LE
    accessed_date = struct.unpack_from("<H", raw, 18)[0]  # DIR_LstAccDate @0x12, 2 bytes LE
    modified_time = struct.unpack_from("<H", raw, 22)[0]  # DIR_WrtTime @0x16, 2 bytes LE
    modified_date = struct.unpack_from("<H", raw, 24)[0]  # DIR_WrtDate @0x18, 2 bytes LE
    high_cluster = struct.unpack_from("<H", raw, 20)[0]  # DIR_FstClusHI @0x14, 2 bytes LE
    low_cluster = struct.unpack_from("<H", raw, 26)[0]  # DIR_FstClusLO @0x1A, 2 bytes LE
    size_bytes = struct.unpack_from("<I", raw, 28)[0]  # DIR_FileSize @0x1C, 4 bytes LE
    timestamps = {
        "created": _decode_timestamp(created_date, created_time, raw[13]),  # DIR_CrtTimeTenth @0x0D
        "modified": _decode_timestamp(modified_date, modified_time),
        "accessed": _decode_timestamp(accessed_date, 0),
    }
    return DirectoryEntry(
        name=name, attributes=attributes, start_cluster=(high_cluster << 16) | low_cluster,
        size_bytes=size_bytes, deleted=deleted, timestamps=timestamps,
    )


def _decode_lfn(records: list[bytes], short_entry: bytes, deleted: bool) -> str | None:
    positions = (1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30)
    if not records:
        return None
    if deleted:
        ordered = list(reversed(records))
    else:
        ordered = sorted(records, key=lambda record: record[0] & 0x1F)
        short_name = short_entry[:11]
        checksum = 0
        for value in short_name:
            checksum = (((checksum & 1) << 7) + (checksum >> 1) + value) & 0xFF
        if any(record[11] != 0x0F or record[13] != checksum for record in ordered):
            return None
    units = []
    for record in ordered:
        units.extend(struct.unpack_from("<H", record, offset)[0] for offset in positions)  # LDIR_Name @field offsets, 2 bytes LE
    trimmed = []
    for unit in units:
        if unit in (0, 0xFFFF):
            break
        trimmed.append(unit)
    if not trimmed:
        return None
    try:
        name = b"".join(struct.pack("<H", unit) for unit in trimmed).decode("utf-16le")
    except UnicodeDecodeError:
        return None
    return ("_" + name[1:]) if deleted and name else name


def _file_type(name: str) -> str:
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return {
        "jpg": "jpeg", "jpeg": "jpeg", "png": "png", "pdf": "pdf",
        "dvr": "dvr", "mp4": "mp4",
    }.get(extension, "unknown")
