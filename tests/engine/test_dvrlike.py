import struct
import unittest
import zlib

from engine.dvrlike import DVRXParser, PARSERS, ContainerParser


def build_clip(frames):
    output = bytearray(struct.pack("<4sHHI", b"DVRX", 1, 2, 0))
    for index, timestamp, payload in frames:
        output.extend(struct.pack("<4sIQI", b"FRM0", index, timestamp, len(payload)))
        output.extend(payload)
        output.extend(struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF))
    return bytes(output)


class DvrLikeTests(unittest.TestCase):
    def test_detect_parse_metadata_and_registry(self):
        clip = build_clip([
            (0, 1_767_264_000_000, b"frame-0"),
            (1, 1_767_264_001_000, b"frame-1"),
        ])
        parser = DVRXParser()
        self.assertIsInstance(parser, ContainerParser)
        self.assertEqual(len(PARSERS), 1)
        self.assertTrue(parser.detect(clip))

        result = parser.parse(clip)
        self.assertTrue(result.ok)
        self.assertEqual(result.frame_count, 2)
        self.assertEqual(result.metadata["frame_count"], 2)
        self.assertEqual(result.frame_payloads, (b"frame-0", b"frame-1"))
        self.assertEqual(result.bytes_consumed, len(clip))
        self.assertEqual(result.metadata["start_time"], "2026-01-01T10:40:00.000Z")

    def test_bad_crc_stops_but_preserves_prior_frames(self):
        clip = bytearray(build_clip([
            (0, 1_767_264_000_000, b"valid"),
            (1, 1_767_264_001_000, b"bad"),
        ]))
        clip[-1] ^= 0x01

        result = DVRXParser().parse(bytes(clip))
        self.assertTrue(result.ok)
        self.assertEqual(result.frame_count, 1)
        self.assertEqual(result.frame_payloads, (b"valid",))
        self.assertTrue(result.warnings)

    def test_invalid_frame_order_and_truncation_are_reported(self):
        non_contiguous = build_clip([
            (0, 1_767_264_000_000, b"first"),
            (2, 1_767_264_001_000, b"third"),
        ])
        result = DVRXParser().parse(non_contiguous)
        self.assertEqual(result.frame_count, 1)
        self.assertTrue(result.warnings)

        truncated = build_clip([(0, 1_767_264_000_000, b"frame")])[:-2]
        result = DVRXParser().parse(truncated)
        self.assertEqual(result.frame_count, 0)
        self.assertFalse(result.ok)

    def test_detect_rejects_non_dvrx_data(self):
        parser = DVRXParser()
        self.assertFalse(parser.detect(b"not a clip"))
        self.assertFalse(parser.parse(b"bad").ok)


if __name__ == "__main__":
    unittest.main()
