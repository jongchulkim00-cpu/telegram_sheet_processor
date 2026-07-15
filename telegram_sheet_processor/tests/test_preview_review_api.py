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


if __name__ == "__main__":
    unittest.main()
