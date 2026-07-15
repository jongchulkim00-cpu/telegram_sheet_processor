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


if __name__ == "__main__":
    unittest.main()
