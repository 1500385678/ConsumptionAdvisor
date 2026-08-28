# ConsumptionAdvisor

> 11-消费-Consumption 行业 Web 项目 · 内部代号 ConsumptionAdvisor
> 帮用户不花冤枉钱——结合张勇的品类研究 + 实时比价 + 决策心理。

## 项目说明
基于张勇的 36 行业架构,ConsumptionAdvisor 是 消费-Consumption 行业的 Web 端顾问产品。
立项背景与完整方案见 [`项目开发计划.md`](项目开发计划.md)。

## 同步
- GitHub: https://github.com/1500385678/ConsumptionAdvisor
- Gitee: https://gitee.com/architectzy/ConsumptionAdvisor

## 自动化(cron 调度)
- T4 每日 02:00 巡检项目 + 更新开发计划 + 写入 .Log/
- T5 每日 03:00 完成小步开发 + commit + push

## 工具链
```bash
# 1. md 源文件 → 结构化 JSON(解析消费品类清单 + 品牌评估框架)
python3 scripts/md_to_json.py

# 2. 品牌种子数据 → 54 主流品牌(覆盖 10 大品类)
python3 scripts/seed_brands.py            # 默认写 data/brands.json
python3 scripts/seed_brands.py --stats   # 看品类/定位分布

# 3. 品牌排行 CLI(综合分 = 0.4*质量 + 0.3*服务 + 0.3*性价比)
python3 scripts/rank_brands.py                       # 全品类 top 5
python3 scripts/rank_brands.py -c digital -n 3       # 数码 top 3
python3 scripts/rank_brands.py -c apparel -p value   # 性价比服饰

# 4. 历史价导入(归一化价格快照 → 按 product_id 分组)
python3 scripts/import_price_history.py              # 导入并写 data/price_history.json
python3 scripts/import_price_history.py --stats      # 打印每 SKU 摘要表

# 5. 30 天最低价 + 虚假折扣检测
python3 scripts/lowest_price.py --input data/prices.example.json

# 6. 单测(无需 pytest)
python3 tests/test_md_to_json.py
python3 tests/test_brands.py
python3 tests/test_lowest_price.py
python3 tests/test_import_price_history.py
# 或一次性跑全部
python3 -m unittest discover tests/
```

## 数据层
- `data/categories.json` — 10 大品类(数码/家电/服饰/美妆/母婴/食品/家居/运动/图书/健康)
- `data/brands.json` — 54 品牌种子(质量/服务/性价比三维度,0-5 评分)
- `data/schema.json` — JSON Schema 校验文件
- `data/prices.example.json` — 价格快照样例(6 SKU × 58 快照,2026-08-27 落地)
- `data/price_history.json` — 归一化历史价(由 `import_price_history.py` 生成)

## 目录结构
```
ConsumptionWeb/
├── 项目开发计划.md           # 立项与开发计划(SOT)
├── 消费顾问开发架构与计划.md   # v1.0 设计稿附录(详见巡检报告)
├── README.md
├── data/                     # 结构化数据(JSON)
├── scripts/                  # 数据生成 + 工具 CLI
├── tests/                    # 单元测试
├── .plan/                    # 每日 T4 写的当日开发计划
└── .Log/                     # 巡检报告
```
