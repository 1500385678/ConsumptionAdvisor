#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_lowest_price.py — lowest_price.py 单元测试
无需 pytest,直接 python3 运行。
"""
import json
import subprocess
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import lowest_price  # noqa: E402

DATA_DIR = ROOT / "data"
EXAMPLE_INPUT = DATA_DIR / "prices.example.json"


def make_snapshots(prices_with_offsets):
    """辅助:[(day_offset, price, original_price|None), ...] → 快照 list(asof=2026-08-27)。"""
    asof = date(2026, 8, 27)
    out = []
    for d, p, orig in prices_with_offsets:
        out.append({
            "product_id": "P000",
            "platform": "jd",
            "price": p,
            "original_price": orig,
            "date": (asof - timedelta(days=d)).isoformat(),
        })
    return out


class TestFilterAndGroup(unittest.TestCase):
    """窗口过滤 + 聚合"""

    def test_filter_window_inclusive(self):
        """窗口含 asof 当天 + (days-1) 天前。"""
        asof = date(2026, 8, 27)
        snaps = make_snapshots([(0, 100, None), (29, 200, None), (30, 999, None)])
        in_win = lowest_price.filter_window(snaps, asof, days=30)
        self.assertEqual(len(in_win), 2)  # day 0 + day 29

    def test_group_by_product(self):
        snaps = [
            {"product_id": "A", "platform": "jd", "price": 100, "date": "2026-08-27"},
            {"product_id": "A", "platform": "pdd", "price": 90, "date": "2026-08-27"},
            {"product_id": "B", "platform": "jd", "price": 200, "date": "2026-08-27"},
        ]
        grouped = lowest_price.group_by_product(snaps)
        self.assertEqual(len(grouped), 2)
        self.assertEqual(len(grouped["A"]), 2)


class TestLowestPrice(unittest.TestCase):
    """30 天最低价计算"""

    def test_lowest_min(self):
        snaps = make_snapshots([(0, 100, None), (10, 80, None), (20, 120, None)])
        self.assertEqual(lowest_price.lowest_in_window(snaps)["price"], 80)

    def test_lowest_empty(self):
        self.assertIsNone(lowest_price.lowest_in_window([]))

    def test_lowest_exclude_date(self):
        """exclude_date 不参与比较。"""
        snaps = make_snapshots([(0, 50, None), (5, 80, None)])
        # 不排除:50 胜
        self.assertEqual(lowest_price.lowest_in_window(snaps)["price"], 50)
        # 排除 day 0:80 胜
        self.assertEqual(
            lowest_price.lowest_in_window(snaps, exclude_date=date(2026, 8, 27))["price"],
            80,
        )

    def test_current_price_today(self):
        """asof 当天有数据时取当日最低平台价。"""
        asof = date(2026, 8, 27)
        snaps = [
            {"product_id": "X", "platform": "jd", "price": 100, "date": asof.isoformat()},
            {"product_id": "X", "platform": "pdd", "price": 90, "date": asof.isoformat()},
            {"product_id": "X", "platform": "taobao", "price": 95, "date": asof.isoformat()},
        ]
        cur = lowest_price.current_price(snaps, asof)
        self.assertEqual(cur["price"], 90)
        self.assertEqual(cur["platform"], "pdd")

    def test_current_price_fallback(self):
        """asof 当天无数据时取最近一次。"""
        asof = date(2026, 8, 27)
        snaps = [
            {"product_id": "X", "platform": "jd", "price": 100, "date": "2026-08-25"},
            {"product_id": "X", "platform": "pdd", "price": 90, "date": "2026-08-20"},
        ]
        cur = lowest_price.current_price(snaps, asof)
        self.assertEqual(cur["price"], 100)  # 8/25 是最近


class TestFakeDiscount(unittest.TestCase):
    """虚假折扣三种启发式"""

    def test_heuristic_a_overprice(self):
        """当前价 > 历史中位数 × 1.10 → overprice_in_disguise。"""
        snaps = make_snapshots([
            (29, 850, 1200), (25, 800, 1200), (20, 820, 1200),
            (15, 880, 1200), (10, 860, 1200), (5, 840, 1200),
        ])
        current = {"price": 1299, "original_price": 1599, "platform": "jd", "date": "2026-08-27"}
        result = lowest_price.detect_fake_discount(snaps, current, snaps[0])
        self.assertIsNotNone(result)
        self.assertEqual(result["kind"], "overprice_in_disguise")

    def test_heuristic_b_inflated_original(self):
        """挂牌原价 > 历史最高 × 1.20 → inflated_original_price。"""
        snaps = make_snapshots([
            (29, 2999, 3299), (20, 2899, 3299), (15, 2799, 3299),
            (10, 2899, 3299), (5, 2799, 3299),
        ])
        current = {"price": 2799, "original_price": 4999, "platform": "jd", "date": "2026-08-27"}
        result = lowest_price.detect_fake_discount(snaps, current, snaps[2])
        self.assertIsNotNone(result)
        self.assertEqual(result["kind"], "inflated_original_price")

    def test_heuristic_c_smokescreen(self):
        """大折扣率 + 前 30 天最低仍高于当前 → smokescreen_discount。"""
        snaps = make_snapshots([
            (29, 1300, 1500), (25, 1100, 1500), (20, 1300, 1500),
            (15, 899, 1500), (10, 1300, 1500), (5, 1100, 1500),
        ])
        # prior_lowest = 899(15 天前)
        prior_lowest = next(s for s in snaps if s["price"] == 899)
        current = {"price": 690, "original_price": 1500, "platform": "taobao", "date": "2026-08-27"}
        result = lowest_price.detect_fake_discount(snaps, current, prior_lowest)
        self.assertIsNotNone(result)
        self.assertEqual(result["kind"], "smokescreen_discount")

    def test_no_fake_discount_normal(self):
        """正常价无任何启发式命中。"""
        snaps = make_snapshots([
            (29, 320, 360), (25, 318, 360), (20, 322, 360),
            (15, 320, 360), (10, 318, 360), (5, 322, 360),
        ])
        current = {"price": 320, "original_price": 360, "platform": "jd", "date": "2026-08-27"}
        result = lowest_price.detect_fake_discount(snaps, current, snaps[0])
        self.assertIsNone(result)

    def test_heuristic_priority_a_beats_b(self):
        """启发式 a 优先于 b:同时满足时返回 a。"""
        snaps = make_snapshots([
            (29, 800, 1200), (25, 800, 1200), (20, 800, 1200),
            (15, 800, 1200), (10, 800, 1200), (5, 800, 1200),
        ])
        # 当前价 1299 (> 800 × 1.10 = 880) 命中 a
        # 原价 1599 (> 800 × 1.20 = 960) 也会命中 b
        current = {"price": 1299, "original_price": 1599, "platform": "jd", "date": "2026-08-27"}
        result = lowest_price.detect_fake_discount(snaps, current, snaps[0])
        self.assertEqual(result["kind"], "overprice_in_disguise")

    def test_too_few_samples_skipped(self):
        """样本 < 3 时不下结论(避免噪声)。"""
        snaps = make_snapshots([(0, 100, 200), (5, 50, 200)])
        current = {"price": 50, "original_price": 200, "platform": "jd", "date": "2026-08-27"}
        result = lowest_price.detect_fake_discount(snaps, current, snaps[1])
        self.assertIsNone(result)


class TestBuildReport(unittest.TestCase):
    """完整报告生成"""

    def test_meta_counts(self):
        with EXAMPLE_INPUT.open(encoding="utf-8") as f:
            snaps = json.load(f)
        report = lowest_price.build_full_report(snaps, asof=date(2026, 8, 27), days=30)
        self.assertEqual(report["meta"]["products_analyzed"], 6)
        self.assertEqual(report["meta"]["total_snapshots"], len(snaps))
        # P002/P003/P004 三种虚假折扣
        self.assertEqual(report["meta"]["fake_discount_flagged"], 3)
        self.assertEqual(
            set(report["flagged_products"]),
            {"P002", "P003", "P004"},
        )

    def test_per_product_structure(self):
        with EXAMPLE_INPUT.open(encoding="utf-8") as f:
            snaps = json.load(f)
        report = lowest_price.build_full_report(snaps, asof=date(2026, 8, 27), days=30)
        p001 = next(p for p in report["products"] if p["product_id"] == "P001")
        self.assertIn("lowest_30d", p001)
        self.assertEqual(p001["lowest_30d"]["price"], 3299)
        self.assertIsNone(p001["fake_discount"])

    def test_product_filter(self):
        with EXAMPLE_INPUT.open(encoding="utf-8") as f:
            snaps = json.load(f)
        report = lowest_price.build_full_report(
            snaps, asof=date(2026, 8, 27), days=30, product_filter="P002"
        )
        self.assertEqual(report["meta"]["products_analyzed"], 1)
        self.assertEqual(report["products"][0]["product_id"], "P002")
        self.assertEqual(report["products"][0]["fake_discount"]["kind"], "overprice_in_disguise")

    def test_default_asof_uses_max_date(self):
        """不传 asof 时取快照最大日期。"""
        with EXAMPLE_INPUT.open(encoding="utf-8") as f:
            snaps = json.load(f)
        report = lowest_price.build_full_report(snaps, asof=None, days=30)
        self.assertEqual(report["meta"]["asof"], "2026-08-27")


class TestCLI(unittest.TestCase):
    """lowest_price.py CLI 子进程"""

    def test_cli_markdown_default(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "lowest_price.py"),
             "--input", str(EXAMPLE_INPUT)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr}")
        out = result.stdout
        self.assertIn("价格报告", out)
        self.assertIn("P001", out)
        self.assertIn("P006", out)
        self.assertIn("🚩 overprice_in_disguise", out)
        self.assertIn("🚩 inflated_original_price", out)
        self.assertIn("🚩 smokescreen_discount", out)

    def test_cli_json_mode(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "lowest_price.py"),
             "--input", str(EXAMPLE_INPUT), "--json"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertIn("meta", data)
        self.assertIn("products", data)

    def test_cli_writes_report(self):
        out_path = ROOT / "data" / "_test_report.json"
        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "lowest_price.py"),
                 "--input", str(EXAMPLE_INPUT),
                 "--report-out", str(out_path)],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0)
            self.assertTrue(out_path.exists())
            data = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(data["meta"]["fake_discount_flagged"], 3)
        finally:
            if out_path.exists():
                out_path.unlink()


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestFilterAndGroup))
    suite.addTests(loader.loadTestsFromTestCase(TestLowestPrice))
    suite.addTests(loader.loadTestsFromTestCase(TestFakeDiscount))
    suite.addTests(loader.loadTestsFromTestCase(TestBuildReport))
    suite.addTests(loader.loadTestsFromTestCase(TestCLI))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
