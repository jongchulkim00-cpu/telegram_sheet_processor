import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import market_data


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


if __name__ == "__main__":
    unittest.main()
