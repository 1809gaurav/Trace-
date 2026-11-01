import io
import struct
import unittest
import zlib

from PIL import Image

from engine.carver import SignatureCarver
from engine.validators import validate_dvr, validate_jpeg, validate_pdf, validate_png


def image_bytes(image_format):
    output = io.BytesIO()
    Image.new("RGB", (24, 16), (90, 120, 150)).save(output, format=image_format)
    return output.getvalue()


def minimal_pdf():
    output = bytearray(b"%PDF-1.4\n")
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>",
    )
    offsets = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii") + value + b"\nendobj\n")
    xref_offset = len(output)
    output.extend(b"xref\n0 4\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


def dvr_clip(frame_data):
    output = bytearray(struct.pack("<4sHHI", b"DVRX", 1, 1, 0))
    for index in range(20):
        output.extend(struct.pack("<4sIQI", b"FRM0", index, 1_767_225_600_000 + index * 1000, len(frame_data)))
        output.extend(frame_data)
        output.extend(struct.pack("<I", zlib.crc32(frame_data) & 0xFFFFFFFF))
    return bytes(output)


class ValidatorTests(unittest.TestCase):
    def test_jpeg_requires_complete_decode(self):
        jpeg = image_bytes("JPEG")
        self.assertTrue(validate_jpeg(jpeg).ok)
        self.assertFalse(validate_jpeg(jpeg[:-20]).ok)

    def test_png_checks_crc_and_pillow_decode(self):
        png = image_bytes("PNG")
        self.assertTrue(validate_png(png).ok)
        broken = bytearray(png)
        broken[-5] ^= 0x01
        self.assertFalse(validate_png(bytes(broken)).ok)

    def test_pdf_requires_parseable_xref_and_page(self):
        pdf = minimal_pdf()
        self.assertTrue(validate_pdf(pdf).ok)
        self.assertFalse(validate_pdf(pdf[:pdf.index(b"%%EOF")]).ok)
        bad_xref = pdf.replace(b"startxref\n", b"startxref\n999999\n", 1)
        self.assertFalse(validate_pdf(bad_xref).ok)

    def test_dvr_requires_valid_jpeg_frames(self):
        clip = dvr_clip(image_bytes("JPEG"))
        self.assertEqual(len(clip), validate_dvr(clip).consumed_bytes)


class CarverTests(unittest.TestCase):
    def test_jpeg_searches_past_embedded_eoi_candidate(self):
        jpeg = image_bytes("JPEG")
        embedded = b"metadata with \xff\xd9 marker"
        segment = b"\xff\xe1" + struct.pack(">H", len(embedded) + 2) + embedded
        wrapped = jpeg[:2] + segment + jpeg[2:]
        self.assertTrue(validate_jpeg(wrapped).ok)
        self.assertFalse(validate_jpeg(wrapped[:wrapped.index(b"\xff\xd9") + 2]).ok)

        carved = SignatureCarver(sector_alignment=1).carve(wrapped)
        jpeg_items = [item for item in carved if item.file_type == "jpeg"]
        self.assertEqual(len(jpeg_items), 1)
        self.assertEqual(jpeg_items[0].data, wrapped)

    def test_decoy_headers_are_not_emitted(self):
        data = b"\xff\xd8\xff" + b"random without an end marker" + b"\n%PDF-1.7\ntruncated"
        self.assertEqual(SignatureCarver(sector_alignment=1).carve(data), [])

    def test_png_and_pdf_carve_to_their_validated_ends(self):
        png = image_bytes("PNG")
        pdf = minimal_pdf()
        data = bytearray(512)
        data.extend(png)
        data.extend(bytes(512 - len(data) % 512))
        data.extend(pdf)

        carved = SignatureCarver().carve(data)
        self.assertEqual([item.file_type for item in carved], ["png", "pdf"])
        self.assertEqual(carved[0].data, png)
        self.assertEqual(carved[1].data, pdf)

    def test_dvrx_container_is_carved_using_valid_frame_prefix(self):
        clip = dvr_clip(image_bytes("JPEG"))
        carved = SignatureCarver(sector_alignment=1).carve(clip)
        self.assertEqual(len(carved), 1)
        self.assertEqual(carved[0].file_type, "dvr")
        self.assertEqual(carved[0].data, clip)

    def test_claimed_ranges_are_skipped(self):
        png = image_bytes("PNG")
        data = bytearray(512)
        data.extend(png)
        carved = SignatureCarver(claimed_ranges=[{"start": 512, "end": 512 + len(png)}]).carve(data)
        self.assertEqual(carved, [])

    def test_explicit_fragment_hints_exclude_contiguous_carving_at_the_start(self):
        jpeg = image_bytes("JPEG")
        data = bytearray(512)
        data.extend(jpeg)
        carved = SignatureCarver(
            sector_alignment=1, excluded_ranges=[(512, 515)]
        ).carve(data)
        self.assertEqual(carved, [])


if __name__ == "__main__":
    unittest.main()
