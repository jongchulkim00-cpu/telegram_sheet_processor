import unittest
import sys
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import api_server


class PreviewReviewApiTests(unittest.TestCase):
    def test_review_ui_contains_expected_controls(self):
        html = api_server.review_ui()

        self.assertIn("Preview / Review Lab", html)
        self.assertIn("@tabler/core", html)
        self.assertIn('data-ui-version="tabler"', html)
        self.assertIn("/preview-review", html)
        self.assertIn("/stocks/search", html)
        self.assertIn("autoFillStockFrom", html)
        self.assertIn("resolveStockFromName", html)
        self.assertIn("preview-review-batch", html)
        self.assertIn("batchItems", html)
        self.assertIn("review-watchlist", html)
        self.assertIn("loadWatchlist", html)
        self.assertIn("saveWatchlist", html)
        self.assertIn("review-sectors", html)
        self.assertIn("loadSectorThemes", html)
        self.assertIn("stocks/universe/status", html)
        self.assertIn("universeStatus", html)
        self.assertIn("review-relative-strength", html)
        self.assertIn("loadRelativeStrength", html)
        self.assertIn("automation/candidates", html)
        self.assertIn("loadAutomationCandidates", html)
        self.assertIn("종목명을 입력하고 Enter", html)
        self.assertNotIn('id="stockSearch"', html)
        self.assertNotIn("종목 검색</label>", html)
        self.assertNotIn("진행 체크리스트", html)
        self.assertNotIn("loadRoadmap", html)
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

    def test_stock_search_name_can_resolve_ticker_for_review_ui(self):
        found = api_server.search_stock_universe("제주반도체", limit=5)

        self.assertGreaterEqual(found["count"], 1)
        self.assertEqual(found["results"][0]["ticker"], "080220")

    def test_stock_universe_status_reports_cached_markets(self):
        status = api_server.stocks_universe_status()

        self.assertTrue(status["ok"])
        self.assertGreater(status["universe_count"], 0)
        self.assertIn("search_policy", status)
        self.assertIn("is_full_universe", status)
        self.assertIn("load_error", status)

    def test_roadmap_status_has_visible_buckets(self):
        roadmap = api_server.roadmap_status()

        self.assertGreater(len(roadmap["completed"]), 1)
        self.assertGreater(len(roadmap["next"]), 1)
        self.assertIn("상대강도", roadmap["in_progress"][0])

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

    def test_classify_stock_theme_marks_semiconductor_items(self):
        result = api_server.classify_stock_theme("080220", "제주반도체", "KOSDAQ")

        self.assertEqual(result["primary_theme"], "반도체/AI")
        self.assertEqual(result["sector"], "반도체")
        self.assertEqual(result["classification_confidence"], "high")

    def test_review_sector_summary_groups_watchlist(self):
        original_path = api_server.REVIEW_WATCHLIST_PATH
        temp_path = PROJECT_ROOT / "data" / "test_review_sector_watchlist.json"
        api_server.REVIEW_WATCHLIST_PATH = temp_path
        try:
            api_server.save_review_watchlist([
                {"ticker": "080220", "name": "제주반도체"},
                {"ticker": "247540", "name": "에코프로비엠"},
            ])
            summary = api_server.review_sector_summary()

            self.assertEqual(summary["count"], 2)
            self.assertTrue(any(group["theme"] == "반도체/AI" for group in summary["groups"]))
            self.assertTrue(any(group["theme"] == "2차전지/소재" for group in summary["groups"]))
        finally:
            api_server.REVIEW_WATCHLIST_PATH = original_path
            if temp_path.exists():
                temp_path.unlink()

    def test_frame_return_pct_calculates_lookback_return(self):
        frame = pd.DataFrame({
            "date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "close": [100, 110, 121],
        })

        self.assertEqual(api_server.frame_return_pct(frame, 2), 21.0)
        self.assertEqual(api_server.frame_return_pct(frame, 1), 10.0)

    def test_relative_strength_label_thresholds(self):
        self.assertEqual(api_server.relative_strength_label(8), "strong_outperform")
        self.assertEqual(api_server.relative_strength_label(3), "outperform")
        self.assertEqual(api_server.relative_strength_label(0), "inline")
        self.assertEqual(api_server.relative_strength_label(-3), "underperform")
        self.assertEqual(api_server.relative_strength_label(-8), "strong_underperform")
        self.assertEqual(api_server.relative_strength_label(None), "unavailable")

    def test_automation_status_is_conservative_by_default(self):
        status = api_server.automation_status()

        self.assertTrue(status["ok"])
        self.assertEqual(status["automation"]["mode"], "review_only")
        self.assertFalse(status["automation"]["allow_live_orders"])
        self.assertIn("Actual Kiwoom order submission", status["order_execution_policy"])

    def test_storage_status_reports_volume_policy(self):
        status = api_server.storage_status()

        self.assertTrue(status["ok"])
        self.assertIn("storage", status)
        self.assertIn("data", status["storage"])
        self.assertIn("outputs", status["storage"])
        self.assertIn("STOCK_DATA_DIR", status["docker_volume_policy"]["data_mount"])
        self.assertIn("intraday_30m", status["retention_policy"])


if __name__ == "__main__":
    unittest.main()
