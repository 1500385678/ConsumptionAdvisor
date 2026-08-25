#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
seed_brands.py — 品牌种子数据(50+ 主流品牌)

为 ConsumptionAdvisor 数据层回填 50+ 品牌,覆盖 10 大品类核心 SKU。
质量/服务/性价比三维度评分(0-5),支持 schema 校验。

设计要点:
  1. BRANDS 表是 single source of truth,改完直接重跑脚本即覆盖 brands.json
  2. id 唯一,name+slug 在同一 category_slug 内不重复(跨品类允许同名,如 Nike 同时在服饰/运动)
  3. 写出 JSON 之前做 schema 校验,失败抛错并定位
  4. CLI:python3 scripts/seed_brands.py [--out data/brands.json] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    import jsonschema
except ImportError:  # 允许离线场景:无 jsonschema 时跳过严格校验,只做基础检查
    jsonschema = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SCHEMA_PATH = DATA_DIR / "schema.json"
BRANDS_OUT = DATA_DIR / "brands.json"


# ---------- 品牌种子数据(54 条) ----------
# 字段:id / name / slug / category_slug / origin / positioning / quality / service / value / notes
# positioning ∈ {high-end, mid, entry, value}
# quality/service/value ∈ [0, 5]
BRANDS: List[Dict[str, Any]] = [
    # ===== 数码 digital (7) =====
    {"id": 1,  "name": "Apple",      "slug": "apple",      "category_slug": "digital", "origin": "美国",   "positioning": "high-end", "quality": 4.8, "service": 4.2, "value": 3.5, "notes": "生态闭环强,保值率中等"},
    {"id": 2,  "name": "小米",       "slug": "xiaomi",     "category_slug": "digital", "origin": "中国",   "positioning": "value",    "quality": 4.0, "service": 3.5, "value": 4.6, "notes": "性价比标杆"},
    {"id": 6,  "name": "华为",       "slug": "huawei",     "category_slug": "digital", "origin": "中国",   "positioning": "mid",      "quality": 4.4, "service": 3.8, "value": 4.0, "notes": "自研芯片+鸿蒙生态"},
    {"id": 7,  "name": "三星",       "slug": "samsung",    "category_slug": "digital", "origin": "韩国",   "positioning": "high-end", "quality": 4.5, "service": 3.6, "value": 3.5, "notes": "屏幕+存储优势,折叠屏第一梯队"},
    {"id": 8,  "name": "OPPO",       "slug": "oppo",       "category_slug": "digital", "origin": "中国",   "positioning": "mid",      "quality": 4.0, "service": 3.7, "value": 4.1, "notes": "快充+影像中端价位优选"},
    {"id": 9,  "name": "vivo",       "slug": "vivo",       "category_slug": "digital", "origin": "中国",   "positioning": "mid",      "quality": 4.0, "service": 3.7, "value": 4.1, "notes": "与 OPPO 同源,主打影像差异化"},
    {"id": 10, "name": "索尼",       "slug": "sony",       "category_slug": "digital", "origin": "日本",   "positioning": "high-end", "quality": 4.7, "service": 3.8, "value": 3.4, "notes": "影音/传感器壁垒高,溢价明显"},

    # ===== 家电 home-appliance (7) =====
    {"id": 3,  "name": "美的",       "slug": "midea",      "category_slug": "home-appliance", "origin": "中国",   "positioning": "mid",      "quality": 4.2, "service": 4.0, "value": 4.3, "notes": "国民家电,售后覆盖广"},
    {"id": 4,  "name": "戴森",       "slug": "dyson",      "category_slug": "home-appliance", "origin": "英国",   "positioning": "high-end", "quality": 4.6, "service": 3.5, "value": 3.2, "notes": "高端定位,溢价明显"},
    {"id": 11, "name": "格力",       "slug": "gree",       "category_slug": "home-appliance", "origin": "中国",   "positioning": "mid",      "quality": 4.3, "service": 3.8, "value": 4.2, "notes": "空调技术深,售后中等"},
    {"id": 12, "name": "海尔",       "slug": "haier",      "category_slug": "home-appliance", "origin": "中国",   "positioning": "mid",      "quality": 4.1, "service": 4.0, "value": 4.2, "notes": "白电覆盖广,服务网点密"},
    {"id": 13, "name": "西门子",     "slug": "siemens",    "category_slug": "home-appliance", "origin": "德国",   "positioning": "high-end", "quality": 4.5, "service": 3.8, "value": 3.6, "notes": "嵌入式厨电德系工艺"},
    {"id": 14, "name": "松下",       "slug": "panasonic",  "category_slug": "home-appliance", "origin": "日本",   "positioning": "mid",      "quality": 4.3, "service": 3.8, "value": 4.0, "notes": "日系耐用,小家电口碑稳"},
    {"id": 15, "name": "老板",       "slug": "robam",      "category_slug": "home-appliance", "origin": "中国",   "positioning": "mid",      "quality": 4.2, "service": 3.7, "value": 4.0, "notes": "抽油烟机+灶具专精"},

    # ===== 服饰 apparel (6) =====
    {"id": 5,  "name": "Lululemon",  "slug": "lululemon",  "category_slug": "apparel",        "origin": "加拿大", "positioning": "high-end", "quality": 4.5, "service": 3.8, "value": 3.4, "notes": "瑜伽裤标杆,二手保值"},
    {"id": 16, "name": "优衣库",     "slug": "uniqlo",     "category_slug": "apparel",        "origin": "日本",   "positioning": "value",    "quality": 4.2, "service": 4.0, "value": 4.5, "notes": "基本款之王,面料迭代快"},
    {"id": 17, "name": "Nike",       "slug": "nike",       "category_slug": "apparel",        "origin": "美国",   "positioning": "mid",      "quality": 4.3, "service": 3.7, "value": 3.8, "notes": "运动+潮流双线,折扣季性价比优"},
    {"id": 18, "name": "Adidas",     "slug": "adidas",     "category_slug": "apparel",        "origin": "德国",   "positioning": "mid",      "quality": 4.2, "service": 3.7, "value": 3.9, "notes": "三叶草系列溢价,主线性价比中"},
    {"id": 19, "name": "Ubras",      "slug": "ubras",      "category_slug": "apparel",        "origin": "中国",   "positioning": "value",    "quality": 4.0, "service": 3.5, "value": 4.4, "notes": "无尺码内衣开创者"},
    {"id": 20, "name": "蕉内",       "slug": "bananain",   "category_slug": "apparel",        "origin": "中国",   "positioning": "value",    "quality": 4.0, "service": 3.6, "value": 4.3, "notes": "体感无尺码,年轻定位"},

    # ===== 美妆 beauty (6) =====
    {"id": 21, "name": "雅诗兰黛",   "slug": "estee-lauder", "category_slug": "beauty",      "origin": "美国",   "positioning": "high-end", "quality": 4.5, "service": 4.0, "value": 3.5, "notes": "小棕瓶+白金线抗老口碑"},
    {"id": 22, "name": "兰蔻",       "slug": "lancome",    "category_slug": "beauty",         "origin": "法国",   "positioning": "high-end", "quality": 4.5, "service": 4.0, "value": 3.5, "notes": "菁纯+小黑瓶双旗舰"},
    {"id": 23, "name": "SK-II",      "slug": "sk-ii",      "category_slug": "beauty",         "origin": "日本",   "positioning": "high-end", "quality": 4.7, "service": 3.8, "value": 3.2, "notes": "Pitera 成分壁垒,价格坚挺"},
    {"id": 24, "name": "资生堂",     "slug": "shiseido",   "category_slug": "beauty",         "origin": "日本",   "positioning": "high-end", "quality": 4.4, "service": 3.8, "value": 3.6, "notes": "红腰子精华+时光琉璃"},
    {"id": 25, "name": "完美日记",   "slug": "perfect-diary","category_slug": "beauty",       "origin": "中国",   "positioning": "value",    "quality": 3.8, "service": 3.3, "value": 4.5, "notes": "彩妆新国货,学生党友好"},
    {"id": 26, "name": "雅漾",       "slug": "avene",      "category_slug": "beauty",         "origin": "法国",   "positioning": "mid",      "quality": 4.2, "service": 3.7, "value": 4.0, "notes": "敏感肌专研,温泉水基底"},

    # ===== 母婴 maternal-infant (6) =====
    {"id": 27, "name": "爱他美",     "slug": "aptamil",    "category_slug": "maternal-infant", "origin": "德国",  "positioning": "high-end", "quality": 4.6, "service": 3.8, "value": 3.6, "notes": "奶粉第一梯队,版本多"},
    {"id": 28, "name": "飞鹤",       "slug": "feihe",      "category_slug": "maternal-infant", "origin": "中国",  "positioning": "mid",      "quality": 4.3, "service": 3.7, "value": 4.0, "notes": "国产奶粉龙头,星飞帆系列"},
    {"id": 29, "name": "帮宝适",     "slug": "pampers",    "category_slug": "maternal-infant", "origin": "美国",  "positioning": "mid",      "quality": 4.2, "service": 3.8, "value": 4.0, "notes": "纸尿裤全球第一品牌"},
    {"id": 30, "name": "好奇",       "slug": "huggies",    "category_slug": "maternal-infant", "origin": "美国",  "positioning": "mid",      "quality": 4.2, "service": 3.8, "value": 4.0, "notes": "金装/铂金装分线"},
    {"id": 31, "name": "Babycare",   "slug": "babycare",   "category_slug": "maternal-infant", "origin": "中国",  "positioning": "mid",      "quality": 4.1, "service": 3.7, "value": 4.1, "notes": "母婴全品类新国货"},
    {"id": 32, "name": "贝亲",       "slug": "pigeon",     "category_slug": "maternal-infant", "origin": "日本",  "positioning": "mid",      "quality": 4.3, "service": 3.8, "value": 4.0, "notes": "奶瓶/奶嘴日式工艺"},

    # ===== 食品 food (5) =====
    {"id": 33, "name": "三只松鼠",   "slug": "three-squirrels","category_slug": "food",       "origin": "中国",   "positioning": "value",    "quality": 3.8, "service": 3.5, "value": 4.2, "notes": "电商品牌坚果起家"},
    {"id": 34, "name": "良品铺子",   "slug": "bestore",    "category_slug": "food",            "origin": "中国",   "positioning": "value",    "quality": 3.8, "service": 3.5, "value": 4.2, "notes": "高端零食,SKU 广"},
    {"id": 35, "name": "百草味",     "slug": "baicaowei",  "category_slug": "food",            "origin": "中国",   "positioning": "value",    "quality": 3.8, "service": 3.5, "value": 4.2, "notes": "坚果+果干性价比"},
    {"id": 36, "name": "山姆会员店", "slug": "sams-club",  "category_slug": "food",            "origin": "美国",   "positioning": "mid",      "quality": 4.5, "service": 4.0, "value": 4.2, "notes": "自有品牌 Member's Mark 强"},
    {"id": 37, "name": "农夫山泉",   "slug": "nongfu",     "category_slug": "food",            "origin": "中国",   "positioning": "value",    "quality": 4.2, "service": 3.8, "value": 4.3, "notes": "饮用水+茶饮料双线"},

    # ===== 家居 home (5) =====
    {"id": 38, "name": "MUJI",       "slug": "muji",       "category_slug": "home",            "origin": "日本",   "positioning": "mid",      "quality": 4.3, "service": 3.8, "value": 4.1, "notes": "极简日用,床品口碑稳"},
    {"id": 39, "name": "宜家",       "slug": "ikea",       "category_slug": "home",            "origin": "瑞典",   "positioning": "value",    "quality": 4.2, "service": 3.7, "value": 4.6, "notes": "全球性价比之王,自提成本"},
    {"id": 40, "name": "林氏木业",   "slug": "linsy",      "category_slug": "home",            "origin": "中国",   "positioning": "value",    "quality": 3.8, "service": 3.5, "value": 4.4, "notes": "互联网家具,设计年轻化"},
    {"id": 41, "name": "梦洁",       "slug": "mengjie",    "category_slug": "home",            "origin": "中国",   "positioning": "mid",      "quality": 4.0, "service": 3.7, "value": 4.0, "notes": "床品老牌,四件套选择多"},
    {"id": 42, "name": "欧普照明",   "slug": "opple",      "category_slug": "home",            "origin": "中国",   "positioning": "mid",      "quality": 4.1, "service": 3.7, "value": 4.1, "notes": "灯具国民品牌,售后稳"},

    # ===== 运动户外 sports (5) =====
    {"id": 43, "name": "HOKA",       "slug": "hoka",       "category_slug": "sports",          "origin": "美国",   "positioning": "high-end", "quality": 4.6, "service": 3.7, "value": 3.5, "notes": "厚底跑鞋开创者,缓震突出"},
    {"id": 44, "name": "Nike",       "slug": "nike",       "category_slug": "sports",          "origin": "美国",   "positioning": "mid",      "quality": 4.3, "service": 3.7, "value": 3.8, "notes": "Pegasus/Vaporfly 产品线全"},
    {"id": 45, "name": "Adidas",     "slug": "adidas",     "category_slug": "sports",          "origin": "德国",   "positioning": "mid",      "quality": 4.2, "service": 3.7, "value": 3.9, "notes": "Ultraboost/Adios 跑马强"},
    {"id": 46, "name": "迪卡侬",     "slug": "decathlon",  "category_slug": "sports",          "origin": "法国",   "positioning": "value",    "quality": 3.9, "service": 3.6, "value": 4.7, "notes": "全品类运动超市,自营占比高"},
    {"id": 47, "name": "Arc'teryx",  "slug": "arc-teryx",  "category_slug": "sports",          "origin": "加拿大", "positioning": "high-end", "quality": 4.8, "service": 3.6, "value": 3.2, "notes": "户外硬壳标杆,溢价显著"},

    # ===== 图书教育 books (3) =====
    {"id": 48, "name": "图灵",       "slug": "turing",     "category_slug": "books",           "origin": "中国",   "positioning": "mid",      "quality": 4.3, "service": 3.8, "value": 4.1, "notes": "IT/计算机图书主力社"},
    {"id": 49, "name": "人民邮电",   "slug": "ptpress",    "category_slug": "books",           "origin": "中国",   "positioning": "mid",      "quality": 4.2, "service": 3.8, "value": 4.1, "notes": "覆盖广,引进版多"},
    {"id": 50, "name": "中信",       "slug": "citic-press","category_slug": "books",           "origin": "中国",   "positioning": "mid",      "quality": 4.2, "service": 3.8, "value": 4.0, "notes": "商业/社科/经管强"},

    # ===== 健康保健 health (4) =====
    {"id": 51, "name": "Nature Made","slug": "nature-made","category_slug": "health",          "origin": "美国",   "positioning": "mid",      "quality": 4.3, "service": 3.8, "value": 4.0, "notes": "USP 认证,维生素全品类"},
    {"id": 52, "name": "Swisse",     "slug": "swisse",     "category_slug": "health",          "origin": "澳大利亚", "positioning": "mid",    "quality": 4.2, "service": 3.8, "value": 4.0, "notes": "澳洲品牌,女性保健品线强"},
    {"id": 53, "name": "Move Free",  "slug": "move-free",  "category_slug": "health",          "origin": "美国",   "positioning": "mid",      "quality": 4.2, "service": 3.8, "value": 4.0, "notes": "关节氨糖口碑品牌"},
    {"id": 54, "name": "汤臣倍健",   "slug": "by-health",  "category_slug": "health",          "origin": "中国",   "positioning": "mid",      "quality": 4.0, "service": 3.7, "value": 4.0, "notes": "国产膳食补充剂龙头"},
]


# ---------- 数据规范化 + 校验 ----------
def normalize_brand(raw: Dict[str, Any]) -> Dict[str, Any]:
    """把 raw dict 转成 schema 要求的结构(嵌套 scores 对象)。"""
    quality = float(raw["quality"])
    service = float(raw["service"])
    value = float(raw["value"])
    for name, score in (("quality", quality), ("service", service), ("value", value)):
        if not (0.0 <= score <= 5.0):
            raise ValueError(f"brand id={raw['id']} {name}={score} 越界 [0,5]")

    return {
        "id": int(raw["id"]),
        "name": str(raw["name"]).strip(),
        "slug": str(raw["slug"]).strip().lower(),
        "category_slug": str(raw["category_slug"]).strip(),
        "origin": str(raw["origin"]).strip(),
        "positioning": str(raw["positioning"]).strip(),
        "scores": {
            "quality": round(quality, 2),
            "service": round(service, 2),
            "value": round(value, 2),
        },
        "notes": str(raw.get("notes", "")).strip(),
    }


def validate_unique_ids(brands: List[Dict[str, Any]]) -> None:
    """id 必须唯一。"""
    seen: Dict[int, str] = {}
    for b in brands:
        bid = b["id"]
        if bid in seen:
            raise ValueError(f"重复 id={bid}: {seen[bid]} vs {b['name']}")
        seen[bid] = b["name"]


def validate_against_schema(brands: List[Dict[str, Any]]) -> None:
    """用 schema.json 校验 brands 数组。失败抛错并打印第一条错误。"""
    if jsonschema is None:
        print("[warn] jsonschema 未安装,跳过 schema 严格校验(只做基础检查)", file=sys.stderr)
        return
    if not SCHEMA_PATH.exists():
        print(f"[warn] schema 不存在: {SCHEMA_PATH},跳过", file=sys.stderr)
        return

    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        schema = json.load(f)

    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(brands), key=lambda e: list(e.absolute_path))
    if errors:
        for e in errors[:3]:
            print(f"[schema error] {'/'.join(map(str, e.absolute_path))}: {e.message}", file=sys.stderr)
        raise SystemExit(f"schema 校验失败 {len(errors)} 条")


# ---------- 主流程 ----------
def build_brands() -> List[Dict[str, Any]]:
    brands = [normalize_brand(b) for b in BRANDS]
    validate_unique_ids(brands)
    return brands


def write_brands(brands: List[Dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(brands, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[ok] wrote {len(brands)} brands → {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="品牌种子数据生成器(54 主流品牌)")
    parser.add_argument("--out", type=Path, default=BRANDS_OUT, help="输出 JSON 路径")
    parser.add_argument("--dry-run", action="store_true", help="只校验,不出文件")
    parser.add_argument("--stats", action="store_true", help="输出品类分布统计")
    args = parser.parse_args()

    brands = build_brands()
    validate_against_schema(brands)

    if args.stats:
        from collections import Counter
        cat_counter = Counter(b["category_slug"] for b in brands)
        pos_counter = Counter(b["positioning"] for b in brands)
        print("\n=== 品类分布 ===")
        for cat, cnt in sorted(cat_counter.items(), key=lambda x: -x[1]):
            print(f"  {cat:20s}  {cnt}")
        print("\n=== 定位分布 ===")
        for pos, cnt in sorted(pos_counter.items(), key=lambda x: -x[1]):
            print(f"  {pos:10s}  {cnt}")
        print(f"\n总计: {len(brands)} 品牌")

    if args.dry_run:
        print("[dry-run] OK,未写文件")
        return 0

    write_brands(brands, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
