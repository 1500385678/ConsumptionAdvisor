#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_price_history.py — 历史价格快照导入器

为 ConsumptionAdvisor 数据层提供:
  1. 读取 price_snapshots 列表(每条 {product_id, platform, price, original_price?, date})
  2. 字段校验:product_id / platform / price / date 必填,缺一即报错并跳过该条
  3. 按 product_id 分组,组内按 date 升序排序
  4. 去重:(product_id, platform, date, price) 四元组相同视为重复
  5. 输出归一化历史价 data/price_history.json:
     {
       "meta": {snapshot_count, sku_count, generated_at, source},
       "products": {
         "P001": {
           "snapshots": [...],                # 已按 date 升序
           "stats": {count, date_min, date_max, platforms, min_price, max_price}
         },
         ...
       }
     }
  6. CLI --stats:每 SKU 摘要表(快照数 / 平台 / 起止日期 / 最低 / 最高)

设计要点:
  - 与 lowest_price.py 解耦:本脚本只做"归一化入库",不计算 30 天最低或折扣
  - 校验失败不静默:错误计数 + 跳过 + 退出码 0(主流程)但 stderr 报警告
  - 缺 original_price 视为"无促销标牌",不参与折扣率计算

用法:
  python3 scripts/import_price_history.py
  python3 scripts/import_price_history.py --input data/prices.example.json
  python3 scripts/import_price_history.py --input data/prices.example.json --output data/price_history.json
  python3 scripts/import_price_history.py --stats
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 仓库根目录(脚本父级的父级)
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "data" / "prices.example.json"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "price_history.json"

# 必填字段
REQUIRED_FIELDS = ("product_id", "platform", "price", "date")
# 平台白名单(常见电商,用于数据质量提示;不在白名单仍接受但标 warn)
KNOWN_PLATFORMS = {"jd", "taobao", "pdd", "douyin", "vipshop", "offline", "suning", "amazon", "lululemon-flagship"}


def validate_snapshot(snap: Any, idx: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """校验单条快照,返回 (clean_snap, error_msg)。error_msg 非空即丢弃该条。"""
    if not isinstance(snap, dict):
        return None, f"[{idx}] not a dict"
    for field in REQUIRED_FIELDS:
        if field not in snap or snap[field] in (None, ""):
            return None, f"[{idx}] missing required field: {field}"
    pid = str(snap["product_id"]).strip()
    platform = str(snap["platform"]).strip().lower()
    if not platform:
        return None, f"[{idx}] empty platform"
    # 平台不强制白名单(线下/品牌官方店等长尾值允许),仅日志提示
    if platform not in KNOWN_PLATFORMS:
        print(f"[info] non-standard platform accepted: {platform}", file=sys.stderr)
    try:
        price = float(snap["price"])
        if price <= 0:
            return None, f"[{idx}] non-positive price: {price}"
    except (TypeError, ValueError):
        return None, f"[{idx}] non-numeric price: {snap['price']!r}"
    try:
        # 校验日期格式
        datetime.strptime(str(snap["date"]), "%Y-%m-%d")
    except (TypeError, ValueError):
        return None, f"[{idx}] invalid date (expect YYYY-MM-DD): {snap['date']!r}"
    original_price: Optional[float] = None
    if snap.get("original_price") is not None:
        try:
            original_price = float(snap["original_price"])
            if original_price <= 0:
                original_price = None  # 无效原价当作没标
        except (TypeError, ValueError):
            original_price = None
    return {
        "product_id": pid,
        "platform": platform,
        "price": price,
        "original_price": original_price,
        "date": str(snap["date"]),
    }, None


def import_snapshots(snapshots: List[Any]) -> Tuple[Dict[str, List[Dict[str, Any]]], int]:
    """分组 + 排序 + 去重,返回 ({product_id: [snapshots]}, dropped_count)。"""
    errors: List[str] = []
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for idx, raw in enumerate(snapshots):
        clean, err = validate_snapshot(raw, idx)
        if err:
            errors.append(err)
            continue
        grouped[clean["product_id"]].append(clean)  # type: ignore[arg-type]
    if errors:
        for line in errors:
            print(f"[warn] {line}", file=sys.stderr)
    # 排序 + 去重
    for pid in grouped:
        grouped[pid].sort(key=lambda s: s["date"])
        seen = set()
        unique: List[Dict[str, Any]] = []
        for s in grouped[pid]:
            key = (s["platform"], s["date"], s["price"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(s)
        grouped[pid] = unique
    return dict(grouped), len(errors)


def build_product_stats(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """单 SKU 摘要:count / date_min / date_max / platforms / min / max。"""
    if not snapshots:
        return {"count": 0}
    prices = [s["price"] for s in snapshots]
    platforms = Counter(s["platform"] for s in snapshots)
    return {
        "count": len(snapshots),
        "date_min": snapshots[0]["date"],
        "date_max": snapshots[-1]["date"],
        "platforms": dict(platforms),
        "min_price": min(prices),
        "max_price": max(prices),
    }


def build_output(grouped: Dict[str, List[Dict[str, Any]]], source: str) -> Dict[str, Any]:
    """构造归一化输出 dict。"""
    products: Dict[str, Dict[str, Any]] = {}
    for pid, snaps in grouped.items():
        products[pid] = {
            "snapshots": snaps,
            "stats": build_product_stats(snaps),
        }
    total = sum(len(snaps) for snaps in grouped.values())
    return {
        "meta": {
            "snapshot_count": total,
            "sku_count": len(grouped),
            "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "source": source,
        },
        "products": products,
    }


def print_stats(output: Dict[str, Any]) -> None:
    """CLI --stats:打印每个 SKU 摘要表。"""
    print(f"# 历史价导入摘要\n")
    print(f"- 快照总数:{output['meta']['snapshot_count']}")
    print(f"- SKU 数:{output['meta']['sku_count']}")
    print(f"- 来源:{output['meta']['source']}")
    print(f"- 生成时间:{output['meta']['generated_at']}\n")
    print("| SKU | 快照 | 起 | 止 | 平台 | 最低 | 最高 |")
    print("|-----|------|----|----|------|------|------|")
    for pid in sorted(output["products"]):
        p = output["products"][pid]
        s = p["stats"]
        platforms_str = "/".join(sorted(s["platforms"].keys()))
        print(
            f"| {pid} | {s['count']} | {s['date_min']} | {s['date_max']} | "
            f"{platforms_str} | ¥{s['min_price']:.0f} | ¥{s['max_price']:.0f} |"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="导入并归一化历史价格快照")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                        help=f"输入快照 JSON(默认:{DEFAULT_INPUT.name})")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help=f"输出归一化 JSON(默认:{DEFAULT_OUTPUT.name})")
    parser.add_argument("--stats", action="store_true", help="打印每 SKU 摘要表")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"[error] input not found: {args.input}", file=sys.stderr)
        return 1
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[error] invalid JSON in {args.input}: {e}", file=sys.stderr)
        return 1
    if not isinstance(raw, list):
        print(f"[error] expected JSON array, got {type(raw).__name__}", file=sys.stderr)
        return 1

    grouped, dropped = import_snapshots(raw)
    if dropped:
        print(f"[warn] dropped {dropped} invalid snapshots", file=sys.stderr)
    output = build_output(grouped, source=str(args.input.name))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[ok] imported {output['meta']['snapshot_count']} snapshots "
          f"across {output['meta']['sku_count']} SKUs → {args.output}")
    if args.stats:
        print_stats(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
