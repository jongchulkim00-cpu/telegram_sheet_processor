import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import trade_automation_policy


class TradeAutomationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.original_env = {
            key: os.environ.get(key)
            for key in [
                "AUTO_TRADE_MODE",
                "AUTO_TRADE_REQUIRE_INTRADAY_SIGNAL",
                "AUTO_TRADE_REQUIRE_BROKER_REALTIME",
                "AUTO_TRADE_ALLOW_LIVE_ORDERS",
                "AUTO_TRADE_REQUIRE_APPROVAL",
            ]
        }

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def sample_review(self, signal="BUY"):
        return {
            "ticker": "080220",
            "name": "제주반도체",
            "signals": [
                {
                    "date": "2026-07-15",
                    "signal": signal,
                    "reason": "stochastic_cross_up_with_trend_support",
                    "close": 89100,
                }
            ],
            "probability_10d": {
                "BUY": {"positive_end_probability_pct": 62.5},
                "PREPARE": {"positive_end_probability_pct": 55.0},
            },
        }

    def test_review_only_blocks_order_submission(self):
        os.environ["AUTO_TRADE_MODE"] = "review_only"

        result = trade_automation_policy.evaluate_candidate(
            self.sample_review(),
            quote={"quote_price": 89100, "quote_source": "kiwoom_rest_ka10001", "quote_label": "broker_realtime"},
            relative_strength={"relative_strength": {"60d": 4.2}},
            settings=trade_automation_policy.AutomationSettings.from_env(),
        )

        self.assertEqual(result["action"], "REVIEW_ONLY")
        self.assertFalse(result["can_submit_order"])
        self.assertIn("30-minute intraday confirmation is not connected yet.", result["blockers"])

    def test_approval_candidate_when_all_safety_gates_are_met(self):
        settings = trade_automation_policy.AutomationSettings(
            mode="approval_required",
            initial_order_budget_krw=100000,
            require_human_approval=True,
            allow_live_orders=False,
            require_broker_realtime=True,
            require_intraday_signal=False,
        )

        result = trade_automation_policy.evaluate_candidate(
            self.sample_review(),
            quote={"quote_price": 50000, "quote_source": "kiwoom_rest_ka10001", "quote_label": "broker_realtime"},
            relative_strength={"relative_strength": {"60d": 7.5}},
            settings=settings,
        )

        self.assertEqual(result["action"], "APPROVAL_REQUIRED")
        self.assertTrue(result["requires_human_approval"])
        self.assertEqual(result["quantity"], 2)
        self.assertEqual(result["estimated_amount_krw"], 100000)
        self.assertEqual(result["blockers"], [])

    def test_reduce_signal_never_creates_buy_order(self):
        settings = trade_automation_policy.AutomationSettings(
            mode="small_auto",
            initial_order_budget_krw=100000,
            require_human_approval=False,
            allow_live_orders=True,
            require_broker_realtime=False,
            require_intraday_signal=False,
        )

        result = trade_automation_policy.evaluate_candidate(
            self.sample_review(signal="REDUCE"),
            quote={"quote_price": 50000},
            settings=settings,
        )

        self.assertEqual(result["side"], "SELL_REVIEW")
        self.assertFalse(result["can_submit_order"])
        self.assertTrue(any("do not open a new buy position" in item for item in result["blockers"]))


if __name__ == "__main__":
    unittest.main()
