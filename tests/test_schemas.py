import json
import unittest
from pathlib import Path

from schemas.models import (
    CustodyLog, GroundTruth, Results, Score, compute_entry_hash,
)


ROOT = Path(__file__).parents[1]


class SchemaTests(unittest.TestCase):
    def test_examples_validate_and_schemas_are_exported(self):
        examples = ROOT / "schemas" / "examples"
        Results.model_validate_json((examples / "results.example.json").read_text())
        CustodyLog.model_validate_json((examples / "custody.example.json").read_text())
        Score.model_validate_json((examples / "score.example.json").read_text())
        for name in (
            "results.schema.json", "custody.schema.json",
            "ground_truth.schema.json", "score.schema.json",
        ):
            schema = json.loads((ROOT / "schemas" / name).read_text())
            self.assertIn("$schema", schema)
        custody_schema = json.loads((ROOT / "schemas" / "custody.schema.json").read_text())
        self.assertEqual(custody_schema["type"], "array")

    def test_custody_hash_test_vector(self):
        self.assertEqual(
            compute_entry_hash("0" * 64, "image_acquired", {"sha256": "abc", "size_bytes": 3}),
            "6eb7cc11c264d35b5059578bd4a29776e55225528e05316bfc21ac06814c2ee5",
        )


if __name__ == "__main__":
    unittest.main()
