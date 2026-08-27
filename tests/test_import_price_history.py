#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_import_price_history.py — 历史价导入器单测

覆盖:
  - 字段校验(缺字段 / 错日期 / 非正价 / 未知平台)
  - 分组 + 排序
  - 去重(同 product+platform+date+price)
  - 统计(count / date_min / date_max / platforms / min / max)
  - 端到端(读 prices.example.json → 写临时输出 → 校验产物)

运行:
  cd /Users/aaron/Mac/Consultant/11-消费-Consumption/_ConsumptionLib/ConsumptionWeb
  python3 tests/test_import_price_history.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

# 让脚本可被 unittest discover 找到
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import import_price_history as iph  # noqa: E402


class TestValidateSnapshot(unittest.TestCase):
    """单条字段校验。"""

    def test_valid_snapshot(self):
        snap, err = iph.validate_snapshot({
            "product_id": "P001",
            "platform": "jd",
            "price": 100,
            "original_price": 200,
            "date": "2026-08-28",
        }, 0)
        self.assertIsNone(err)
        self.assertEqual(snap["product_id"], "P001")
        self.assertEqual(snap["platform"], "jd")
        self.assertEqual(snap["price"], 100.0)
        self.assertEqual(snap["original_price"], 200.0)
        self.assertEqual(snap["date"], "2026-08-28")

    def test_missing_product_id(self):
        snap, err = iph.validate_snapshot({
            "platform": "jd", "price": 100, "date": "2026-08-28",
        }, 5)
        self.assertIsNone(snap)
        self.assertIn("product_id", err)

    def test_missing_date(self):
        snap, err = iph.validate_snapshot({
            "product_id": "P001", "platform": "jd", "price": 100,
        }, 7)
        self.assertIsNone(snap)
        self.assertIn("date", err)

    def test_non_dict(self):
        snap, err = iph.validate_snapshot("not a dict", 0)
        self.assertIsNone(snap)
        self.assertIn("not a dict", err)

    def test_invalid_date_format(self):
        snap, err = iph.validate_snapshot({
            "product_id": "P001", "platform": "jd",
            "price": 100, "date": "2026/08/28",
        }, 0)
        self.assertIsNone(snap)
        self.assertIn("invalid date", err)

    def test_non_positive_price(self):
        snap, err = iph.validate_snapshot({
            "product_id": "P001", "platform": "jd",
            "price": 0, "date": "2026-08-28",
        }, 0)
        self.assertIsNone(snap)
        self.assertIn("non-positive", err)

    def test_non_numeric_price(self):
        snap, err = iph.validate_snapshot({
            "product_id": "P001", "platform": "jd",
            "price": "free", "date": "2026-08-28",
        }, 0)
        self.assertIsNone(snap)
        self.assertIn("non-numeric", err)

    def test_empty_platform_rejected(self):
        snap, err = iph.validate_snapshot({
            "product_id": "P001", "platform": "",
            "price": 100, "date": "2026-08-28",
        }, 0)
        self.assertIsNone(snap)
        self.assertIn("platform", err)

    def test_unknown_platform_accepted(self):
        """lululemon-flagship / 线下店等长尾值允许通过。"""
        snap, err = iph.validate_snapshot({
            "product_id": "P006", "platform": "lululemon-flagship",
            "price": 500, "date": "2026-08-28",
        }, 0)
        self.assertIsNone(err)
        self.assertEqual(snap["platform"], "lululemon-flagship")

    def test_invalid_original_price_ignored(self):
        """无效 original_price 视为无标,不当作致命错。"""
        snap, err = iph.validate_snapshot({
            "product_id": "P001", "platform": "jd",
            "price": 100, "original_price": "junk",
            "date": "2026-08-28",
        }, 0)
        self.assertIsNone(err)
        self.assertIsNone(snap["original_price"])


class TestImportSnapshots(unittest.TestCase):
    """分组 + 排序 + 去重。"""

    def test_grouping(self):
        raw = [
            {"product_id": "A", "platform": "jd", "price": 10, "date": "2026-08-01"},
            {"product_id": "B", "platform": "jd", "price": 20, "date": "2026-08-01"},
            {"product_id": "A", "platform": "taobao", "price": 11, "date": "2026-08-02"},
        ]
        grouped, dropped = iph.import_snapshots(raw)
        self.assertEqual(dropped, 0)
        self.assertEqual(set(grouped.keys()), {"A", "B"})
        self.assertEqual(len(grouped["A"]), 2)
        self.assertEqual(len(grouped["B"]), 1)

    def test_sorting(self):
        raw = [
            {"product_id": "A", "platform": "jd", "price": 10, "date": "2026-08-05"},
            {"product_id": "A", "platform": "jd", "price": 12, "date": "2026-08-01"},
            {"product_id": "A", "platform": "jd", "price": 11, "date": "2026-08-03"},
        ]
        grouped, _ = iph.import_snapshots(raw)
        dates = [s["date"] for s in grouped["A"]]
        self.assertEqual(dates, ["2026-08-01", "2026-08-03", "2026-08-05"])

    def test_dedup(self):
        raw = [
            {"product_id": "A", "platform": "jd", "price": 10, "date": "2026-08-01"},
            {"product_id": "A", "platform": "jd", "price": 10, "date": "2026-08-01"},
            {"product_id": "A", "platform": "jd", "price": 11, "date": "2026-08-01"},
        ]
        grouped, _ = iph.import_snapshots(raw)
        self.assertEqual(len(grouped["A"]), 2)

    def test_dropped_count(self):
        raw = [
            {"product_id": "A", "platform": "jd", "price": 10, "date": "2026-08-01"},
            {"platform": "jd", "price": 20, "date": "2026-08-01"},  # 缺 product_id
            {"product_id": "B", "platform": "jd", "price": 0, "date": "2026-08-01"},  # 非正价
        ]
        grouped, dropped = iph.import_snapshots(raw)
        self.assertEqual(dropped, 2)
        self.assertEqual(set(grouped.keys()), {"A"})


class TestBuildProductStats(unittest.TestCase):
    def test_basic(self):
        snaps = [
            {"product_id": "A", "platform": "jd", "price": 100, "date": "2026-08-01"},
            {"product_id": "A", "platform": "taobao", "price": 80, "date": "2026-08-05"},
            {"product_id": "A", "platform": "pdd", "price": 90, "date": "2026-08-03"},
        ]
        # 已按 date 升序
        snaps.sort(key=lambda s: s["date"])
        stats = iph.build_product_stats(snaps)
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["date_min"], "2026-08-01")
        self.assertEqual(stats["date_max"], "2026-08-05")
        self.assertEqual(stats["min_price"], 80.0)
        self.assertEqual(stats["max_price"], 100.0)
        self.assertEqual(stats["platforms"], {"jd": 1, "taobao": 1, "pdd": 1})

    def test_empty(self):
        stats = iph.build_product_stats([])
        self.assertEqual(stats, {"count": 0})


class TestBuildOutput(unittest.TestCase):
    def test_structure(self):
        grouped = {
            "P001": [
                {"product_id": "P001", "platform": "jd", "price": 100,
                 "original_price": 200, "date": "2026-08-01"},
            ],
        }
        out = iph.build_output(grouped, source="test.json")
        self.assertIn("meta", out)
        self.assertIn("products", out)
        self.assertEqual(out["meta"]["snapshot_count"], 1)
        self.assertEqual(out["meta"]["sku_count"], 1)
        self.assertEqual(out["meta"]["source"], "test.json")
        self.assertIn("P001", out["products"])
        self.assertIn("stats", out["products"]["P001"])
        self.assertIn("snapshots", out["products"]["P001"])


class TestEndToEnd(unittest.TestCase):
    """读 prices.example.json → 导入 → 校验产物。"""

    def setUp(self):
        self.input_path = ROOT / "data" / "prices.example.json"
        self.tmpdir = tempfile.mkdtemp()
        self.output_path = Path(self.tmpdir) / "out.json"

    def test_real_data_imports(self):
        if not self.input_path.exists():
            self.skipTest(f"missing test fixture: {self.input_path}")
        raw = json.loads(self.input_path.read_text(encoding="utf-8"))
        grouped, dropped = iph.import_snapshots(raw)
        out = iph.build_output(grouped, source=self.input_path.name)
        # 6 SKU (P001-P006) 全部入库
        self.assertEqual(out["meta"]["sku_count"], 6)
        # 58 快照原始数据,全部通过校验
        self.assertEqual(out["meta"]["snapshot_count"], 58)
        self.assertEqual(dropped, 0)
        # 每个 SKU 至少 1 个快照
        for pid, payload in out["products"].items():
            self.assertGreaterEqual(payload["stats"]["count"], 1, f"{pid} empty")
            # 排序:date 单调不减
            dates = [s["date"] for s in payload["snapshots"]]
            self.assertEqual(dates, sorted(dates), f"{pid} not sorted")
            # min_price <= max_price
            self.assertLessEqual(
                payload["stats"]["min_price"],
                payload["stats"]["max_price"],
            )
        # P001 (相机):京东有最低 3299,最大 3799
        p001 = out["products"]["P001"]
        self.assertIn("jd", p001["stats"]["platforms"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
