import unittest

from engine.classifier import classify_file


class ClassificationTests(unittest.TestCase):
    def test_intact_confidence_bands_distinguish_live_and_deleted(self):
        live = classify_file(
            "fat32", state="live", dir_entry_present=True,
            validation_ok=True, full_chain=True,
        )
        deleted = classify_file(
            "fat32", state="deleted_contiguous", dir_entry_present=True,
            validation_ok=True, full_chain=False,
        )
        self.assertEqual(live.classification, "intact")
        self.assertGreaterEqual(live.confidence, 0.95)
        self.assertEqual(deleted.classification, "intact")
        self.assertGreaterEqual(deleted.confidence, 0.88)
        self.assertLess(deleted.confidence, 0.95)

    def test_carved_and_reconstructed_bands_and_reasons(self):
        carved = classify_file(
            "carver", state="carved", dir_entry_present=False,
            validation_ok=True, full_chain=False,
        )
        reconstructed = classify_file(
            "fragments", state="deleted_fragmented", dir_entry_present=True,
            validation_ok=True, full_chain=False, search_cost=500,
        )
        self.assertEqual(carved.classification, "carved")
        self.assertGreaterEqual(carved.confidence, 0.70)
        self.assertLessEqual(carved.confidence, 0.85)
        self.assertEqual(reconstructed.classification, "reconstructed")
        self.assertGreaterEqual(reconstructed.confidence, 0.50)
        self.assertLessEqual(reconstructed.confidence, 0.70)
        self.assertTrue(carved.reason.endswith("."))
        self.assertTrue(reconstructed.reason.endswith("."))

    def test_partial_confidence_scales_with_decoded_fraction(self):
        partial = classify_file(
            "carver", state="partial", dir_entry_present=False,
            validation_ok=False, full_chain=False, decoded_fraction=0.5,
        )
        self.assertEqual(partial.classification, "partial")
        self.assertAlmostEqual(partial.confidence, 0.4)

    def test_risk_penalties_reduce_confidence_without_leaving_band(self):
        ordinary = classify_file(
            "carver", state="carved", dir_entry_present=False,
            validation_ok=True, full_chain=False,
        )
        risky = classify_file(
            "carver", state="carved", dir_entry_present=False,
            validation_ok=True, full_chain=False,
            duplicate=True, unusually_small=True, ambiguous_footer=True,
        )
        self.assertLess(risky.confidence, ordinary.confidence)
        self.assertGreaterEqual(risky.confidence, 0.70)


if __name__ == "__main__":
    unittest.main()
