import unittest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import api_server


class PreviewReviewApiTests(unittest.TestCase):
    def test_review_ui_contains_expected_controls(self):
        html = api_server.review_ui()

        self.assertIn("Preview / Review Lab", html)
        self.assertIn("/preview-review", html)
        self.assertIn("/stocks/search", html)
        self.assertIn("stockSearch", html)
        self.assertIn("autoFillStockFrom", html)
        self.assertIn("preview-review-batch", html)
        self.assertIn("batchItems", html)
        self.assertIn("review-roadmap", html)
        self.assertIn("review-watchlist", html)
        self.assertIn("loadWatchlist", html)
        self.assertIn("saveWatchlist", html)
        self.assertIn("include_quote=true", html)
        self.assertIn("ticker", html)
        self.assertIn("BUY", html)
        self.assertIn("PREPARE", html)

    def test_compact_preview_review_adds_chart_url_and_policy(self):
        result = {
            "ticker": "080220",
            "name": "제주반도체",
            "probability_10d": {},
        }

        compact = api_server.compact_preview_review(result)

        self.assertEqual(compact["chart_url"], "/preview-review/chart/080220")
        self.assertEqual(compact["policy"]["watchlist_limit"], 50)
        self.assertEqual(compact["policy"]["initial_order_budget_krw"], 100000)

    def test_stock_search_finds_default_korean_names(self):
        found = api_server.search_stock_universe("한미", limit=5)

        self.assertGreaterEqual(found["count"], 1)
        self.assertTrue(any(item["ticker"] == "042700" for item in found["results"]))

    def test_stock_search_finds_by_ticker_prefix(self):
        found = api_server.search_stock_universe("042", limit=5)

        self.assertGreaterEqual(found["count"], 1)
        self.assertEqual(found["results"][0]["ticker"], "042700")

    def test_roadmap_status_has_visible_buckets(self):
        roadmap = api_server.roadmap_status()

        self.assertGreater(len(roadmap["completed"]), 1)
        self.assertGreater(len(roadmap["next"]), 1)
        self.assertIn("섹터", roadmap["in_progress"][0])

    def test_review_watchlist_save_load_normalizes_duplicates(self):
        original_path = api_server.REVIEW_WATCHLIST_PATH
        temp_path = PROJECT_ROOT / "data" / "test_review_watchlist.json"
        api_server.REVIEW_WATCHLIST_PATH = temp_path
        try:
            saved = api_server.save_review_watchlist([
                {"ticker": "042700", "name": "한미반도체"},
                {"ticker": "042700", "name": "중복"},
                {"symbol": "080220", "name": "제주반도체"},
                {"ticker": ""},
            ])
            loaded = api_server.load_review_watchlist()

            self.assertEqual(saved, loaded)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0]["ticker"], "042700")
            self.assertEqual(loaded[1]["ticker"], "080220")
        finally:
            api_server.REVIEW_WATCHLIST_PATH = original_path
            if temp_path.exists():
                temp_path.unlink()


if __name__ == "__main__":
    unittest.main()
