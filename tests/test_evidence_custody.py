import ast
import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from custody.verify import tamper, verify
from engine.evidence import EvidenceImage
from custody.chain import CustodyChain


class EngineIsolationTests(unittest.TestCase):
    def test_engine_does_not_import_testgen_or_scorer_or_name_ground_truth(self):
        engine_dir = Path(__file__).resolve().parents[1] / "engine"
        for source_path in engine_dir.glob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = [alias.name.split(".", 1)[0] for alias in node.names]
                    self.assertFalse({"testgen", "scorer"}.intersection(imported))
                elif isinstance(node, ast.ImportFrom):
                    imported = (node.module or "").split(".", 1)[0]
                    self.assertNotIn(imported, {"testgen", "scorer"})
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertFalse(node.value.lower().startswith("ground_truth"))


class EvidenceTests(unittest.TestCase):
    def test_hash_size_and_write_guard(self):
        image_bytes = b"read-only evidence"
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "disk.img"
            path.write_bytes(image_bytes)

            with EvidenceImage(path) as evidence:
                self.assertEqual(evidence.size_bytes, len(image_bytes))
                self.assertEqual(evidence.sha256, hashlib.sha256(image_bytes).hexdigest())
                self.assertEqual(evidence.read(), image_bytes)
                with self.assertRaises((OSError, PermissionError)):
                    evidence.write(b"changed")

            self.assertEqual(path.read_bytes(), image_bytes)

    def test_reverify_detects_changed_image(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "disk.img"
            path.write_bytes(b"before")

            with EvidenceImage(path) as evidence:
                path.write_bytes(b"after!")
                self.assertFalse(evidence.reverify())


class CustodyTests(unittest.TestCase):
    def make_chain(self):
        times = iter((
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
            datetime(2026, 1, 3, tzinfo=timezone.utc),
        ))
        chain = CustodyChain(clock=lambda: next(times))
        for step in ("IMAGE_OPENED", "CARVING_DONE", "RESULTS_WRITTEN"):
            chain.append(step, {"message": step})
        return chain

    def test_chain_verifies_and_details_tampering_is_detected(self):
        chain = self.make_chain()
        self.assertTrue(verify(chain.entries)["ok"])

        modified = tamper(list(chain.entries), 1)
        self.assertTrue(verify(list(chain.entries))["ok"])
        self.assertFalse(verify(modified)["ok"])
        self.assertEqual(verify(modified)["first_failing_index"], 1)

    def test_reordering_and_deleting_an_interior_entry_are_detected(self):
        entries = list(self.make_chain().entries)

        reordered = [entries[1], entries[0], entries[2]]
        self.assertEqual(verify(reordered)["first_failing_index"], 0)

        del entries[1]
        self.assertEqual(verify(entries)["first_failing_index"], 1)


if __name__ == "__main__":
    unittest.main()
