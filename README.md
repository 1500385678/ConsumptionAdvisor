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

# 6. 决策辅助 CLI(3 步反问 → Top 3 + 值得分,飞书 Bot 接入的预演版)
python3 scripts/decision_helper.py --category digital --need --top 3
python3 scripts/decision_helper.py --category apparel --want --top 3
python3 scripts/decision_helper.py --category home-appliance --positioning mid --need

# 7. 单测(无需 pytest)
python3 tests/test_md_to_json.py
python3 tests/test_brands.py
python3 tests/test_lowest_price.py
python3 tests/test_import_price_history.py
python3 tests/test_decision_helper.py
# 或一次性跑全部
python3 -m unittest discover tests/
```

## 数据层
- `data/categories.json` — 10 大品类(数码/家电/服饰/美妆/母婴/食品/家居/运动/图书/健康)
- `data/brands.json` — 54 品牌种子(质量/服务/性价比三维度,0-5 评分)
- `data/schema.json` — JSON Schema 校验文件
- `data/prices.example.json` — 价格快照样例(6 SKU × 58 快照,2026-08-27 落地)
- `data/price_history.json` — 归一化历史价(由 `import_price_history.py` 生成)

## 决策辅助输出样例

`scripts/decision_helper.py` 是飞书 Bot "消费决策"对话流程的预演版,3 个典型场景:

### 场景 1 · 数码 + 中端 + 真需要(值得分 5/5)

```bash
python3 scripts/decision_helper.py --category digital --positioning mid --need
```

```markdown
## 决策辅助报告

- **品类**:数码 (优先级 P0)
- **目的**:真需要
- **价位定位**:中端
- **品类决策倾向**:`长值优先,谨慎升级`
- **综合值得分**:**5 / 5**

> ✅ 值得认真考虑;在 Top 3 里挑一个**预算够且服务能到**的即可。

### Top 推荐

| 排名 | 品牌 | 定位 | 产地 | 质量 | 服务 | 性价比 | **综合分** | 备注 |
|------|------|------|------|------|------|--------|-----------|------|
| 1 | 华为 | 中端 | 中国 | 4.4 | 3.8 | 4.0 | **4.1** | 自研芯片+鸿蒙生态 |
| 2 | OPPO | 中端 | 中国 | 4.0 | 3.7 | 4.1 | **3.94** | 快充+影像中端价位优选 |
| 3 | vivo | 中端 | 中国 | 4.0 | 3.7 | 4.1 | **3.94** | 与 OPPO 同源,主打影像差异化 |

_评分权重:质量 0.4 / 服务 0.3 / 性价比 0.3;数据来源 brands.json_
```

### 场景 2 · 服饰 + 性价比 + 想要(值得分 1/5,劝退)

```bash
python3 scripts/decision_helper.py --category apparel --positioning value --want
```

```markdown
- **品类**:服饰 (优先级 P1)
- **目的**:只是想要
- **综合值得分**:**1 / 5**

> 🛑 看起来是「想要」驱动;若非真需要,建议**跳过或加入 30 天观察清单**。
```

### 场景 3 · 家电 + 不限定位 + 真需要(值得分 5/5,跨价位 Top 3)

```bash
python3 scripts/decision_helper.py --category home-appliance --need
```

```markdown
- **品类**:家电 (优先级 P0)
- **目的**:真需要
- **价位定位**:不限
- **品类决策倾向**:`长寿命+能耗`
- **综合值得分**:**5 / 5**

### Top 推荐

| 排名 | 品牌 | 定位 | 产地 | 质量 | 服务 | 性价比 | **综合分** | 备注 |
|------|------|------|------|------|------|--------|-----------|------|
| 1 | 美的 | 中端 | 中国 | 4.2 | 4.0 | 4.3 | **4.17** | 国民家电,售后覆盖广 |
| 2 | 格力 | 中端 | 中国 | 4.3 | 3.8 | 4.2 | **4.12** | 空调技术深,售后中等 |
| 3 | 海尔 | 中端 | 中国 | 4.1 | 4.0 | 4.2 | **4.1** | 白电覆盖广,服务网点密 |
```

### 值得分启发式

| 输入 | 值得分 | 引导语 |
|------|--------|--------|
| 想要(任何品类) | 1 | 🛑 跳过 / 加入 30 天观察清单 |
| 真需要 + P0 品类 | 5 | ✅ 预算够且服务能到即可 |
| 真需要 + P1 品类 | 4 | ✅ 认真比价后下手 |
| 真需要 + P2 品类 | 3 | ⚖️ 先确认使用频次 |

> 全部 10 大品类的品类决策倾向(`decision_bias`)见 `data/categories.json`。

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
