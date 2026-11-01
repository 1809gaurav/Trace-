import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from scorer.score import main, score_case


def fixture():
    payload = bytes((index % 251 for index in range(10_240)))
    digest = hashlib.sha256(payload).hexdigest()
    truth = {
        "schema_version": "1.0", "scenario": "test", "seed": 1,
        "pillow_version": "test",
        "image": {"path": "disk.img", "sha256": "0" * 64, "size_bytes": 1,
                  "bytes_per_sector": 512, "sectors_per_cluster": 2,
                  "cluster_size": 1024, "data_start_offset": 0},
        "files": [{
            "id": "gt-1", "name": "FILE.BIN", "type": "unknown",
            "original_sha256": digest, "size_bytes": len(payload),
            "state": "live", "recoverable": True, "fragments": [{"start": 10, "end": 10 + len(payload)}],
            "dir_entry_present": True, "fs_timestamps": {},
            "expected_via": "fat32", "expected_classification": "intact",
            "acceptable_classifications": ["intact"], "metadata": {},
        }],
        "decoys": [{"id": "decoy-1", "kind": "noise", "start": 20_000, "end": 20_100}],
    }
    return payload, truth


def result_item(payload, output_path="f.bin", start=10, confidence=0.9):
    return {
        "id": "f-1", "name": "FILE.BIN", "type": "unknown", "source": "fat32",
        "stage": "test", "classification": "intact", "confidence": confidence,
        "reason": "", "offsets": [{"start": start, "end": start + len(payload)}],
        "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
        "output_path": output_path, "timestamps": {}, "metadata": {}, "warnings": [],
        "_bytes": payload,
    }


class ScorerTests(unittest.TestCase):
    def run_score(self, items, *, modify_image=False):
        payload, truth = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "out").mkdir()
            for item in items:
                path = root / "out" / item["output_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                content = item.pop("_bytes", payload)
                path.write_bytes(content)
                item["sha256"] = hashlib.sha256(content).hexdigest()
            image_bytes = bytearray(20_200)
            image_bytes[10:10 + len(payload)] = payload
            truth["image"]["sha256"] = hashlib.sha256(image_bytes).hexdigest()
            image = root / "disk.img"
            if modify_image:
                image_bytes[0] = 1
            image.write_bytes(image_bytes)
            return score_case(truth, {"schema_version": "1.0", "case_id": "case-1",
                                      "tool_version": "0.1.0",
                                      "generated_at": "2026-01-01T00:00:00Z",
                                      "image": {"path": "disk.img", "sha256": "0" * 64,
                                                "size_bytes": 1},
                                      "files": items, "summary": {"total": len(items),
                                      "by_classification": {}}}, root / "out", image)

    def test_perfect_results(self):
        full = bytes((index % 251 for index in range(10_240)))
        perfect = self.run_score([result_item(full)])
        self.assertEqual((perfect.precision, perfect.recall, perfect.completeness), (1.0, 1.0, 1.0))
        self.assertEqual(perfect.false_positives, 0)

    def test_empty_results(self):
        empty = self.run_score([])
        self.assertEqual(empty.recovered, 0)
        self.assertEqual(empty.completeness, 0)

    def test_decoy_is_false_positive(self):
        decoy = result_item(b"noise", output_path="decoy.bin", start=20_000)
        self.assertEqual(self.run_score([decoy]).false_positives, 1)

    def test_duplicate_is_false_positive(self):
        full = bytes((index % 251 for index in range(10_240)))
        duplicate = result_item(full, output_path="dup.bin")
        duplicate["id"] = "f-2"
        score = self.run_score([result_item(full), duplicate])
        self.assertEqual(score.false_positives, 1)

    def test_truncated_file_has_partial_completeness(self):
        full = bytes((index % 251 for index in range(10_240)))
        partial_bytes = full[: int(len(full) * 0.6)]
        partial_item = result_item(partial_bytes)
        partial_score = self.run_score([partial_item])
        self.assertAlmostEqual(partial_score.per_file[0].completeness, 0.6, delta=0.02)
        self.assertEqual(partial_score.per_file[0].status, "partial")

    def test_high_confidence_wrong_item_is_overconfident_error(self):
        wrong = result_item(b"wrong content", confidence=0.99)
        wrong["name"] = "WRONG.BIN"
        wrong_score = self.run_score([wrong])
        self.assertGreaterEqual(wrong_score.overconfident_errors, 1)

    def test_modified_image_fails_integrity_check(self):
        self.assertFalse(self.run_score([], modify_image=True).image_integrity_ok)

    def test_malformed_results_raise_schema_error(self):
        payload, truth = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "disk.img"
            image.write_bytes(payload)
            with self.assertRaises(ValidationError) as context:
                score_case(truth, {"files": [{"id": "missing-fields"}]}, root, image)
            self.assertIn("validation", str(context.exception).lower())
            truth_path, result_path = root / "truth.json", root / "results.json"
            truth_path.write_text(json.dumps(truth), encoding="utf-8")
            result_path.write_text('{"files":[{"id":"missing-fields"}]}', encoding="utf-8")
            errors = io.StringIO()
            with patch("sys.stderr", errors):
                status = main([
                    "--truth", str(truth_path), "--results", str(result_path),
                    "--recovered-dir", str(root), "--image", str(image),
                ])
            self.assertEqual(status, 2)
            self.assertIn("Schema validation failed", errors.getvalue())

    def test_cli_writes_score_and_strict_rejects_modified_image(self):
        payload, truth = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recovered = root / "out"
            recovered.mkdir()
            image_bytes = bytearray(20_200)
            image_bytes[10:10 + len(payload)] = payload
            truth["image"]["sha256"] = hashlib.sha256(image_bytes).hexdigest()
            truth["image"]["size_bytes"] = len(image_bytes)
            truth_path = root / "truth.json"
            truth_path.write_text(json.dumps(truth), encoding="utf-8")
            image = root / "disk.img"
            image.write_bytes(image_bytes)
            item = result_item(payload)
            item.pop("_bytes")
            (recovered / item["output_path"]).write_bytes(payload)
            results_path = root / "results.json"
            results_path.write_text(json.dumps({
                "schema_version": "1.0", "case_id": "case-1",
                "tool_version": "0.1.0", "generated_at": "2026-01-01T00:00:00Z",
                "image": {"path": "disk.img", "sha256": "0" * 64, "size_bytes": 1},
                "files": [item],
                "summary": {"total": 1, "by_classification": {"intact": 1}},
            }), encoding="utf-8")
            output_path = root / "score.json"
            output = io.StringIO()
            with patch("sys.stdout", output):
                status = main([
                    "--truth", str(truth_path), "--results", str(results_path),
                    "--recovered-dir", str(recovered), "--image", str(image),
                    "--json", str(output_path), "--strict",
                ])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output_path.read_text())["completeness"], 1.0)
            self.assertIn("100.0%", output.getvalue())
            image_bytes[0] = 1
            image.write_bytes(image_bytes)
            self.assertEqual(main([
                "--truth", str(truth_path), "--results", str(results_path),
                "--recovered-dir", str(recovered), "--image", str(image),
                "--json", str(root / "score-modified.json"), "--strict",
            ]), 1)


if __name__ == "__main__":
    unittest.main()
