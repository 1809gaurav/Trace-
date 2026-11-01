"""Sector-aligned signature carving with full-content validation."""

from __future__ import annotations

import hashlib
import mmap
from dataclasses import dataclass
from typing import Iterable

from engine.config import (
    JPEG_MAX_SIZE_BYTES,
    MAX_FOOTER_CANDIDATES,
    PDF_MAX_SIZE_BYTES,
    PNG_MAX_SIZE_BYTES,
    SCAN_ALIGNMENT,
    DVR_MAX_FILE_BYTES,
)
from engine.dvrlike import DVRXParser
from engine.validators import png_length, validate_dvr, validate_jpeg, validate_pdf, validate_png


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ImageBuffer = bytes | bytearray | mmap.mmap


@dataclass(frozen=True)
class CarvedFile:
    """A fully validated contiguous object found by signature."""

    file_type: str
    data: bytes
    offsets: list[dict[str, int]]
    sha256: str
    source: str = "carver"
    name: str | None = None


class SignatureCarver:
    """Find aligned media headers and accept only candidates that fully validate."""

    def __init__(
        self,
        sector_alignment: int = SCAN_ALIGNMENT,
        claimed_ranges: Iterable[dict[str, int] | tuple[int, int]] = (),
        excluded_ranges: Iterable[dict[str, int] | tuple[int, int]] = (),
    ):
        if sector_alignment < 1:
            raise ValueError("sector alignment must be positive")
        self.sector_alignment = sector_alignment
        self.claimed_ranges = [
            (item["start"], item["end"]) if isinstance(item, dict) else item
            for item in claimed_ranges
        ]
        self.excluded_ranges = [
            (item["start"], item["end"]) if isinstance(item, dict) else item
            for item in excluded_ranges
        ]

    def _overlaps_claimed(self, start: int, end: int) -> bool:
        return any(start < known_end and known_start < end
                   for known_start, known_end in self.claimed_ranges + self.excluded_ranges)

    def _starts(self, image: ImageBuffer, signature: bytes):
        cursor = 0
        while True:
            start = image.find(signature, cursor)
            if start < 0:
                return
            cursor = start + 1
            if start % self.sector_alignment == 0:
                yield start

    def _make(self, file_type: str, data: bytes, start: int) -> CarvedFile:
        end = start + len(data)
        self.claimed_ranges.append((start, end))
        return CarvedFile(
            file_type=file_type, data=data,
            offsets=[{"start": start, "end": end}],
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def _carve_jpeg(self, image: ImageBuffer, start: int) -> CarvedFile | None:
        limit = min(len(image), start + JPEG_MAX_SIZE_BYTES)
        footer = image.find(b"\xff\xd9", start + 3, limit)
        attempts = 0
        while footer >= 0 and attempts < MAX_FOOTER_CANDIDATES:
            end = footer + 2
            if not self._overlaps_claimed(start, end):
                data = bytes(image[start:end])
                if validate_jpeg(data).ok:
                    return self._make("jpeg", data, start)
            attempts += 1
            footer = image.find(b"\xff\xd9", footer + 2, limit)
        return None

    def _carve_png(self, image: ImageBuffer, start: int) -> CarvedFile | None:
        end_limit = min(len(image), start + PNG_MAX_SIZE_BYTES)
        data = bytes(image[start:end_limit])
        length = png_length(data)
        if length is None:
            return None
        end = start + length
        if self._overlaps_claimed(start, end):
            return None
        candidate = data[:length]
        if not validate_png(candidate).ok:
            return None
        return self._make("png", candidate, start)

    def _carve_pdf(self, image: ImageBuffer, start: int) -> CarvedFile | None:
        limit = min(len(image), start + PDF_MAX_SIZE_BYTES)
        next_header = image.find(b"%PDF-", start + 5, limit)
        if next_header >= 0:
            limit = next_header
        footer = image.find(b"%%EOF", start + 5, limit)
        attempts = 0
        while footer >= 0 and attempts < MAX_FOOTER_CANDIDATES:
            end = footer + 5
            if image[end:end + 2] == b"\r\n":
                end += 2
            elif image[end:end + 1] in (b"\r", b"\n"):
                end += 1
            if not self._overlaps_claimed(start, end):
                data = bytes(image[start:end])
                if validate_pdf(data).ok:
                    return self._make("pdf", data, start)
            attempts += 1
            footer = image.find(b"%%EOF", footer + 5, limit)
        return None

    def _carve_dvr(self, image: ImageBuffer, start: int) -> CarvedFile | None:
        limit = min(len(image), start + DVR_MAX_FILE_BYTES)
        parsed = DVRXParser().parse(bytes(image[start:limit]))
        if not parsed.ok or not 20 <= parsed.frame_count <= 40:
            return None
        data = bytes(image[start:start + parsed.bytes_consumed])
        end = start + len(data)
        if self._overlaps_claimed(start, end) or not validate_dvr(data).ok:
            return None
        return self._make("dvr", data, start)

    def carve(self, image: ImageBuffer) -> list[CarvedFile]:
        """Scan image signatures using bounded ``find`` operations, never bytewise loops."""
        found: list[CarvedFile] = []
        for start in self._starts(image, b"DVRX"):
            item = self._carve_dvr(image, start)
            if item is not None:
                found.append(item)
        for start in self._starts(image, b"\xff\xd8\xff"):
            item = self._carve_jpeg(image, start)
            if item is not None:
                found.append(item)
        for start in self._starts(image, PNG_SIGNATURE):
            item = self._carve_png(image, start)
            if item is not None:
                found.append(item)
        for start in self._starts(image, b"%PDF-"):
            item = self._carve_pdf(image, start)
            if item is not None:
                found.append(item)
        return sorted(found, key=lambda item: item.offsets[0]["start"])
