#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_brands.py — seed_brands.py / rank_brands.py 单元测试
无需 pytest,直接 python3 运行。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# 把 scripts/ 加进 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import seed_brands  # noqa: E402
import rank_brands  # noqa: E402

DATA_DIR = ROOT / "data"
BRANDS_PATH = DATA_DIR / "brands.json"
SCHEMA_PATH = DATA_DIR / "schema.json"


class TestSeedBrands(unittest.TestCase):
    """seed_brands.py 数据生成 + 校验"""

    def test_count_at_least_50(self):
        """Phase 0 要求品牌 >= 50。"""
        brands = seed_brands.build_brands()
        self.assertGreaterEqual(len(brands), 50,
                                f"品牌数 {len(brands)} 不足 50")
        print(f"  [info] 品牌总数: {len(brands)}")

    def test_all_required_fields(self):
        """每条 brand 必须含 id/name/slug/category_slug/scores/origin/positioning/notes。"""
        brands = seed_brands.build_brands()
        for b in brands:
            self.assertIn("id", b)
            self.assertIn("name", b)
            self.assertIn("slug", b)
            self.assertIn("category_slug", b)
            self.assertIn("scores", b)
            self.assertIn("origin", b)
            self.assertIn("positioning", b)
            self.assertIn("notes", b)
            for sub in ("quality", "service", "value"):
                self.assertIn(sub, b["scores"])
                self.assertGreaterEqual(b["scores"][sub], 0.0)
                self.assertLessEqual(b["scores"][sub], 5.0)

    def test_unique_ids(self):
        """id 全局唯一。"""
        brands = seed_brands.build_brands()
        ids = [b["id"] for b in brands]
        self.assertEqual(len(ids), len(set(ids)), f"id 重复: {[i for i in ids if ids.count(i) > 1]}")

    def test_covers_all_10_categories(self):
        """覆盖项目开发计划 §五 10 大品类。"""
        brands = seed_brands.build_brands()
        cats = {b["category_slug"] for b in brands}
        expected = {"digital", "home-appliance", "apparel", "beauty",
                    "maternal-infant", "food", "home", "sports", "books", "health"}
        missing = expected - cats
        self.assertFalse(missing, f"缺品类: {missing}")
        print(f"  [info] 覆盖品类: {len(cats)}/10")

    def test_brands_json_matches_seed(self):
        """data/brands.json 与 BRANDS 种子表行数一致(若有旧文件,跑 seed 后应 >= 50)。"""
        if BRANDS_PATH.exists():
            with BRANDS_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertGreaterEqual(len(data), 50, f"brands.json 现有 {len(data)} < 50")

    def test_positioning_enum_valid(self):
        """positioning 必须是 schema 允许的 4 个枚举之一。"""
        valid = {"high-end", "mid", "entry", "value"}
        brands = seed_brands.build_brands()
        for b in brands:
            self.assertIn(b["positioning"], valid, f"id={b['id']} positioning={b['positioning']} 非法")


class TestRankBrands(unittest.TestCase):
    """rank_brands.py 综合分计算 + 过滤排序"""

    def setUp(self):
        # 临时 brands.json
        self.tmpdir = tempfile.mkdtemp()
        self.tmp_brands = Path(self.tmpdir) / "brands.json"
        brands = [
            {"id": 1, "name": "A", "slug": "a", "category_slug": "digital",
             "origin": "X", "positioning": "high-end",
             "scores": {"quality": 5.0, "service": 5.0, "value": 5.0}, "notes": ""},
            {"id": 2, "name": "B", "slug": "b", "category_slug": "digital",
             "origin": "X", "positioning": "value",
             "scores": {"quality": 3.0, "service": 3.0, "value": 5.0}, "notes": ""},
            {"id": 3, "name": "C", "slug": "c", "category_slug": "apparel",
             "origin": "Y", "positioning": "mid",
             "scores": {"quality": 4.0, "service": 4.0, "value": 4.0}, "notes": ""},
        ]
        with self.tmp_brands.open("w", encoding="utf-8") as f:
            json.dump(brands, f)

    def test_composite_score_formula(self):
        """综合分 = 0.4*q + 0.3*s + 0.3*v。"""
        b = {"scores": {"quality": 5.0, "service": 4.0, "value": 3.0}}
        # 0.4*5 + 0.3*4 + 0.3*3 = 2.0 + 1.2 + 0.9 = 4.1
        self.assertEqual(rank_brands.composite_score(b), 4.1)

    def test_filter_by_category(self):
        brands = rank_brands.load_brands(self.tmp_brands)
        out = rank_brands.filter_brands(brands, category="digital", positioning=None)
        self.assertEqual(len(out), 2)
        self.assertTrue(all(b["category_slug"] == "digital" for b in out))

    def test_filter_by_positioning(self):
        brands = rank_brands.load_brands(self.tmp_brands)
        out = rank_brands.filter_brands(brands, category=None, positioning="high-end")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "A")

    def test_rank_order(self):
        """A(5/5/5=5.0) > C(4/4/4=4.0) > B(3/3/5=3.6)。"""
        brands = rank_brands.load_brands(self.tmp_brands)
        top = rank_brands.rank(brands, top=3)
        self.assertEqual([b["name"] for b in top], ["A", "C", "B"])

    def test_cli_runs(self):
        """rank_brands.py CLI 子进程能跑出 markdown。"""
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "rank_brands.py"),
             "--brands", str(self.tmp_brands),
             "--category", "digital", "--top", "2"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr}")
        self.assertIn("A", result.stdout)
        self.assertIn("B", result.stdout)
        self.assertIn("| 排名 |", result.stdout)


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestSeedBrands))
    suite.addTests(loader.loadTestsFromTestCase(TestRankBrands))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
