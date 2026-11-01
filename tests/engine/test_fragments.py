import io
import math
import random
import unittest

from PIL import Image

from engine.config import FRAGMENT_UNKNOWN_CANDIDATES_PER_FILE
from engine.fat32 import FragmentHint
from engine.fragments import reconstruct_fragments


CLUSTER_SIZE = 1024
DATA_START = 512


def jpeg_bytes():
    output = io.BytesIO()
    pixels = random.Random(42).randbytes(320 * 240 * 3)
    Image.frombytes("RGB", (320, 240), pixels).save(output, format="JPEG", quality=85)
    return output.getvalue()


def make_image(payload, pieces):
    total_clusters = math.ceil(len(payload) / CLUSTER_SIZE)
    start_cluster = 10
    image = bytearray(DATA_START + 160 * CLUSTER_SIZE)
    piece_sizes = [total_clusters // pieces] * pieces
    for index in range(total_clusters % pieces):
        piece_sizes[index] += 1
    cursor = start_cluster
    data_cursor = 0
    gap_clusters = []
    ranges = []
    for piece_index, count in enumerate(piece_sizes):
        start = DATA_START + (cursor - 2) * CLUSTER_SIZE
        length = min(count * CLUSTER_SIZE, len(payload) - data_cursor)
        image[start:start + length] = payload[data_cursor:data_cursor + length]
        ranges.append((start, start + length))
        data_cursor += length
        cursor += count
        if piece_index < pieces - 1:
            gap_clusters.append(cursor)
            gap_start = DATA_START + (cursor - 2) * CLUSTER_SIZE
            image[gap_start:gap_start + 3 * CLUSTER_SIZE] = random.Random(
                42 + piece_index
            ).randbytes(3 * CLUSTER_SIZE)
            cursor += 3
    hint = FragmentHint(
        name="_RAG0001.JPG", file_type="jpeg", size_bytes=len(payload),
        start_cluster=start_cluster, timestamps={},
    )
    return image, hint, ranges, gap_clusters


class FragmentTests(unittest.TestCase):
    def test_reconstructs_two_jpeg_fragments_with_search_cost(self):
        payload = jpeg_bytes()
        image, hint, ranges, gaps = make_image(payload, 2)

        recovered = reconstruct_fragments(
            image, [hint], data_start=DATA_START, cluster_size=CLUSTER_SIZE,
            cluster_count=160, claimed_clusters=set(),
        )

        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].data, payload)
        self.assertEqual(recovered[0].offsets, [
            {"start": ranges[0][0], "end": ranges[0][1]},
            {"start": ranges[1][0], "end": ranges[1][1]},
        ])
        self.assertGreater(recovered[0].search_cost, 0)
        self.assertEqual(len(gaps), 1)

    def test_does_not_fabricate_three_fragment_jpeg(self):
        image, hint, _ranges, _gaps = make_image(jpeg_bytes(), 3)
        recovered = reconstruct_fragments(
            image, [hint], data_start=DATA_START, cluster_size=CLUSTER_SIZE,
            cluster_count=160, claimed_clusters=set(),
        )
        self.assertFalse(recovered)

    def test_unknown_header_hints_use_bounded_search(self):
        payload = jpeg_bytes()
        image, _hint, _ranges, _gaps = make_image(payload, 2)

        recovered = reconstruct_fragments(
            image, [], data_start=DATA_START, cluster_size=CLUSTER_SIZE,
            cluster_count=160, claimed_clusters=set(),
        )

        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].data, payload)
        self.assertIsNone(recovered[0].name)
        self.assertLessEqual(
            recovered[0].search_cost, FRAGMENT_UNKNOWN_CANDIDATES_PER_FILE
        )


if __name__ == "__main__":
    unittest.main()
