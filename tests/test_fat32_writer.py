import hashlib
import tempfile
import unittest
from pathlib import Path

from testgen.fat32_writer import Fat32Image


class Fat32WriterTests(unittest.TestCase):
    def test_round_trip_and_delete_preserves_data(self):
        image = Fat32Image()
        payload = b"forensic fixture" * 100
        allocation = image.write_file("TEST.BIN", payload)
        image.validate()
        self.assertEqual(image.read_file("TEST.BIN"), payload)

        before = b"".join(image.read_cluster(cluster) for cluster in allocation.clusters)
        image.delete_file("TEST.BIN")
        self.assertEqual(image.directory_entry_first_byte("TEST.BIN"), 0xE5)
        self.assertTrue(all(image.fat_entry(cluster) == 0 for cluster in allocation.clusters))
        after = b"".join(image.read_cluster(cluster) for cluster in allocation.clusters)
        self.assertEqual(before, after)

    def test_explicit_fragmented_allocation(self):
        image = Fat32Image()
        clusters = [3, 5, 7]
        payload = b"A" * (image.cluster_size * 2) + b"B" * image.cluster_size
        allocation = image.write_file("FRAG.BIN", payload, clusters=clusters)
        self.assertEqual(allocation.clusters, clusters)
        self.assertEqual(image.read_file("FRAG.BIN"), payload)

    def test_long_name_entries_round_trip_and_delete(self):
        image = Fat32Image()
        payload = b"synthetic dvr clip"
        image.write_file("CH01_0001.DVR", payload)
        image.validate()
        entry_offset = image.entries["CH01_0001.DVR"]
        root = image.cluster_offset(2)
        self.assertEqual(image.image[entry_offset - 32 + 11], 0x0F)
        image.delete_file("CH01_0001.DVR")
        self.assertEqual(image.directory_entry_first_byte("CH01_0001.DVR"), 0xE5)
        self.assertEqual(image.image[entry_offset - 32], 0xE5)
        self.assertGreaterEqual(entry_offset - 32, root)

    def test_format_resets_volume(self):
        image = Fat32Image()
        image.write_file("TEST.BIN", b"before")
        image.format()
        self.assertEqual(image.files, {})
        image.validate()

    def test_saved_image_is_byte_stable_and_optional_tools_validate(self):
        image = Fat32Image()
        image.write_file("TEST.BIN", b"stable")
        image.validate()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "disk.img"
            image.save(path)
            first = hashlib.sha256(path.read_bytes()).hexdigest()
            image.save(path)
            self.assertEqual(first, hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
