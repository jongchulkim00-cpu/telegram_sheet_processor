import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


class KiwoomBridgeTests(unittest.TestCase):
    def setUp(self):
        self.original_env = {
            key: os.environ.get(key)
            for key in [
                "KIWOOM_BRIDGE_MODE",
                "KIWOOM_REST_BASE_URL",
                "KIWOOM_REST_APP_KEY",
                "KIWOOM_REST_APP_SECRET",
            ]
        }

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def reload_bridge(self):
        import kiwoom_rest_bridge_example

        return importlib.reload(kiwoom_rest_bridge_example)

    def test_mock_quote(self):
        os.environ["KIWOOM_BRIDGE_MODE"] = "mock"
        bridge = self.reload_bridge()

        result = bridge.fetch_quote("399720")

        self.assertTrue(result["ok"])
        self.assertEqual(result["ticker"], "399720")
        self.assertEqual(result["source"], "kiwoom_bridge_mock")
        self.assertGreater(result["price"], 0)

    @patch("kiwoom_rest_bridge_example.requests.post")
    def test_rest_quote_fetches_token_and_price(self, mock_post):
        os.environ["KIWOOM_BRIDGE_MODE"] = "rest"
        os.environ["KIWOOM_REST_BASE_URL"] = "https://mockapi.kiwoom.com"
        os.environ["KIWOOM_REST_APP_KEY"] = "app"
        os.environ["KIWOOM_REST_APP_SECRET"] = "secret"
        bridge = self.reload_bridge()

        token_response = Mock()
        token_response.raise_for_status.return_value = None
        token_response.json.return_value = {"token": "abc", "expires_dt": "20991231235959"}
        quote_response = Mock()
        quote_response.raise_for_status.return_value = None
        quote_response.json.return_value = {"stk_cd": "005930", "stk_nm": "Samsung", "cur_prc": "+91700"}
        mock_post.side_effect = [token_response, quote_response]

        result = bridge.fetch_quote("005930")

        self.assertTrue(result["ok"])
        self.assertEqual(result["price"], 91700)
        self.assertEqual(result["source"], "kiwoom_rest_ka10001")
        self.assertEqual(mock_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
