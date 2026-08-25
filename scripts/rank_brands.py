#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rank_brands.py — 品牌排行 CLI

按 综合分 = 0.4*质量 + 0.3*服务 + 0.3*性价比 排序,可按品类/定位过滤。
读 data/brands.json,输出 markdown 表格到 stdout。

用法:
  python3 scripts/rank_brands.py
  python3 scripts/rank_brands.py --category digital --top 5
  python3 scripts/rank_brands.py --category apparel --positioning value
  python3 scripts/rank_brands.py --all --top 10
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
BRANDS_PATH = ROOT / "data" / "brands.json"

# 综合分权重(质量优先,服务和性价比并重)
WEIGHTS = {
    "quality": 0.4,
    "service": 0.3,
    "value": 0.3,
}

# 品类 slug → 中文名
CATEGORY_LABELS = {
    "digital": "数码",
    "home-appliance": "家电",
    "apparel": "服饰",
    "beauty": "美妆",
    "maternal-infant": "母婴",
    "food": "食品",
    "home": "家居",
    "sports": "运动户外",
    "books": "图书教育",
    "health": "健康保健",
}

# 定位 → 中文
POSITION_LABELS = {
    "high-end": "高端",
    "mid": "中端",
    "entry": "入门",
    "value": "性价比",
}


def composite_score(brand: Dict[str, Any]) -> float:
    s = brand["scores"]
    return round(WEIGHTS["quality"] * s["quality"]
                 + WEIGHTS["service"] * s["service"]
                 + WEIGHTS["value"] * s["value"], 2)


def load_brands(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"brands.json 不存在: {path}  请先跑 seed_brands.py")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def filter_brands(brands: List[Dict[str, Any]],
                  category: str | None,
                  positioning: str | None) -> List[Dict[str, Any]]:
    out = brands
    if category:
        out = [b for b in out if b["category_slug"] == category]
    if positioning:
        out = [b for b in out if b["positioning"] == positioning]
    return out


def rank(brands: List[Dict[str, Any]], top: int) -> List[Dict[str, Any]]:
    return sorted(brands, key=lambda b: composite_score(b), reverse=True)[:top]


def render_markdown(brands: List[Dict[str, Any]],
                    category: str | None,
                    positioning: str | None) -> str:
    if not brands:
        return "_(无匹配品牌)_\n"

    title_parts = ["品牌排行"]
    if category:
        title_parts.append(f"品类={CATEGORY_LABELS.get(category, category)}")
    if positioning:
        title_parts.append(f"定位={POSITION_LABELS.get(positioning, positioning)}")
    title_parts.append(f"权重=质量{WEIGHTS['quality']}/服务{WEIGHTS['service']}/性价比{WEIGHTS['value']}")

    lines: List[str] = []
    lines.append("## " + " · ".join(title_parts))
    lines.append("")
    lines.append("| 排名 | 品牌 | 品类 | 定位 | 产地 | 质量 | 服务 | 性价比 | **综合分** | 备注 |")
    lines.append("|------|------|------|------|------|------|------|--------|-----------|------|")
    for i, b in enumerate(rank(brands, len(brands)), start=1):
        s = b["scores"]
        cat_label = CATEGORY_LABELS.get(b["category_slug"], b["category_slug"])
        pos_label = POSITION_LABELS.get(b["positioning"], b["positioning"])
        score = composite_score(b)
        notes = b.get("notes", "").replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {i} | {b['name']} | {cat_label} | {pos_label} | {b['origin']} "
            f"| {s['quality']} | {s['service']} | {s['value']} | **{score}** | {notes} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="品牌排行 CLI")
    parser.add_argument("--category", "-c", help="按品类过滤(英文 slug)")
    parser.add_argument("--positioning", "-p", help="按定位过滤(high-end/mid/entry/value)")
    parser.add_argument("--top", "-n", type=int, default=5, help="前 N 名(默认 5)")
    parser.add_argument("--all", action="store_true", help="忽略 --top,显示全部")
    parser.add_argument("--brands", type=Path, default=BRANDS_PATH, help="brands.json 路径")
    args = parser.parse_args()

    brands = load_brands(args.brands)
    filtered = filter_brands(brands, args.category, args.positioning)
    top = len(filtered) if args.all else min(args.top, len(filtered))

    print(render_markdown(filtered, args.category, args.positioning) if args.all
          else render_markdown(rank(filtered, top), args.category, args.positioning))
    print(f"\n_共 {len(filtered)} 个匹配品牌,展示前 {top} 个_")
    return 0


if __name__ == "__main__":
    sys.exit(main())
