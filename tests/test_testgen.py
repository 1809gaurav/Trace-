import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from testgen.content import validate_payload
from testgen.make_image import generate, main
from testgen.scenarios import SCENARIOS


class TestGenerationTests(unittest.TestCase):
    def test_scenario_names(self):
        self.assertEqual(
            set(SCENARIOS),
            {"clean_deleted", "corrupted_fs", "fragmented", "demo_mixed", "empty_fs", "not_fat"},
        )

    def test_scenario_compositions_and_decoy_ranges(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            generate(root, seed=1337)
            truths = {
                name: json.loads((root / name / "ground_truth.json").read_text())
                for name in SCENARIOS
            }
            self.assertEqual(len(truths["clean_deleted"]["files"]), 13)
            self.assertEqual(sum(f["state"] == "deleted_contiguous" for f in truths["clean_deleted"]["files"]), 6)
            self.assertEqual(len(truths["corrupted_fs"]["files"]), 13)
            self.assertTrue(all(f["state"] == "fs_corrupted_contiguous" for f in truths["corrupted_fs"]["files"]))
            self.assertEqual(len(truths["fragmented"]["files"]), 7)
            self.assertEqual(
                sum(f["recoverable"] and f["expected_via"] == "reconstruction"
                    for f in truths["fragmented"]["files"]),
                3,
            )
            self.assertEqual(
                sum(not f["recoverable"] for f in truths["fragmented"]["files"]), 1
            )
            self.assertEqual(len(truths["demo_mixed"]["files"]), 17)
            self.assertEqual(sum(f["recoverable"] for f in truths["demo_mixed"]["files"]), 15)
            self.assertEqual(len(truths["demo_mixed"]["decoys"]), 5)
            self.assertEqual(truths["empty_fs"]["files"], [])
            self.assertEqual(truths["not_fat"]["expected_error"], "unrecognized_filesystem")
            for scenario, truth in truths.items():
                image = (root / scenario / "disk.img").read_bytes()
                self.assertEqual(hashlib.sha256(image).hexdigest(), truth["image"]["sha256"])
                for entry in truth["files"]:
                    original = (root / scenario / "originals" / entry["name"]).read_bytes()
                    self.assertEqual(hashlib.sha256(original).hexdigest(), entry["original_sha256"])
                    suffix = entry["type"]
                    if suffix in ("jpeg", "png", "pdf"):
                        validate_payload(suffix, original)
                    if entry["recoverable"]:
                        recovered_bytes = b"".join(
                            image[fragment["start"]:fragment["end"]]
                            for fragment in entry["fragments"]
                        )
                        self.assertEqual(recovered_bytes[:len(original)], original)
                for decoy in truth.get("decoys", []):
                    for entry in truth["files"]:
                        for fragment in entry["fragments"]:
                            self.assertFalse(
                                decoy["start"] < fragment["end"]
                                and fragment["start"] < decoy["end"]
                            )

    def test_deterministic_image_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first"
            second = Path(temp) / "second"
            generate(first, seed=1337, only=["C", "D"])
            generate(second, seed=1337, only=["C", "D"])
            for scenario in ("fragmented", "demo_mixed"):
                digest_a = hashlib.sha256((first / scenario / "disk.img").read_bytes()).hexdigest()
                digest_b = hashlib.sha256((second / scenario / "disk.img").read_bytes()).hexdigest()
                self.assertEqual(digest_a, digest_b)
                self.assertEqual(
                    json.loads((first / scenario / "ground_truth.json").read_text())["image"]["sha256"],
                    digest_a,
                )

    def test_subset_option(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            table = io.StringIO()
            with patch("sys.stdout", table):
                status = main(["--out", str(output), "--seed", "1337", "--only", "A,C"])
            self.assertEqual(status, 0)
            self.assertTrue((output / "clean_deleted" / "disk.img").exists())
            self.assertTrue((output / "fragmented" / "disk.img").exists())
            self.assertFalse((output / "demo_mixed").exists())
            self.assertIn("clean_deleted", table.getvalue())
            self.assertIn("fragmented", table.getvalue())


if __name__ == "__main__":
    unittest.main()
