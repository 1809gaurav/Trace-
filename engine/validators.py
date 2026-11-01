"""Pure media validators shared by FAT recovery and signature carving."""

from __future__ import annotations

import io
import struct
import warnings
import zlib
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from engine.dvrlike import DVRXParser


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class ValidationResult:
    """Validation status and lightweight decode information."""

    ok: bool
    decoded_fraction: float
    width: int | None
    height: int | None
    notes: tuple[str, ...] = ()
    consumed_bytes: int | None = None


def _failure(note: str, width: int | None = None, height: int | None = None) -> ValidationResult:
    return ValidationResult(False, 0.0, width, height, (note,))


def validate_jpeg(data: bytes) -> ValidationResult:
    """Require Pillow to verify and fully load a JPEG without decode warnings."""
    if not data.startswith(b"\xff\xd8\xff"):
        return _failure("missing JPEG start marker")
    if not data.endswith(b"\xff\xd9"):
        return _failure("missing terminal JPEG end marker")
    if not jpeg_entropy_prefix_is_plausible(data):
        return _failure("invalid JPEG marker or entropy sequence")
    width = height = None
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "JPEG":
                    return _failure("signature does not decode as JPEG")
                width, height = image.size
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                width, height = image.size
            if caught:
                return _failure("decoder emitted a warning", width, height)
    except (
        OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError,
    ) as error:
        return _failure(f"JPEG decode failed: {error}", width, height)
    return ValidationResult(True, 1.0, width, height, (), len(data))


def jpeg_entropy_prefix_is_plausible(data: bytes) -> bool:
    """Check JPEG marker structure and byte stuffing through the available prefix."""
    if not data.startswith(b"\xff\xd8"):
        return False
    offset = 2
    while offset < len(data):
        marker_start = offset
        if data[offset] != 0xFF:  # JPEG marker prefix @offset, 1 byte
            return False
        while offset < len(data) and data[offset] == 0xFF:  # JPEG marker fill @offset, 1 byte
            offset += 1
        if offset >= len(data):
            return True
        marker = data[offset]  # JPEG marker code @offset, 1 byte
        offset += 1
        if marker == 0xD9:  # EOI marker @offset-1, 1 byte
            return True
        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            return marker == 0xDA
        segment_length = struct.unpack_from(">H", data, offset)[0]  # JPEG segment length @offset, 2 bytes BE
        if segment_length < 2 or offset + segment_length > len(data):
            return False
        offset += segment_length
        if marker != 0xDA:  # SOS marker @offset-1, 1 byte
            continue
        while offset < len(data):
            if data[offset] != 0xFF:  # JPEG entropy byte @offset, 1 byte
                offset += 1
                continue
            entropy_marker_start = offset
            while offset < len(data) and data[offset] == 0xFF:  # JPEG entropy marker fill @offset
                offset += 1
            if offset >= len(data):
                return True
            entropy_marker = data[offset]  # JPEG entropy marker code @offset, 1 byte
            if entropy_marker == 0x00 or 0xD0 <= entropy_marker <= 0xD7:
                offset += 1
                continue
            offset = entropy_marker_start
            break
        if offset >= len(data):
            return True
    return False


def jpeg_entropy_chunk_is_plausible(data: bytes, previous_ff: bool = False) -> bool:
    """Check only a candidate entropy gap, using C-level byte searches."""
    return jpeg_entropy_chunk_prefix_length(data, previous_ff) == len(data)


def jpeg_entropy_chunk_prefix_length(data: bytes, previous_ff: bool = False) -> int:
    """Return bytes that could continue JPEG entropy before an invalid marker."""
    offset = 0
    if previous_ff and data:
        following = data[0]  # JPEG entropy marker code at fragment boundary, 1 byte
        if following != 0x00 and not 0xD0 <= following <= 0xD7:
            return 0
        offset = 1
    while True:
        marker_offset = data.find(b"\xff", offset)
        if marker_offset < 0:
            return len(data)
        if marker_offset + 1 >= len(data):
            return len(data)
        marker = data[marker_offset + 1]  # JPEG entropy marker code @marker+1, 1 byte
        if marker != 0x00 and not 0xD0 <= marker <= 0xD7:
            return marker_offset
        offset = marker_offset + 2


def png_length(data: bytes) -> int | None:
    """Return a structurally valid PNG length after checking every chunk CRC."""
    if not data.startswith(PNG_SIGNATURE):
        return None
    offset = len(PNG_SIGNATURE)
    saw_header = False
    while offset + 12 <= len(data):
        chunk_length = struct.unpack_from(">I", data, offset)[0]  # PNG chunk length @chunk offset, 4 bytes BE
        chunk_type = data[offset + 4:offset + 8]  # PNG chunk type @chunk offset+4, 4 bytes
        chunk_end = offset + 12 + chunk_length
        if chunk_end > len(data):
            return None
        chunk_data = data[offset + 8:offset + 8 + chunk_length]  # PNG chunk data @chunk offset+8
        expected_crc = struct.unpack_from(">I", data, offset + 8 + chunk_length)[0]  # PNG CRC @chunk end-4, 4 bytes BE
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(chunk_data, actual_crc) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            return None
        if not saw_header:
            if chunk_type != b"IHDR" or chunk_length != 13:
                return None
            saw_header = True
        if chunk_type == b"IEND":
            return chunk_end if chunk_length == 0 and saw_header else None
        offset = chunk_end
    return None


def validate_png(data: bytes) -> ValidationResult:
    """Check PNG chunk CRCs and require Pillow to verify and fully load it."""
    length = png_length(data)
    if length is None:
        return _failure("PNG chunks or CRCs are invalid")
    width = height = None
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with Image.open(io.BytesIO(data[:length])) as image:
                if image.format != "PNG":
                    return _failure("signature does not decode as PNG")
                width, height = image.size
                image.verify()
            with Image.open(io.BytesIO(data[:length])) as image:
                image.load()
                width, height = image.size
            if caught:
                return _failure("decoder emitted a warning", width, height)
    except (
        OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError,
    ) as error:
        return _failure(f"PNG decode failed: {error}", width, height)
    return ValidationResult(True, 1.0, width, height, (), length)


def validate_pdf(data: bytes) -> ValidationResult:
    """Require a PDF header, terminal EOF marker, parseable xref, and a page."""
    if not data.startswith(b"%PDF-"):
        return _failure("missing PDF header")
    if not data.rstrip().endswith(b"%%EOF"):
        return _failure("missing terminal PDF EOF marker")
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        page_count = len(reader.pages)
    except (PdfReadError, PdfStreamError, OSError, ValueError, IndexError, struct.error) as error:
        return _failure(f"PDF parse failed: {error}")
    if page_count < 1:
        return _failure("PDF contains no pages")
    return ValidationResult(True, 1.0, None, None, (f"{page_count} page(s)",), len(data))


def validate_dvr(data: bytes) -> ValidationResult:
    """Validate a DVRX clip and every JPEG frame in its valid frame prefix."""
    parsed = DVRXParser().parse(data)
    if not parsed.ok or not 20 <= parsed.frame_count <= 40:
        return _failure("DVRX must contain 20 to 40 valid frames")
    for index, frame in enumerate(parsed.frame_payloads):
        if not validate_jpeg(frame).ok:
            return _failure(f"DVRX frame {index} is not a valid JPEG")
    return ValidationResult(
        True, 1.0, None, None, parsed.warnings, parsed.bytes_consumed
    )


def validate_media(file_type: str, data: bytes) -> ValidationResult:
    """Dispatch supported media validation without consulting external state."""
    if file_type == "jpeg":
        return validate_jpeg(data)
    if file_type == "png":
        return validate_png(data)
    if file_type == "pdf":
        return validate_pdf(data)
    if file_type == "dvr":
        return validate_dvr(data)
    return _failure(f"unsupported media type: {file_type}")
