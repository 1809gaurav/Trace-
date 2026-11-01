import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from schemas.models import CustodyLog, Results
from custody.verify import verify
from engine.pipeline import run_pipeline


FIXED_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


class PipelineTests(unittest.TestCase):
    def test_random_non_fat_image_finishes_with_warning_and_empty_results(self):
        image_bytes = bytes(range(256)) * 4096
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image_path = root / "disk.img"
            image_path.write_bytes(image_bytes)
            events = []

            outcome = run_pipeline(
                image_path, root / "out", clock=lambda: FIXED_TIME,
                progress=events.append,
            )

            self.assertEqual(outcome.results["files"], [])
            self.assertIn("unrecognized_filesystem", outcome.warnings)
            self.assertEqual(image_path.read_bytes(), image_bytes)
            self.assertEqual(
                hashlib.sha256(image_path.read_bytes()).hexdigest(),
                outcome.results["image"]["sha256"],
            )
            Results.model_validate(outcome.results)
            CustodyLog.model_validate(outcome.custody)
            self.assertTrue(verify(outcome.custody)["ok"])
            self.assertTrue(any(event["stage"] == "filesystem" for event in events))

    def test_results_are_deterministic_with_an_injected_clock(self):
        image_bytes = b"not a filesystem"
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image_path = root / "disk.img"
            image_path.write_bytes(image_bytes)
            first = run_pipeline(image_path, root / "first", clock=lambda: FIXED_TIME)
            second = run_pipeline(image_path, root / "second", clock=lambda: FIXED_TIME)

            first_results = (root / "first" / "results.json").read_bytes()
            second_results = (root / "second" / "results.json").read_bytes()
            self.assertEqual(first_results, second_results)
            self.assertEqual(json.dumps(first.results, sort_keys=True), json.dumps(second.results, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
