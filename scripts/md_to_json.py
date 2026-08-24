#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md_to_json.py — 把 md 源文件转成结构化 JSON

输入:消费品类清单.md / 品牌评估框架.md
输出:data/categories.json / data/brands.json

设计要点:
  1. 解析器支持三类 md 结构:一级/二级标题、Markdown 列表、Markdown 表格
  2. 源文件暂缺时,自动启用内置 fallback(10 大类 / 5 品牌种子数据)
  3. 写出 JSON 之前做 schema 校验,失败抛错并定位
  4. CLI 入口:python3 scripts/md_to_json.py [--source md | --fallback] [--out-dir data]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------- 路径常量 ----------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SCHEMA_FILE = DATA_DIR / "schema.json"
CATEGORIES_OUT = DATA_DIR / "categories.json"
BRANDS_OUT = DATA_DIR / "brands.json"

CATEGORY_MD = ROOT / "消费品类清单.md"
BRAND_MD = ROOT / "品牌评估框架.md"


# ---------- 内置 fallback 数据(源 md 缺位时使用) ----------
FALLBACK_CATEGORIES: List[Dict[str, Any]] = [
    {"id": 1, "name": "数码", "slug": "digital", "priority": "P0", "decision_bias": "长值优先,谨慎升级",
     "subcategories": [{"name": "手机", "examples": ["iPhone 15", "小米 14"]}]},
    {"id": 2, "name": "家电", "slug": "home-appliance", "priority": "P0", "decision_bias": "长寿命+能耗",
     "subcategories": [{"name": "空调", "examples": ["美的", "格力"]}]},
    {"id": 3, "name": "服饰", "slug": "apparel", "priority": "P1", "decision_bias": "场合+频次",
     "subcategories": [{"name": "内衣", "examples": ["Ubras"]}]},
    {"id": 4, "name": "美妆", "slug": "beauty", "priority": "P1", "decision_bias": "成分+肤质匹配",
     "subcategories": [{"name": "护肤", "examples": ["雅诗兰黛"]}]},
    {"id": 5, "name": "母婴", "slug": "maternal-infant", "priority": "P0", "decision_bias": "安全标准+真实口碑",
     "subcategories": [{"name": "奶粉", "examples": ["爱他美"]}]},
    {"id": 6, "name": "食品", "slug": "food", "priority": "P1", "decision_bias": "配料表优先",
     "subcategories": [{"name": "零食", "examples": ["三只松鼠"]}]},
    {"id": 7, "name": "家居", "slug": "home", "priority": "P1", "decision_bias": "频次+收纳",
     "subcategories": [{"name": "床品", "examples": ["MUJI"]}]},
    {"id": 8, "name": "运动户外", "slug": "sports", "priority": "P2", "decision_bias": "频次决定预算",
     "subcategories": [{"name": "跑鞋", "examples": ["HOKA"]}]},
    {"id": 9, "name": "图书教育", "slug": "books", "priority": "P2", "decision_bias": "电子优先",
     "subcategories": [{"name": "专业书", "examples": ["图灵"]}]},
    {"id": 10, "name": "健康保健", "slug": "health", "priority": "P1", "decision_bias": "体检优先",
     "subcategories": [{"name": "维生素", "examples": ["Nature Made"]}]},
]

FALLBACK_BRANDS: List[Dict[str, Any]] = [
    {"id": 1, "name": "Apple", "slug": "apple", "category_slug": "digital", "origin": "美国",
     "positioning": "high-end", "scores": {"quality": 4.8, "service": 4.2, "value": 3.5},
     "notes": "生态闭环强,保值率中等"},
    {"id": 2, "name": "小米", "slug": "xiaomi", "category_slug": "digital", "origin": "中国",
     "positioning": "value", "scores": {"quality": 4.0, "service": 3.5, "value": 4.6},
     "notes": "性价比标杆"},
    {"id": 3, "name": "美的", "slug": "midea", "category_slug": "home-appliance", "origin": "中国",
     "positioning": "mid", "scores": {"quality": 4.2, "service": 4.0, "value": 4.3},
     "notes": "国民家电,售后覆盖广"},
    {"id": 4, "name": "戴森", "slug": "dyson", "category_slug": "home-appliance", "origin": "英国",
     "positioning": "high-end", "scores": {"quality": 4.6, "service": 3.5, "value": 3.2},
     "notes": "高端定位,溢价明显"},
    {"id": 5, "name": "Lululemon", "slug": "lululemon", "category_slug": "apparel", "origin": "加拿大",
     "positioning": "high-end", "scores": {"quality": 4.5, "service": 3.8, "value": 3.4},
     "notes": "瑜伽裤标杆,二手保值"},
]


# ---------- 轻量 schema 校验器 ----------
class SchemaError(Exception):
    """schema 校验失败,带定位信息"""

    def __init__(self, path: str, msg: str):
        self.path = path
        self.msg = msg
        super().__init__(f"[{path}] {msg}")


def _expect_type(value: Any, types: Tuple[type, ...], path: str) -> None:
    if not isinstance(value, types):
        raise SchemaError(path, f"期望类型 {types}, 实际 {type(value).__name__}")


def _validate_score(obj: Dict[str, Any], path: str) -> None:
    """校验 scores 子对象"""
    if "scores" not in obj or not isinstance(obj["scores"], dict):
        raise SchemaError(path, "scores 字段缺失或非对象")
    for key in ("quality", "service", "value"):
        if key not in obj["scores"]:
            raise SchemaError(f"{path}.scores", f"缺失 {key}")
        v = obj["scores"][key]
        _expect_type(v, (int, float), f"{path}.scores.{key}")
        if not (0 <= v <= 5):
            raise SchemaError(f"{path}.scores.{key}", f"分数需在 0-5 之间,实际 {v}")


def validate_categories(data: List[Dict[str, Any]]) -> None:
    _expect_type(data, (list,), "categories")
    seen_slugs = set()
    for i, cat in enumerate(data):
        path = f"categories[{i}]"
        _expect_type(cat, (dict,), path)
        for key in ("id", "name", "slug", "priority", "subcategories"):
            if key not in cat:
                raise SchemaError(path, f"缺失必填字段 {key}")
        _expect_type(cat["id"], (int,), f"{path}.id")
        _expect_type(cat["name"], (str,), f"{path}.name")
        _expect_type(cat["slug"], (str,), f"{path}.slug")
        if cat["slug"] in seen_slugs:
            raise SchemaError(f"{path}.slug", f"slug 重复: {cat['slug']}")
        seen_slugs.add(cat["slug"])
        if cat["priority"] not in ("P0", "P1", "P2"):
            raise SchemaError(f"{path}.priority", f"非法优先级: {cat['priority']}")
        _expect_type(cat["subcategories"], (list,), f"{path}.subcategories")
        for j, sub in enumerate(cat["subcategories"]):
            _expect_type(sub, (dict,), f"{path}.subcategories[{j}]")
            if "name" not in sub:
                raise SchemaError(f"{path}.subcategories[{j}]", "缺失 name")


def validate_brands(data: List[Dict[str, Any]]) -> None:
    _expect_type(data, (list,), "brands")
    seen_slugs = set()
    for i, b in enumerate(data):
        path = f"brands[{i}]"
        _expect_type(b, (dict,), path)
        for key in ("id", "name", "slug", "category_slug", "scores"):
            if key not in b:
                raise SchemaError(path, f"缺失必填字段 {key}")
        if b["slug"] in seen_slugs:
            raise SchemaError(f"{path}.slug", f"slug 重复: {b['slug']}")
        seen_slugs.add(b["slug"])
        if b.get("positioning") and b["positioning"] not in ("high-end", "mid", "entry", "value"):
            raise SchemaError(f"{path}.positioning", f"非法定位: {b['positioning']}")
        _validate_score(b, path)


# ---------- MD 解析器 ----------
H1_RE = re.compile(r"^#\s+(.+)$")
H2_RE = re.compile(r"^##\s+(.+)$")
LIST_RE = re.compile(r"^[\-\*]\s+(.+)$")
TABLE_ROW_RE = re.compile(r"^\|.+\|$")
TABLE_SEP_RE = re.compile(r"^\|[\s\-\|:]+\|$")


@dataclass
class ParsedDoc:
    title: str = ""
    sections: List[Dict[str, Any]] = field(default_factory=list)


def _parse_table_rows(lines: List[str], start: int) -> Tuple[List[str], int]:
    """从 start 起解析表头/分隔/数据行,返回 (headers, next_index)"""
    headers = [c.strip() for c in lines[start].strip("|").split("|")]
    # 跳过分隔行
    next_i = start + 2
    return headers, next_i


def parse_markdown(text: str) -> ParsedDoc:
    """解析 md 文本为 ParsedDoc(sections 含 h2 + list/table)"""
    lines = text.splitlines()
    doc = ParsedDoc()
    i = 0
    current_section: Optional[Dict[str, Any]] = None

    while i < len(lines):
        line = lines[i].rstrip()
        m1 = H1_RE.match(line)
        m2 = H2_RE.match(line)
        if m1:
            doc.title = m1.group(1).strip()
            i += 1
            continue
        if m2:
            if current_section is not None:
                doc.sections.append(current_section)
            current_section = {"heading": m2.group(1).strip(), "items": [], "table": None}
            i += 1
            continue
        if current_section is None:
            i += 1
            continue
        # 表格
        if TABLE_ROW_RE.match(line) and i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i + 1]):
            headers, next_i = _parse_table_rows(lines, i)
            rows = []
            while next_i < len(lines) and TABLE_ROW_RE.match(lines[next_i]):
                cells = [c.strip() for c in lines[next_i].strip("|").split("|")]
                rows.append(dict(zip(headers, cells)))
                next_i += 1
            current_section["table"] = {"headers": headers, "rows": rows}
            i = next_i
            continue
        # 列表
        ml = LIST_RE.match(line)
        if ml:
            current_section["items"].append(ml.group(1).strip())
            i += 1
            continue
        i += 1

    if current_section is not None:
        doc.sections.append(current_section)
    return doc


# ---------- 适配器:把 ParsedDoc 转成 categories/brands ----------
def adapt_categories(doc: ParsedDoc, fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从 md sections 推断 categories。规则:h2 段名 = 类目名,list 项 = 子类名。
    若 sections 为空,使用 fallback。
    """
    if not doc.sections:
        return list(fallback)
    out: List[Dict[str, Any]] = []
    next_id = 1
    for sec in doc.sections:
        slug = re.sub(r"[^a-z0-9]+", "-", sec["heading"].lower()).strip("-")
        subs = [{"name": item} for item in sec.get("items", [])]
        # 表格情形:从 rows 中找 name 列
        if not subs and sec.get("table"):
            for row in sec["table"]["rows"]:
                name = row.get("name") or row.get("名称") or row.get("品类")
                if name:
                    subs.append({"name": name})
        out.append({
            "id": next_id,
            "name": sec["heading"],
            "slug": slug or f"cat-{next_id}",
            "priority": "P1",
            "subcategories": subs,
        })
        next_id += 1
    return out


def adapt_brands(doc: ParsedDoc, fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从 md sections 推断 brands。规则:每个 h2 = 一个品牌,table 中找 scores/positioning。
    若 sections 为空,使用 fallback。
    """
    if not doc.sections:
        return list(fallback)
    out: List[Dict[str, Any]] = []
    next_id = 1
    for sec in doc.sections:
        brand_name = sec["heading"]
        slug = re.sub(r"[^a-z0-9]+", "-", brand_name.lower()).strip("-")
        scores = {"quality": 0.0, "service": 0.0, "value": 0.0}
        positioning = None
        origin = None
        notes_parts: List[str] = []

        # 字段名 → 内部 key 的映射
        field_map = {
            "quality": ("质量", "quality"),
            "service": ("服务", "service"),
            "value": ("性价比", "value", "性价比评分"),
            "positioning": ("定位", "positioning"),
            "origin": ("产地", "origin", "国家"),
        }

        def _assign(internal_key: str, raw_value: str) -> None:
            nonlocal positioning, origin
            if internal_key == "positioning":
                positioning = raw_value
            elif internal_key == "origin":
                origin = raw_value
            else:
                try:
                    scores[internal_key] = float(raw_value)
                except ValueError:
                    pass

        if sec.get("table"):
            headers = sec["table"]["headers"]
            # 检测长表(行=维度)vs 宽表(列=维度)
            long_form = any(h in ("维度", "指标", "item", "key") for h in headers)
            for row in sec["table"]["rows"]:
                if long_form:
                    # 找到"维度/指标"列与对应"分数/值"列
                    dim_key = next((h for h in headers if h in ("维度", "指标", "item", "key")), None)
                    val_key = next((h for h in headers if h in ("分数", "值", "评分", "score", "value")), None)
                    if not dim_key or not val_key:
                        continue
                    dim = row.get(dim_key, "").strip()
                    val = row.get(val_key, "").strip()
                    for internal, aliases in field_map.items():
                        if any(alias in dim for alias in aliases):
                            _assign(internal, val)
                            break
                    else:
                        if val:
                            notes_parts.append(f"{dim}={val}")
                else:
                    # 宽表:列名 = 维度
                    for k, v in row.items():
                        for internal, aliases in field_map.items():
                            if any(alias in k for alias in aliases):
                                _assign(internal, v)
                                break
                        else:
                            if v:
                                notes_parts.append(f"{k}={v}")
        out.append({
            "id": next_id,
            "name": brand_name,
            "slug": slug or f"brand-{next_id}",
            "category_slug": "unknown",
            "origin": origin,
            "positioning": positioning,
            "scores": scores,
            "notes": "; ".join(notes_parts) or None,
        })
        next_id += 1
    return out


# ---------- 写文件 ----------
def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")


# ---------- 主流程 ----------
def run(use_fallback: bool, out_dir: Path) -> Tuple[int, int]:
    """执行解析 → 校验 → 写出。返回 (categories 数量, brands 数量)"""
    out_dir.mkdir(parents=True, exist_ok=True)

    # 解析 md(缺源文件时回退 fallback)
    cat_doc = ParsedDoc()
    brand_doc = ParsedDoc()
    if not use_fallback:
        if CATEGORY_MD.exists():
            cat_doc = parse_markdown(CATEGORY_MD.read_text(encoding="utf-8"))
        else:
            print(f"[warn] {CATEGORY_MD} 不存在,使用 fallback", file=sys.stderr)
        if BRAND_MD.exists():
            brand_doc = parse_markdown(BRAND_MD.read_text(encoding="utf-8"))
        else:
            print(f"[warn] {BRAND_MD} 不存在,使用 fallback", file=sys.stderr)

    categories = adapt_categories(cat_doc, FALLBACK_CATEGORIES)
    brands = adapt_brands(brand_doc, FALLBACK_BRANDS)

    # 校验
    validate_categories(categories)
    validate_brands(brands)

    # 写出
    write_json(out_dir / "categories.json", categories)
    write_json(out_dir / "brands.json", brands)
    return len(categories), len(brands)


def main() -> int:
    parser = argparse.ArgumentParser(description="md → JSON 转换器(ConsumptionAdvisor)")
    parser.add_argument("--fallback", action="store_true", help="强制使用内置 fallback")
    parser.add_argument("--out-dir", type=Path, default=DATA_DIR, help="输出目录")
    args = parser.parse_args()
    try:
        n_cat, n_brand = run(use_fallback=args.fallback, out_dir=args.out_dir)
    except SchemaError as e:
        print(f"[error] schema 校验失败: {e}", file=sys.stderr)
        return 1
    print(f"[ok] categories: {n_cat}, brands: {n_brand} → {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
