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
            ]
        }

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


if __name__ == "__main__":
    unittest.main()
