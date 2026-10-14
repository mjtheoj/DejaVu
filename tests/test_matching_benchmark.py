"""Validate labels in the synthetic matching evaluation data."""
import json
import unittest
from pathlib import Path

DATA = Path(__file__).parent / "data" / "matching_benchmark.json"


class MatchingBenchmarkDataTests(unittest.TestCase):
    def test_has_fifteen_queries_and_valid_relevant_ids(self):
        payload = json.loads(DATA.read_text(encoding="utf-8"))
        cases = payload["cases"]
        self.assertEqual(len(cases), 15)
        self.assertIn("synthetic", payload["description"].lower())
        for case in cases:
            self.assertGreaterEqual(len(case["candidates"]), 6)
            candidate_ids = {item["id"] for item in case["candidates"]}
            self.assertTrue(set(case["relevant_ids"]).issubset(candidate_ids), case["case_id"])

    def test_contains_reworded_and_wrong_category_scenarios(self):
        labels = " ".join(case["label"].lower() for case in json.loads(DATA.read_text(encoding="utf-8"))["cases"])
        self.assertIn("reworded", labels)
        self.assertIn("wrong-category", labels)


if __name__ == "__main__":
    unittest.main()
