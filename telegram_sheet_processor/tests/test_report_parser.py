import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import market_data
import pandas as pd


class ReportParserTests(unittest.TestCase):
    def test_target_label_does_not_steal_stop_loss_price(self):
        text = (
            "분석 기준일: 2026-07-15\n"
            "종목명: 가온칩스\n"
            "종목코드: 399720\n"
            "공개 현재가: 55,100원\n"
            "목표가: 별도 제시 안 함 (60일선 돌파 확인 후 재산정)\n"
            "손절가: 50,000원"
        )

        claims = market_data.extract_report_claims(text)

        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["claimed_price"], 55100)
        self.assertIsNone(claims[0]["target_price"])
        self.assertEqual(claims[0]["stop_loss"], 50000)

    def test_target_price_null_json_does_not_steal_stop_loss(self):
        text = (
            "분석 기준일: 2026-07-15\n"
            "가온칩스(399720) 공개 현재가: 55,100원\n"
            "목표가: 별도 제시 안 함\n"
            "손절가: 50,000원\n"
            '<json>{"symbol":"399720","score":65,"decision":"Buy",'
            '"target_price":null,"stop_loss":50000}</json>'
        )

        claims = market_data.extract_report_claims(text)

        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["claimed_price"], 55100)
        self.assertIsNone(claims[0]["target_price"])
        self.assertEqual(claims[0]["stop_loss"], 50000)

    def test_ticker_briefing_without_price_claim_is_informational(self):
        text = (
            "금일 시장에서 주목받고 있는 주요 이슈 종목 5개에 대한 분석 결과입니다.\n"
            "| 종목명 | 종목코드 | 주요 이슈 및 촉매제 | 예상 영향력 | 시간 지평 |\n"
            "| 삼성전자 | 005930 | 파운드리 수주 기대감 | +3 | 중기 |\n"
            "| SK하이닉스 | 000660 | HBM3E 공급 확대 | +4 | 중기 |\n"
            "참고: 개별 종목의 실시간 매매 판단은 기술적 데이터 검증이 필수입니다."
        )

        result = market_data.validate_report_text(text)

        self.assertTrue(result["publishable"])
        self.assertEqual(result["report_guard_status"], "informational_ticker_briefing")
        self.assertEqual(result["price_verification"]["count"], 0)
        self.assertEqual(result["blocking_reasons"], [])

    def test_strategy_price_on_ticker_line_is_not_claimed_current_price(self):
        text = (
            "분석 기준일: 2026-07-15\n"
            "한미반도체(042700) 종합 신호: 강2\n"
            "목표가: 100,000원, 손절가: 80,000원\n"
        )

        claims = market_data.extract_report_claims(text)

        self.assertEqual(len(claims), 1)
        self.assertIsNone(claims[0]["claimed_price"])
        self.assertEqual(claims[0]["target_price"], 100000)
        self.assertEqual(claims[0]["stop_loss"], 80000)

    def test_realtime_data_wording_is_not_strict_realtime_price_claim(self):
        text = "특정 종목에 대해 상세 지표가 궁금하시다면 즉시 실시간 데이터를 반영하여 보고서를 작성하겠습니다."

        self.assertEqual(market_data.report_claims_strict_realtime_wording(text), [])
        self.assertTrue(market_data.report_claims_strict_realtime_wording("실시간 현재가: 10,000원"))

    def test_repeated_ticker_merges_later_strategy_segment(self):
        text = (
            "분석 기준일: 2026-07-15\n"
            "후보: 가온칩스(399720), 한미반도체(042700), 제주반도체(080220)\n"
            "한미반도체(042700)\n"
            "목표가: 100,000원\n"
            "손절가: 80,000원\n"
        )

        claims = market_data.extract_report_claims(text)
        by_ticker = {row["ticker"]: row for row in claims}

        self.assertIsNone(by_ticker["042700"]["claimed_price"])
        self.assertEqual(by_ticker["042700"]["target_price"], 100000)
        self.assertEqual(by_ticker["042700"]["stop_loss"], 80000)

    def test_reduce_json_marks_strategy_as_bearish(self):
        text = (
            "분석 기준일: 2026-07-15\n"
            "제주반도체(080220) 종합 신호: 약2(비중 축소/Reduce)\n"
            "목표가: 제시 불가\n"
            "손절가: 85,000원\n"
            '<json>{"symbol":"080220","score":33.08,"decision":"Reduce",'
            '"target_price":null,"stop_loss":85000}</json>'
        )

        claims = market_data.extract_report_claims(text)

        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["decision"], "Reduce")
        self.assertEqual(claims[0]["strategy_side"], "bearish")
        self.assertIsNone(claims[0]["target_price"])
        self.assertEqual(claims[0]["stop_loss"], 85000)

    def test_reduce_strategy_does_not_require_upside_target(self):
        frame = pd.DataFrame(
            [
                {"date": pd.Timestamp("2026-07-15"), "open": 87000, "high": 88000, "low": 86000, "close": 87100, "volume": 1000},
            ]
        )
        fetch = market_data.FetchResult(
            ticker="080220",
            name="제주반도체",
            provider="test",
            frame=frame,
            cache_path=PROJECT_ROOT / "data" / "cache" / "test.csv",
            rows=1,
            warnings=[],
        )
        claim = {
            "ticker": "080220",
            "name": "제주반도체",
            "claimed_price": 87100,
            "target_price": 85000,
            "stop_loss": 85000,
            "strategy_side": "bearish",
        }

        with patch.object(market_data, "fetch_ohlcv", return_value=fetch), \
             patch.object(market_data, "cross_validate_ohlcv", return_value={"tradable": True, "status": "matched"}), \
             patch.object(market_data, "fetch_best_current_quote", return_value={"ok": True, "price": 87100, "provider": "test_quote"}):
            result = market_data.verify_price_claims([claim], force=True)

        self.assertEqual(result["error_count"], 0)
        self.assertEqual(result["results"][0]["claim_status"], "matched")
        self.assertTrue(result["results"][0]["tradable"])


if __name__ == "__main__":
    unittest.main()
