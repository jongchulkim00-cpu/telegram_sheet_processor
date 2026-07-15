import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import market_data


class KiwoomRestTests(unittest.TestCase):
    def setUp(self):
        self.original_env = {
            key: os.environ.get(key)
            for key in [
                "KIWOOM_ENABLED",
                "KIWOOM_REST_QUOTE_URL",
                "KIWOOM_REST_METHOD",
                "KIWOOM_REST_HEADERS_JSON",
                "KIWOOM_REST_TIMEOUT_SECONDS",
                "KIWOOM_REST_BASE_URL",
                "KIWOOM_REST_APP_KEY",
                "KIWOOM_REST_APP_SECRET",
            ]
        }
        market_data._KIWOOM_REST_TOKEN_CACHE.update({"token": None, "expires_at": 0.0, "expires_dt": None})

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_status_detects_rest_configuration(self):
        os.environ["KIWOOM_ENABLED"] = "true"
        os.environ["KIWOOM_REST_QUOTE_URL"] = "https://example.test/quote/{ticker}"

        status = market_data.kiwoom_rest_source_status()

        self.assertTrue(status["enabled"])
        self.assertTrue(status["configured"])
        self.assertTrue(status["quote_url_configured"])

    def test_status_detects_direct_rest_configuration(self):
        os.environ["KIWOOM_REST_ENABLED"] = "true"
        os.environ["KIWOOM_REST_APP_KEY"] = "app"
        os.environ["KIWOOM_REST_APP_SECRET"] = "secret"

        status = market_data.kiwoom_rest_source_status()

        self.assertTrue(status["enabled"])
        self.assertTrue(status["configured"])
        self.assertTrue(status["direct_api_configured"])
        self.assertFalse(status["quote_url_configured"])

    @patch("market_data.requests.request")
    def test_fetch_kiwoom_rest_quote_parses_price(self, mock_request):
        os.environ["KIWOOM_ENABLED"] = "true"
        os.environ["KIWOOM_REST_QUOTE_URL"] = "https://example.test/quote/{ticker}"
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"output": {"price": 123456}}
        mock_request.return_value = response

        result = market_data.fetch_kiwoom_rest_quote("123456")

        self.assertTrue(result["ok"])
        self.assertEqual(result["price"], 123456)
        self.assertEqual(result["source"], "kiwoom_rest")

    @patch("market_data.requests.post")
    def test_fetch_direct_kiwoom_rest_quote_fetches_token_and_price(self, mock_post):
        os.environ["KIWOOM_REST_ENABLED"] = "true"
        os.environ["KIWOOM_REST_BASE_URL"] = "https://mockapi.kiwoom.com"
        os.environ["KIWOOM_REST_APP_KEY"] = "app"
        os.environ["KIWOOM_REST_APP_SECRET"] = "secret"
        token_response = Mock()
        token_response.raise_for_status.return_value = None
        token_response.json.return_value = {"token": "abc", "expires_dt": "20991231235959"}
        quote_response = Mock()
        quote_response.raise_for_status.return_value = None
        quote_response.json.return_value = {"stk_cd": "005930", "stk_nm": "Samsung", "cur_prc": "+91700"}
        mock_post.side_effect = [token_response, quote_response]

        result = market_data.fetch_kiwoom_rest_quote("005930")

        self.assertTrue(result["ok"])
        self.assertEqual(result["price"], 91700)
        self.assertEqual(result["source"], "kiwoom_rest_ka10001")
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(mock_post.call_args_list[0].kwargs["headers"]["api-id"], "au10001")
        self.assertEqual(mock_post.call_args_list[1].kwargs["headers"]["api-id"], "ka10001")

    @patch("market_data.fetch_naver_public_quote")
    @patch("market_data.fetch_kiwoom_rest_quote")
    def test_best_current_quote_prefers_kiwoom_over_naver(self, mock_kiwoom, mock_naver):
        mock_kiwoom.return_value = {
            "ok": True,
            "source": "kiwoom_rest_ka10001",
            "ticker": "005930",
            "price": 91700,
            "url": "https://api.kiwoom.com/api/dostk/stkinfo",
        }

        result = market_data.fetch_best_current_quote("005930")

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "kiwoom_rest_ka10001")
        self.assertEqual(result["price"], 91700)
        self.assertEqual(result["priority"], "broker_kiwoom_rest")
        mock_naver.assert_not_called()

    @patch("market_data.fetch_ohlcv")
    @patch("market_data.cross_validate_ohlcv")
    @patch("market_data.fetch_best_current_quote")
    def test_verify_price_claims_uses_best_current_quote(self, mock_quote, mock_validate, mock_fetch):
        import pandas as pd

        frame = pd.DataFrame(
            [{"date": "2026-07-15", "open": 90000, "high": 92000, "low": 89000, "close": 90000, "volume": 1000}]
        )
        mock_fetch.return_value = market_data.FetchResult(
            ticker="005930",
            name="삼성전자",
            provider="pykrx",
            rows=len(frame),
            frame=frame,
            cache_path=None,
            warnings=[],
        )
        mock_validate.return_value = {"tradable": True, "checks": []}
        mock_quote.return_value = {
            "ok": True,
            "provider": "kiwoom_rest_ka10001",
            "price": 91700,
            "url": "https://api.kiwoom.com/api/dostk/stkinfo",
        }

        result = market_data.verify_price_claims(
            [{"ticker": "005930", "name": "삼성전자", "claimed_price": 91700}],
            force=True,
        )

        row = result["results"][0]
        self.assertEqual(row["verified_price"], 91700)
        self.assertEqual(row["verified_price_source"], "kiwoom_rest_ka10001")
        self.assertEqual(row["claim_status"], "matched")


if __name__ == "__main__":
    unittest.main()
