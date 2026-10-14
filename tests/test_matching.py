import unittest

from app.matching import MatchingEngine, lexical_similarity


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.engine = MatchingEngine()

    def test_same_description_scores_above_unrelated_description(self):
        same = lexical_similarity(
            "Navy backpack with two front pockets",
            "Dark blue backpack with two front pockets"
        )
        different = lexical_similarity(
            "Navy backpack with two front pockets",
            "Steel water bottle with a black cap"
        )
        self.assertGreater(same, different)

    def test_category_location_and_date_affect_match(self):
        lost = {
            "title": "Blue backpack", "description": "dark blue bag with two pockets",
            "category": "bags_wallets", "location_block": "Block A",
            "location_floor": "1", "location_room": "A-101",
            "location_area": "Library", "occurred_at": "2026-10-13T12:00:00"
        }
        found = dict(lost)
        result = self.engine.compare(lost, found)
        self.assertGreaterEqual(result["score"], 0.9)
        self.assertIn("category", result["signals"])

    def test_missing_location_and_date_are_supported(self):
        lost = {"title": "Black headphones", "description": "black headphones", "category": "accessories"}
        found = {"title": "Black headphones", "description": "black headphones", "category": "accessories"}
        result = self.engine.compare(lost, found)
        self.assertIsNone(result["signals"]["location"])
        self.assertIsNone(result["signals"]["time"])
        self.assertIn("text", result["signals"])

    def test_rank_returns_best_candidates_first(self):
        lost = {"title": "Blue backpack", "description": "blue backpack with pockets", "category": "bags_wallets"}
        candidates = [
            {"title": "Steel bottle", "description": "silver bottle", "category": "accessories"},
            {"title": "Blue backpack", "description": "blue bag with pockets", "category": "bags_wallets"},
        ]
        ranked = self.engine.rank(lost, candidates)
        self.assertEqual(ranked[0]["report"]["title"], "Blue backpack")


if __name__ == "__main__":
    unittest.main()
