#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_md_to_json.py — md_to_json.py 单元测试
无需 pytest,直接 python3 运行。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

# 把 scripts/ 加进 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import md_to_json  # noqa: E402


SAMPLE_MD = """# 消费品类清单

## 数码

- 手机
- 笔记本
- 耳机

## 家电

- 空调
- 冰箱

## 服饰
"""


SAMPLE_BRAND_MD = """# 品牌评估框架

## Apple

| 维度 | 分数 |
|------|------|
| 质量 | 4.8 |
| 服务 | 4.2 |
| 性价比 | 3.5 |
| 定位 | high-end |
| 产地 | 美国 |

## 小米

| 维度 | 分数 |
|------|------|
| 质量 | 4.0 |
| 服务 | 3.5 |
| 性价比 | 4.6 |
| 定位 | value |
| 产地 | 中国 |
"""


class TestMarkdownParser(unittest.TestCase):
    def test_parse_h1_title(self):
        doc = md_to_json.parse_markdown(SAMPLE_MD)
        self.assertEqual(doc.title, "消费品类清单")

    def test_parse_sections(self):
        doc = md_to_json.parse_markdown(SAMPLE_MD)
        headings = [s["heading"] for s in doc.sections]
        self.assertEqual(headings, ["数码", "家电", "服饰"])

    def test_parse_list_items(self):
        doc = md_to_json.parse_markdown(SAMPLE_MD)
        digital = doc.sections[0]
        self.assertEqual(digital["items"], ["手机", "笔记本", "耳机"])


class TestSchemaValidator(unittest.TestCase):
    def test_valid_categories(self):
        data = [
            {"id": 1, "name": "数码", "slug": "digital", "priority": "P0",
             "subcategories": [{"name": "手机"}]}
        ]
        md_to_json.validate_categories(data)  # 不应抛错

    def test_duplicate_slug_fails(self):
        data = [
            {"id": 1, "name": "A", "slug": "same", "priority": "P0", "subcategories": []},
            {"id": 2, "name": "B", "slug": "same", "priority": "P1", "subcategories": []},
        ]
        with self.assertRaises(md_to_json.SchemaError):
            md_to_json.validate_categories(data)

    def test_invalid_priority_fails(self):
        data = [{"id": 1, "name": "A", "slug": "a", "priority": "PX", "subcategories": []}]
        with self.assertRaises(md_to_json.SchemaError):
            md_to_json.validate_categories(data)

    def test_score_out_of_range(self):
        data = [{
            "id": 1, "name": "X", "slug": "x", "category_slug": "digital",
            "positioning": "high-end", "scores": {"quality": 6.0, "service": 3.0, "value": 3.0}
        }]
        with self.assertRaises(md_to_json.SchemaError):
            md_to_json.validate_brands(data)


class TestAdapters(unittest.TestCase):
    def test_adapt_categories_from_md(self):
        doc = md_to_json.parse_markdown(SAMPLE_MD)
        out = md_to_json.adapt_categories(doc, fallback=[])
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0]["name"], "数码")
        # 中文标题归一化后为空 → fallback 到 cat-1
        self.assertEqual(out[0]["slug"], "cat-1")
        self.assertEqual(len(out[0]["subcategories"]), 3)
        # 第一个子项保留中文名
        self.assertEqual(out[0]["subcategories"][0]["name"], "手机")

    def test_adapt_brands_from_table(self):
        doc = md_to_json.parse_markdown(SAMPLE_BRAND_MD)
        out = md_to_json.adapt_brands(doc, fallback=[])
        self.assertEqual(len(out), 2)
        self.assertAlmostEqual(out[0]["scores"]["quality"], 4.8)
        self.assertEqual(out[0]["positioning"], "high-end")
        self.assertEqual(out[1]["positioning"], "value")


class TestEndToEnd(unittest.TestCase):
    def test_run_with_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            n_cat, n_brand = md_to_json.run(use_fallback=True, out_dir=out)
            self.assertEqual(n_cat, 10)
            self.assertEqual(n_brand, 5)
            self.assertTrue((out / "categories.json").exists())
            self.assertTrue((out / "brands.json").exists())
            # 校验写出文件可被 json 解析
            data = json.loads((out / "categories.json").read_text(encoding="utf-8"))
            self.assertEqual(data[0]["slug"], "digital")


if __name__ == "__main__":
    unittest.main(verbosity=2)
