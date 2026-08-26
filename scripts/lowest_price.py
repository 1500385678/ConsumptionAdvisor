#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lowest_price.py — 30 天最低价 + 虚假折扣检测

为 ConsumptionAdvisor 数据层提供:
  1. 滚动 30 天最低价计算(按 SKU × 平台聚合)
  2. 虚假折扣识别:当前"促销价"看似折扣大,但相对历史中位数 / 标准差 并未真便宜
  3. 跨平台最低价:同一 SKU 哪平台当前最低
  4. JSON 报告输出,供 Web App / 飞书 Bot 调用

设计要点:
  1. 输入是 price_snapshots 列表,每条 {product_id, platform, price, original_price?, date}
     - 无 original_price 视为无促销标牌,只算最低价
     - 缺日期则按 ISO YYYY-MM-DD 解析
  2. "30 天最低"= 滚动窗口内(含当天)最低成交价,跨平台取 min
  3. "虚假折扣"启发式(三选一命中即标记):
     (a) 当前价 > 历史中位数 × 1.10(看似促销,实际比平时贵)
     (b) 原价(original_price) > 历史最高价 × 1.20(原价虚标,涨上去再打折)
     (c) 折扣率(deep_discount)= (原价 - 当前价) / 原价 > 0.5 但 30 天最低价 > 当前价 × 1.05
         (说明历史从未跌到当前价附近,"5 折"是烟雾弹)
  4. CLI 输出 markdown 表格 + 可选 JSON 报告

用法:
  python3 scripts/lowest_price.py --input data/prices.example.json
  python3 scripts/lowest_price.py --input data/prices.example.json --days 60
  python3 scripts/lowest_price.py --input data/prices.example.json --report-out data/lowest_report.json
  python3 scripts/lowest_price.py --input data/prices.example.json --product P001
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data" / "prices.example.json"
DEFAULT_REPORT = ROOT / "data" / "lowest_report.json"

# 平台 → 中文标签
PLATFORM_LABELS = {
    "jd": "京东",
    "taobao": "淘宝",
    "pdd": "拼多多",
    "douyin": "抖音",
    "vipshop": "唯品会",
    "offline": "线下",
}

# 折扣启发式阈值(可调,见模块 docstring)
FAKE_DISCOUNT_OVERPRICE_RATIO = 1.10   # 当前价 / 历史中位数 > 此值 → 虚假
FAKE_DISCOUNT_ORIGINAL_BLOAT = 1.20    # 原价 / 历史最高价 > 此值 → 原价虚标
FAKE_DISCOUNT_DEEP_CUT = 0.5           # 折扣率 > 50% 但 30 天最低 > 当前价 × 1.05 → 烟雾弹


# ---------- 输入加载 ----------
def load_snapshots(path: Path) -> List[Dict[str, Any]]:
    """读 price_snapshots JSON list。每条至少含 product_id / platform / price / date。"""
    if not path.exists():
        raise SystemExit(f"价格快照文件不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise SystemExit(f"价格快照必须是 JSON list,实际 {type(data).__name__}")
    for i, s in enumerate(data):
        for key in ("product_id", "platform", "price", "date"):
            if key not in s:
                raise SystemExit(f"快照 #{i} 缺字段: {key}")
        if not isinstance(s["price"], (int, float)) or s["price"] <= 0:
            raise SystemExit(f"快照 #{i} price 非法: {s['price']}")
    return data


def parse_date(s: str) -> date:
    """YYYY-MM-DD → date。"""
    return datetime.strptime(s, "%Y-%m-%d").date()


# ---------- 聚合 / 计算 ----------
def filter_window(snapshots: List[Dict[str, Any]], asof: date, days: int) -> List[Dict[str, Any]]:
    """返回 asof 当天及之前 days 天内的快照(含 asof 当天)。"""
    cutoff = asof - timedelta(days=days - 1)
    out = []
    for s in snapshots:
        d = parse_date(s["date"])
        if cutoff <= d <= asof:
            out.append(s)
    return out


def group_by_product(snapshots: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """按 product_id 聚合。"""
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for s in snapshots:
        groups[s["product_id"]].append(s)
    return groups


def group_by_product_platform(snapshots: List[Dict[str, Any]]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    """按 (product_id, platform) 聚合。"""
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for s in snapshots:
        groups[(s["product_id"], s["platform"])] = s  # 最新覆盖即可,但先全收
    return groups


def lowest_in_window(snapshots: List[Dict[str, Any]],
                     exclude_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """返回窗口内价格最低的那条快照。exclude_date 不参与比较(用于"前 30 天最低")。"""
    if not snapshots:
        return None
    if exclude_date is not None:
        snapshots = [s for s in snapshots if parse_date(s["date"]) != exclude_date]
        if not snapshots:
            return None
    return min(snapshots, key=lambda s: s["price"])


def current_price(snapshots: List[Dict[str, Any]], asof: date) -> Optional[Dict[str, Any]]:
    """asof 当天该 SKU 的价格(若无当日,取最近一次;再无则 None)。"""
    if not snapshots:
        return None
    same_day = [s for s in snapshots if parse_date(s["date"]) == asof]
    if same_day:
        return min(same_day, key=lambda s: s["price"])
    prior = [s for s in snapshots if parse_date(s["date"]) <= asof]
    if not prior:
        return None
    most_recent = max(prior, key=lambda s: parse_date(s["date"]))
    return most_recent


# ---------- 虚假折扣检测 ----------
def detect_fake_discount(product_snapshots: List[Dict[str, Any]],
                         current: Dict[str, Any],
                         lowest_30d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    返回虚假折扣诊断 dict,或 None(无嫌疑)。
    见模块 docstring 的三条启发式。
    """
    prices = [s["price"] for s in product_snapshots]
    if len(prices) < 3:
        return None  # 样本太少,不下结论

    median = statistics.median(prices)
    hist_max = max(prices)
    cur_price = current["price"]
    orig_price = current.get("original_price")

    # 启发式 (a):当前价 > 历史中位数 × 1.10
    if median > 0 and cur_price / median > FAKE_DISCOUNT_OVERPRICE_RATIO:
        return {
            "kind": "overprice_in_disguise",
            "current_price": cur_price,
            "historical_median": round(median, 2),
            "ratio": round(cur_price / median, 3),
            "threshold": FAKE_DISCOUNT_OVERPRICE_RATIO,
            "message": f"当前价 ¥{cur_price:.2f} 比历史中位数 ¥{median:.2f} 高 {((cur_price / median - 1) * 100):.1f}%,疑似先涨后降",
        }

    # 启发式 (b):原价 > 历史最高价 × 1.20
    if orig_price and hist_max > 0 and orig_price / hist_max > FAKE_DISCOUNT_ORIGINAL_BLOAT:
        return {
            "kind": "inflated_original_price",
            "original_price": orig_price,
            "historical_max": hist_max,
            "ratio": round(orig_price / hist_max, 3),
            "threshold": FAKE_DISCOUNT_ORIGINAL_BLOAT,
            "message": f"挂牌原价 ¥{orig_price:.2f} 比历史最高 ¥{hist_max:.2f} 高 {((orig_price / hist_max - 1) * 100):.1f}%,原价虚标",
        }

    # 启发式 (c):大折扣率 + 历史最低仍高于当前
    if orig_price and orig_price > 0:
        cut_rate = (orig_price - cur_price) / orig_price
        if cut_rate > FAKE_DISCOUNT_DEEP_CUT and lowest_30d and lowest_30d["price"] > cur_price * 1.05:
            return {
                "kind": "smokescreen_discount",
                "original_price": orig_price,
                "current_price": cur_price,
                "displayed_cut_rate": round(cut_rate, 3),
                "lowest_30d_price": lowest_30d["price"],
                "message": f"标 {cut_rate * 100:.0f}% 折扣,但 30 天内从未跌到此价(最低 ¥{lowest_30d['price']:.2f})",
            }

    return None


# ---------- 报告生成 ----------
def build_product_report(product_id: str,
                         all_snapshots: List[Dict[str, Any]],
                         asof: date,
                         days: int) -> Dict[str, Any]:
    """生成单个 SKU 的报告段。"""
    in_window = filter_window(all_snapshots, asof, days)
    lowest = lowest_in_window(in_window)  # 含 day 0:真实 30 天最低(可能 = 当前)
    # 前 30 天最低(不含 day 0):用于虚假折扣启发式 (c) 判定"历史是否到此价"
    prior_lowest = lowest_in_window(in_window, exclude_date=asof)
    current = current_price(all_snapshots, asof)
    platforms_today: Dict[str, float] = {}
    for s in in_window:
        if parse_date(s["date"]) == asof:
            cur = platforms_today.get(s["platform"])
            if cur is None or s["price"] < cur:
                platforms_today[s["platform"]] = s["price"]

    # 跨平台最低:取 asof 当日(无当日则取窗口末次)
    cross_platform: Optional[Dict[str, Any]] = None
    if platforms_today:
        platform, price = min(platforms_today.items(), key=lambda kv: kv[1])
        cross_platform = {"platform": platform, "price": price}

    fake = None
    if current and lowest:
        # 启发式 (c) 用"前 30 天最低(不含 day 0)"判定历史是否到过此价
        fake = detect_fake_discount(in_window, current, prior_lowest or lowest)

    return {
        "product_id": product_id,
        "asof": asof.isoformat(),
        "window_days": days,
        "snapshot_count_in_window": len(in_window),
        "current_price": current["price"] if current else None,
        "current_platform": current["platform"] if current else None,
        "lowest_30d": {
            "price": lowest["price"],
            "platform": lowest["platform"],
            "date": lowest["date"],
        } if lowest else None,
        "cross_platform_today": cross_platform,
        "fake_discount": fake,
    }


def build_full_report(snapshots: List[Dict[str, Any]],
                      asof: Optional[date] = None,
                      days: int = 30,
                      product_filter: Optional[str] = None) -> Dict[str, Any]:
    """生成完整报告 dict。"""
    if asof is None:
        asof = max(parse_date(s["date"]) for s in snapshots)

    grouped = group_by_product(snapshots)
    if product_filter:
        grouped = {k: v for k, v in grouped.items() if k == product_filter}

    products = [build_product_report(pid, snaps, asof, days) for pid, snaps in sorted(grouped.items())]
    flagged = [p for p in products if p["fake_discount"]]

    return {
        "meta": {
            "asof": asof.isoformat(),
            "window_days": days,
            "total_snapshots": len(snapshots),
            "products_analyzed": len(products),
            "fake_discount_flagged": len(flagged),
        },
        "products": products,
        "flagged_products": [p["product_id"] for p in flagged],
    }


# ---------- 渲染 ----------
def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    lines: List[str] = []
    lines.append(f"## 价格报告 · asof {meta['asof']} · {meta['window_days']} 天窗口")
    lines.append("")
    lines.append(f"快照总数: {meta['total_snapshots']} · 涉及 SKU: {meta['products_analyzed']} · 虚假折扣嫌疑: **{meta['fake_discount_flagged']}**")
    lines.append("")
    if not report["products"]:
        lines.append("_(无数据)_")
        return "\n".join(lines) + "\n"

    lines.append("| SKU | 当前价 | 30 天最低(平台/日期) | 跨平台当日最低 | 折扣嫌疑 |")
    lines.append("|-----|--------|----------------------|----------------|----------|")
    for p in report["products"]:
        cur = f"¥{p['current_price']:.2f}" if p["current_price"] is not None else "—"
        plat = PLATFORM_LABELS.get(p["current_platform"], p["current_platform"]) if p["current_platform"] else "—"
        cur = f"{cur} ({plat})"
        if p["lowest_30d"]:
            lp = PLATFORM_LABELS.get(p["lowest_30d"]["platform"], p["lowest_30d"]["platform"])
            low = f"¥{p['lowest_30d']['price']:.2f} ({lp} {p['lowest_30d']['date']})"
        else:
            low = "—"
        if p["cross_platform_today"]:
            cp = PLATFORM_LABELS.get(p["cross_platform_today"]["platform"], p["cross_platform_today"]["platform"])
            cross = f"¥{p['cross_platform_today']['price']:.2f} ({cp})"
        else:
            cross = "—"
        flag = "🚩 " + p["fake_discount"]["kind"] if p["fake_discount"] else "✅"
        lines.append(f"| {p['product_id']} | {cur} | {low} | {cross} | {flag} |")
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------- 主流程 ----------
def main() -> int:
    parser = argparse.ArgumentParser(description="30 天最低价 + 虚假折扣检测")
    parser.add_argument("--input", "-i", type=Path, default=DEFAULT_INPUT,
                        help=f"价格快照 JSON 路径(默认 {DEFAULT_INPUT.relative_to(ROOT)})")
    parser.add_argument("--days", "-d", type=int, default=30, help="窗口天数(默认 30)")
    parser.add_argument("--asof", type=str, default=None,
                        help="asof 日期 YYYY-MM-DD(默认取快照最大日期)")
    parser.add_argument("--product", "-p", type=str, default=None, help="只看某个 SKU")
    parser.add_argument("--report-out", "-o", type=Path, default=None,
                        help=f"把 JSON 报告写到这里(默认不写)")
    parser.add_argument("--json", action="store_true", help="stdout 直接打 JSON 报告")
    args = parser.parse_args()

    snapshots = load_snapshots(args.input)
    asof = parse_date(args.asof) if args.asof else None
    report = build_full_report(snapshots, asof=asof, days=args.days, product_filter=args.product)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))

    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        with args.report_out.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"[ok] wrote report → {args.report_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
