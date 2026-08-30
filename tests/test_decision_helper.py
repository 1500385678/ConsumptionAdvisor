#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_decision_helper.py — decision_helper.py 单元测试

覆盖:
- composite_score: 权重 0.4/0.3/0.3
- filter_brands: 品类 + 定位过滤
- rank: 倒序取前 N
- worth_score: need/want × P0/P1/P2 四个分支
- decide: 端到端 + 未知品类报错
- render: 表格含 "排名 / 品牌 / 综合分"

数据使用 data/ 真实文件,确保 schema 同步。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import decision_helper as dh  # noqa: E402


class TestCompositeScore(unittest.TestCase):
    def test_weights_4_3_3(self):
        brand = {"scores": {"quality": 5.0, "service": 4.0, "value": 3.0}}
        # 0.4*5 + 0.3*4 + 0.3*3 = 2.0 + 1.2 + 0.9 = 4.1
        self.assertEqual(dh.composite_score(brand), 4.1)

    def test_all_five(self):
        brand = {"scores": {"quality": 5.0, "service": 5.0, "value": 5.0}}
        self.assertEqual(dh.composite_score(brand), 5.0)

    def test_all_one(self):
        brand = {"scores": {"quality": 1.0, "service": 1.0, "value": 1.0}}
        self.assertEqual(dh.composite_score(brand), 1.0)


class TestFilterBrands(unittest.TestCase):
    def setUp(self):
        self.brands = [
            {"name": "Apple", "category_slug": "digital", "positioning": "high-end",
             "scores": {"quality": 4.8, "service": 4.2, "value": 3.5}},
            {"name": "小米", "category_slug": "digital", "positioning": "value",
             "scores": {"quality": 4.0, "service": 3.5, "value": 4.6}},
            {"name": "Ubras", "category_slug": "apparel", "positioning": "value",
             "scores": {"quality": 4.0, "service": 3.8, "value": 4.3}},
        ]

    def test_filter_category_only(self):
        out = dh.filter_brands(self.brands, "digital", None)
        self.assertEqual(len(out), 2)
        self.assertTrue(all(b["category_slug"] == "digital" for b in out))

    def test_filter_category_and_position(self):
        out = dh.filter_brands(self.brands, "digital", "value")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "小米")

    def test_filter_empty(self):
        out = dh.filter_brands(self.brands, "books", None)
        self.assertEqual(out, [])


class TestRank(unittest.TestCase):
    def test_top_n_descending(self):
        brands = [
            {"name": "A", "scores": {"quality": 3.0, "service": 3.0, "value": 3.0}},
            {"name": "B", "scores": {"quality": 5.0, "service": 5.0, "value": 5.0}},
            {"name": "C", "scores": {"quality": 4.0, "service": 4.0, "value": 4.0}},
        ]
        ranked = dh.rank(brands, top=2)
        self.assertEqual([b["name"] for b in ranked], ["B", "C"])

    def test_top_larger_than_list(self):
        brands = [{"name": "A", "scores": {"quality": 4.0, "service": 4.0, "value": 4.0}}]
        ranked = dh.rank(brands, top=10)
        self.assertEqual(len(ranked), 1)


class TestWorthScore(unittest.TestCase):
    def test_need_p0(self):
        cat = {"priority": "P0", "decision_bias": "长值优先,谨慎升级"}
        self.assertEqual(dh.worth_score(cat, need_flag=True, positioning="mid"), 5)

    def test_need_p1(self):
        cat = {"priority": "P1", "decision_bias": "场合+频次"}
        self.assertEqual(dh.worth_score(cat, need_flag=True, positioning="value"), 4)

    def test_need_p2(self):
        cat = {"priority": "P2", "decision_bias": "电子优先"}
        self.assertEqual(dh.worth_score(cat, need_flag=True, positioning=None), 3)

    def test_want_any_priority_is_1(self):
        for p in ("P0", "P1", "P2"):
            cat = {"priority": p, "decision_bias": "x"}
            self.assertEqual(dh.worth_score(cat, need_flag=False, positioning="mid"), 1)

    def test_unknown_priority_defaults_to_3(self):
        cat = {"priority": "P9", "decision_bias": "x"}
        self.assertEqual(dh.worth_score(cat, need_flag=True, positioning=None), 3)


class TestDecide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.brands = dh.load_json(dh.BRANDS_PATH)
        cls.categories = dh.load_json(dh.CATEGORIES_PATH)

    def test_digital_need_top3(self):
        cat, top, worth = dh.decide(
            self.categories, self.brands,
            "digital", "mid", need_flag=True, top=3,
        )
        self.assertEqual(cat["slug"], "digital")
        self.assertEqual(cat["priority"], "P0")
        self.assertEqual(worth, 5)
        self.assertEqual(len(top), 3)
        # 全部都是 mid 定位
        for b in top:
            self.assertEqual(b["positioning"], "mid")

    def test_apparel_want(self):
        cat, top, worth = dh.decide(
            self.categories, self.brands,
            "apparel", None, need_flag=False, top=3,
        )
        self.assertEqual(worth, 1)
        # 服饰有品牌即可
        self.assertGreater(len(top), 0)

    def test_unknown_category_raises(self):
        with self.assertRaises(SystemExit):
            dh.decide(self.categories, self.brands,
                      "not-a-cat", None, need_flag=True, top=3)

    def test_no_brand_match_returns_empty(self):
        # health 是 P1,有品牌;选一个应该能返回 0 的组合
        # 实际数据中,数字"健康保健"品类 + high-end 也许空
        # 用人造 brands 测试
        fake_brands = [
            {"name": "X", "category_slug": "health", "positioning": "mid",
             "scores": {"quality": 4.0, "service": 4.0, "value": 4.0}}
        ]
        cat, top, worth = dh.decide(
            self.categories, fake_brands,
            "health", "high-end", need_flag=True, top=3,
        )
        self.assertEqual(top, [])
        self.assertEqual(worth, 4)  # P1 + need = 4


class TestRender(unittest.TestCase):
    def test_render_contains_key_fields(self):
        cat = {"slug": "digital", "name": "数码", "priority": "P0",
               "decision_bias": "长值优先,谨慎升级"}
        top = [
            {"name": "华为", "category_slug": "digital", "positioning": "mid",
             "origin": "中国", "scores": {"quality": 4.4, "service": 3.8, "value": 4.0},
             "notes": "自研芯片+鸿蒙生态"},
        ]
        out = dh.render(need_flag=True, category=cat,
                        positioning="mid", top_brands=top, worth=5)
        self.assertIn("决策辅助报告", out)
        self.assertIn("**5 / 5**", out)
        self.assertIn("华为", out)
        self.assertIn("**4.1**", out)  # composite 4.1
        self.assertIn("Top 推荐", out)
        # 5 分用 ✅
        self.assertIn("✅", out)

    def test_render_want_shows_stop(self):
        cat = {"slug": "digital", "name": "数码", "priority": "P0",
               "decision_bias": "长值优先,谨慎升级"}
        out = dh.render(need_flag=False, category=cat,
                        positioning=None, top_brands=[], worth=1)
        self.assertIn("**1 / 5**", out)
        self.assertIn("🛑", out)
        self.assertIn("无匹配品牌", out)

    def test_render_no_match_message(self):
        cat = {"slug": "books", "name": "图书教育", "priority": "P2",
               "decision_bias": "电子优先"}
        out = dh.render(need_flag=True, category=cat,
                        positioning="high-end", top_brands=[], worth=3)
        self.assertIn("**3 / 5**", out)
        self.assertIn("⚖️", out)


class TestEndToEndCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.brands = dh.load_json(dh.BRANDS_PATH)
        cls.categories = dh.load_json(dh.CATEGORIES_PATH)
        # 保证 data/ 内至少有 1 个 digital mid 品牌
        cls.has_digital_mid = any(
            b["category_slug"] == "digital" and b["positioning"] == "mid"
            for b in cls.brands
        )

    def test_invoke_main_help(self):
        from io import StringIO
        # 模拟 --help,确保 argparse 配置不冲突
        old_argv = sys.argv
        sys.argv = ["decision_helper.py", "--help"]
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            with self.assertRaises(SystemExit) as cm:
                dh.main()
            self.assertEqual(cm.exception.code, 0)
        finally:
            sys.argv = old_argv
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main(verbosity=2)
