# 最小闭环执行报告（retrieval pipeline）

任务类型：`retrieval`（manifest.pipelines: literature-miner → literature-scholar）
执行日期：2026-10-19（v1）；2026-10-19（v2 短板改进轮）

## v2 改进对照（四短板 → 现状）

| v1 短板 | v2 改进 | 结果 |
|---|---|---|
| ① 单源检索（仅 arXiv） | 增加 OpenAlex + Crossref 真实并发检索（S2 两次 429 降级缺席） | 21 → **57 篇**（44 相关，4 篇多源交叉验证） |
| ② 摘要级摄取 | top3 全文摄取（arXiv HTML → 文本提取 → 全文级论断切分） | +9 全文级节点（含 quantity 量值与章节级 span） |
| ③ 跨文献关系稀疏（1/9） | 新增 5 条跨文献边 | 6/16 跨文献边 |
| ④ refute 边为 0 | 概念分歧分析（truthfulness vs faithfulness；有意性维度） | refute 1 条（E-10）+ condition 3 条 |

## 执行链路

| 阶段 | skill | 产物 | 状态 |
|---|---|---|---|
| 检索 v2 | literature-miner | inbox/raw/{oa,cr}-*.json + papers.json（57 篇）+ index.md v2 | completed |
| 全文摄取 v2 | literature-scholar | inbox/fulltext/{hallulens,kghalubench,lifecycle}.{html,txt} | completed |
| 建图 v2 | literature-scholar | graph.json v2（30 节点/16 边/6 篇）+ notes×6 + entries×6 + index.md v2 | completed |

## 关键事件（HARNESS 恢复与缺陷记录）

- E2 协议修正（v1）：arXiv HTTP 80 → 301 强制 HTTPS，修正后 3/3 式成功
- E1/E2 限速降级（v2）：S2 三式 ×2 次 429 → 降级缺席（EVIDENCE_MISSING，不编造）；Crossref method 式空响应 → 重试成功
- E5 落盘竞态（v2）：`&` 后台任务未继承 `cd`，5 个检索文件落盘到项目根目录 → 定位归位后重跑合并
- **去重缺陷（v2 发现并修复）**：arXiv ID 带版本号（`2602.19643v1`）vs OpenAlex DOI 无版本（`2602.19643`）键不一致 → 3 条重复入库 + sources 重复 append → 修复：规范化去版本 + 双键归并 + sources 去重（60 → 57）

## 诊断报告（diagnosis）

| 条目 | 判断 | 置信度 | 依据 | 未决项 |
|---|---|---|---|---|
| 检索真实性（R2） | 通过 | 高 | raw/ 三源原始返回可复核；57 篇均带真实外部 ID | S2 源缺席（429），引用图数据缺失 |
| 去重正确性（R3） | 通过（修复后） | 中 | 版本号键缺陷已修复，57 篇抽查无重复 | 仅抽查非全量人工核验 |
| 论断原子性（N1） | 通过 | 中 | 30 节点单一主张、scope 齐全 | Can LLMs Lie? 仍为摘要级 |
| 全文级摄取质量 | 通过 | 中 | top3 全文，span 到章节，quantity 落值（96.67%/15 准则/5 步骤） | 其余 3 篇仍摘要级 |
| 边纪律（E1/E2） | 通过 | 高 | 16 边全部 ∈ 四类且带 evidence_span | — |
| refute 边定性（E-10） | 存疑 | 中 | KGHaluBench abstract（truthfulness 界定）vs HalluLens §2（解耦主张）定义域重叠且互斥 | KGHaluBench 正文是否点名 HalluLens 未核验；refute vs condition 的归类待全文复核 |
| 条件边定性（E-15） | 成立 | 中 | 有意性维度正交于「与源一致性」维度，逻辑成立 | 说谎行为的实证覆盖未读全文 |
| graph_stat 一致性（G1） | 通过 | 高 | 30/16/6 与实际一致 | — |

## 未决项汇总（v2 遗留）

1. S2 源缺席：引用数与引用图数据不完整（OpenAlex 引用数为 0/27，arXiv 源无引用数）
2. 摄取不对称：top3 全文级 vs 其余 3 篇摘要级——同图共存的粒度差异已用 span 字段区分，但跨粒度关系（如 E-16）置信度受限
3. E-10 refute 定性待核验：需读 KGHaluBench §2 Related Work 是否点名批评 HalluLens 类静态/intrinsic 任务复用
4. 44 篇相关文献仅摄取 6 篇：图基座代表性受限于演示规模

## 自评（rubric 对照，v2）

- retrieval-qa-rubric：R1=5 / R2=5 / R3=4（缺陷自查自修，非事先防住）/ R4=4 / R5=3 / R6=4
- graph-qa-rubric：N1=4 / N2=4 / N3=5 / E1=5 / E2=5 / G1=5 / G2=5
- 结论：四短板全部实质改进，硬约束零违规；新暴露缺陷（去重键、落盘竞态）已修复并沉淀（见 rsi-evolver 产物）
