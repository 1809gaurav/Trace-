"""Reproducible media payloads for forensic test images."""

from __future__ import annotations

import io
import random
from pathlib import Path
from typing import Literal

from PIL import Image, ImageChops, ImageDraw

PayloadType = Literal["jpeg", "png", "pdf"]


def _image(seed: int, width: int, height: int, *, compact: bool = False) -> Image.Image:
    rng = random.Random(seed)
    vertical = Image.linear_gradient("L").resize((width, height))
    horizontal = vertical.rotate(90, expand=True).resize((width, height))
    diagonal = ImageChops.add(vertical, horizontal, scale=2)
    image = Image.merge("RGB", (
        horizontal.point(lambda value: (value * 3 + seed * 17) % 256),
        vertical.point(lambda value: (value * 5 + seed * 23) % 256),
        diagonal.point(lambda value: (value * 2 + seed * 31) % 256),
    ))
    draw = ImageDraw.Draw(image)
    count = 4 if compact else 24
    for _ in range(count):
        x1 = rng.randrange(width)
        y1 = rng.randrange(height)
        x2 = min(width - 1, x1 + rng.randrange(8, max(9, width // 3)))
        y2 = min(height - 1, y1 + rng.randrange(8, max(9, height // 3)))
        color = tuple(rng.randrange(32, 256) for _ in range(3))
        if compact:
            draw.rectangle((x1, y1, x2, y2), fill=color)
        else:
            draw.ellipse((x1, y1, x2, y2), fill=color, outline=(0, 0, 0), width=2)
    draw.text((8, 8), f"TRACE {seed:04d}", fill="white", stroke_width=1, stroke_fill="black")
    return image


def make_jpeg(seed: int, *, compact: bool = False) -> bytes:
    """Return a seeded, Pillow-generated JPEG image."""
    rng = random.Random(seed)
    width = 160 if compact else rng.randint(320, 800)
    height = 120 if compact else rng.randint(240, 600)
    output = io.BytesIO()
    _image(seed, width, height, compact=compact).save(
        output, format="JPEG", quality=38 if compact else 75, optimize=False,
        progressive=False, subsampling=2 if compact else 0,
    )
    payload = output.getvalue()
    if not payload.startswith(b"\xff\xd8") or not payload.endswith(b"\xff\xd9"):
        raise ValueError("Pillow produced an invalid JPEG")
    if not compact and not 8 * 1024 <= len(payload) <= 90 * 1024:
        raise ValueError(f"generated JPEG outside 8-90 KiB: {len(payload)}")
    validate_payload("jpeg", payload)
    return payload


def make_png(seed: int) -> bytes:
    """Return a seeded PNG payload."""
    output = io.BytesIO()
    _image(seed, 192, 144).save(output, format="PNG", optimize=False, compress_level=6)
    payload = output.getvalue()
    validate_payload("png", payload)
    return payload


def _fallback_pdf(text: str) -> bytes:
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 14 Tf 72 720 Td ({safe}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Title (Forensic test document) /Creator (ForensicRecover testgen) /CreationDate (D:20260101100000Z) >>",
    ]
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R /Info 6 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(output)


def make_pdf(seed: int) -> bytes:
    """Return a deterministic one-page PDF with fixed metadata."""
    try:
        from reportlab.pdfgen import canvas
    except ImportError:
        payload = _fallback_pdf(f"Forensic test document {seed:04d}")
    else:
        output = io.BytesIO()
        document = canvas.Canvas(output, pagesize=(612, 792), invariant=1, pageCompression=0)
        document.setTitle("Forensic test document")
        document.setAuthor("ForensicRecover testgen")
        document.setCreator("ForensicRecover testgen")
        document.drawString(72, 720, f"Forensic test document {seed:04d}")
        document.showPage()
        document.save()
        payload = output.getvalue()
    if not payload.startswith(b"%PDF-") or b"%%EOF" not in payload:
        raise ValueError("generated PDF failed structural validation")
    validate_payload("pdf", payload)
    return payload


def validate_payload(kind: PayloadType, payload: bytes) -> None:
    """Decode a generated payload before it is written to a disk image."""
    if kind in ("jpeg", "png"):
        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
    else:
        if not payload.startswith(b"%PDF-") or not payload.rstrip().endswith(b"%%EOF"):
            raise ValueError("invalid PDF payload")
        try:
            xref_offset = int(payload.rsplit(b"startxref\n", 1)[1].splitlines()[0])
        except (IndexError, ValueError) as error:
            raise ValueError("PDF is missing a valid xref offset") from error
        if payload[xref_offset:xref_offset + 4] != b"xref":
            raise ValueError("PDF xref offset does not point to an xref table")


def write_original(path: Path, payload: bytes) -> None:
    """Write a generated original to its inspection directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
