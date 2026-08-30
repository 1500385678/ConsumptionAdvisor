#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
decision_helper.py — 决策辅助 CLI(飞书 Bot "消费决策"对话流程的预演版)

按 3 步反问 → Top 3 推荐,辅助用户理清"该不该买 / 买哪个 / 什么价位"。
读 data/categories.json + data/brands.json,输出 markdown 表格到 stdout。

3 步反问:
  1) 是真需要还是想要?(--need/--want 显式回答,避免模糊)
  2) 哪个品类?(--category 必填,从 categories.json 选)
  3) 价位定位?(--positioning high-end/mid/value)

输出:
  - Top 3 推荐品牌(按综合分排序)
  - 品类决策倾向(decision_bias,来自 categories.json)
  - 长值/性价比提示
  - "是否值得"评分(1-5)

用法:
  python3 scripts/decision_helper.py --category digital --positioning mid --need
  python3 scripts/decision_helper.py --category apparel --positioning value --want
  python3 scripts/decision_helper.py --category home-appliance --positioning high-end --need --top 5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
BRANDS_PATH = DATA_DIR / "brands.json"
CATEGORIES_PATH = DATA_DIR / "categories.json"

# 综合分权重(与 rank_brands.py 对齐:质量优先,服务和性价比并重)
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
    """综合分 = 0.4*质量 + 0.3*服务 + 0.3*性价比"""
    s = brand["scores"]
    return round(WEIGHTS["quality"] * s["quality"]
                 + WEIGHTS["service"] * s["service"]
                 + WEIGHTS["value"] * s["value"], 2)


def load_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"{path.name} 不存在,请先跑 seed_brands.py / md_to_json.py")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def filter_brands(brands: List[Dict[str, Any]],
                  category: str,
                  positioning: Optional[str]) -> List[Dict[str, Any]]:
    out = [b for b in brands if b["category_slug"] == category]
    if positioning:
        out = [b for b in out if b["positioning"] == positioning]
    return out


def rank(brands: List[Dict[str, Any]], top: int) -> List[Dict[str, Any]]:
    return sorted(brands, key=composite_score, reverse=True)[:top]


def worth_score(category: Dict[str, Any], need_flag: bool,
                positioning: Optional[str]) -> int:
    """
    "是否值得"评分(1-5),启发式:
    - 想要 → 1(劝退,除非你能再举证必要性)
    - 真需要 + P0 → 5(刚需要做)
    - 真需要 + P1 → 4(值得认真看)
    - 真需要 + P2 → 3(边界,先确认频次)
    - 显式选了定位 → 不影响分数,但说明用户想清楚预算
    """
    if not need_flag:
        return 1
    priority = category.get("priority", "P1")
    return {"P0": 5, "P1": 4, "P2": 3}.get(priority, 3)


def render(need_flag: bool,
           category: Dict[str, Any],
           positioning: Optional[str],
           top_brands: List[Dict[str, Any]],
           worth: int) -> str:
    cat_label = CATEGORY_LABELS.get(category["slug"], category["slug"])
    pos_label = POSITION_LABELS.get(positioning, "不限") if positioning else "不限"
    need_label = "真需要" if need_flag else "只是想要"

    lines: List[str] = []
    lines.append("## 决策辅助报告")
    lines.append("")
    lines.append(f"- **品类**:{cat_label} (优先级 {category.get('priority', '?')})")
    lines.append(f"- **目的**:{need_label}")
    lines.append(f"- **价位定位**:{pos_label}")
    lines.append(f"- **品类决策倾向**:`{category.get('decision_bias', '?')}`")
    lines.append(f"- **综合值得分**:**{worth} / 5**")
    lines.append("")
    if worth >= 4:
        lines.append("> ✅ 值得认真考虑;在 Top 3 里挑一个**预算够且服务能到**的即可。")
    elif worth == 3:
        lines.append("> ⚖️ 边界情况,先确认使用频次;若 < 每周 1 次,延后 30 天再决定。")
    else:
        lines.append("> 🛑 看起来是「想要」驱动;若非真需要,建议**跳过或加入 30 天观察清单**。")
    lines.append("")

    if not top_brands:
        lines.append("_(该品类/定位下无匹配品牌 — 可放宽定位或换个品类)_\n")
        return "\n".join(lines)

    lines.append("### Top 推荐")
    lines.append("")
    lines.append("| 排名 | 品牌 | 定位 | 产地 | 质量 | 服务 | 性价比 | **综合分** | 备注 |")
    lines.append("|------|------|------|------|------|------|--------|-----------|------|")
    for i, b in enumerate(top_brands, start=1):
        s = b["scores"]
        notes = b.get("notes", "").replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {i} | {b['name']} | {POSITION_LABELS.get(b['positioning'], b['positioning'])} "
            f"| {b['origin']} | {s['quality']} | {s['service']} | {s['value']} "
            f"| **{composite_score(b)}** | {notes} |"
        )
    lines.append("")
    lines.append("_评分权重:质量 0.4 / 服务 0.3 / 性价比 0.3;数据来源 brands.json_")
    return "\n".join(lines) + "\n"


def decide(categories: List[Dict[str, Any]],
           brands: List[Dict[str, Any]],
           category_slug: str,
           positioning: Optional[str],
           need_flag: bool,
           top: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]], int]:
    category = next((c for c in categories if c["slug"] == category_slug), None)
    if category is None:
        valid = ", ".join(sorted(c["slug"] for c in categories))
        raise SystemExit(f"未知品类: {category_slug}\n可选: {valid}")
    filtered = filter_brands(brands, category_slug, positioning)
    top_brands = rank(filtered, top)
    worth = worth_score(category, need_flag, positioning)
    return category, top_brands, worth


def main() -> int:
    parser = argparse.ArgumentParser(description="决策辅助 CLI")
    parser.add_argument("--category", "-c", required=True,
                        help="品类 slug(必填,digital/apparel/...)")
    parser.add_argument("--positioning", "-p",
                        choices=["high-end", "mid", "entry", "value"],
                        help="价位定位(不传则不限)")
    parser.add_argument("--need", action="store_true",
                        help="标记为「真需要」(否则视为「只是想要」)")
    parser.add_argument("--want", action="store_true",
                        help="显式标记为「只是想要」(覆盖 --need)")
    parser.add_argument("--top", "-n", type=int, default=3,
                        help="Top N(默认 3)")
    parser.add_argument("--brands", type=Path, default=BRANDS_PATH)
    parser.add_argument("--categories", type=Path, default=CATEGORIES_PATH)
    args = parser.parse_args()

    need_flag = args.need and not args.want
    brands = load_json(args.brands)
    categories = load_json(args.categories)
    category, top_brands, worth = decide(
        categories, brands, args.category, args.positioning, need_flag, args.top
    )
    print(render(need_flag, category, args.positioning, top_brands, worth))
    return 0


if __name__ == "__main__":
    sys.exit(main())
