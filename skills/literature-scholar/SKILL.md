---
name: literature-scholar
description: 文献学者。将科研文献（PDF/文本/链接）切分为原子论断，抽取四类原子关系（support 支持 / refute 反驳 / condition 条件约束 / source 来源依赖）构建科学论断图，并为每篇生成中文《我的想法》笔记与结构化条目。触发条件：用户上传论文 PDF、文献目录或文献链接，要求"读文献""整理文献""建立知识图谱""做文献笔记""构建论断图"。
parameters:
  input:
    type: string
    required: true
    description: "论文 PDF 路径 / 目录 / 链接列表（逗号分隔）"
  scope:
    type: string
    default: general
    description: "领域提示：chemistry/biology/material/cs/general，用于关系抽取上下文"
  out_dir:
    type: string
    required: false
    description: "产物目录，默认 .codeartsdoer/.research/workspace/literature"
---

# literature-scholar Skill

文献摄取与科学论断图构建。**本 skill 是共享图基座的唯一生产者**——它产出的 `graph.json` 被 survey-architect、idea-forge、diagnosis-clinician 只读消费。

> **核心方法论（P0）**：参考 AskChem（带来源/条件的原子断言）、SciFact（证据检索 + 支持判断）、G-Retriever（子图检索 + GNN 编码）。**但图连通 ≠ 因果/支持**——本 skill 只做「结构化提取 + 图构建」，不做证据资格裁决，裁决交给 diagnosis-clinician。
>
> **验收标准**：产出按 `references/graph-qa-rubric.md` 打分；E2（可回接性）= 0 → 整图降级草稿，禁止下游消费。

---

## 1. 产物结构

```
out_dir/
├── graph.json                      ← 全局科学论断图（本 skill 主产物）
├── notes/
│   └── <文献短名>/我的想法.md        ← 每篇一篇中文笔记
├── entries/
│   └── <文献短名>.md                ← 结构化条目（题名/方法/贡献/局限）
└── index.md                        ← 文献总索引（题名 → 笔记/条目/节点范围）
```

---

## 2. 工作流

### Phase 0：摄取与解析

1. 对每个输入：PDF 抽文本层（无文本层则 OCR）、提取图表说明、定位章节与段落跨度。arXiv 文献优先走 **HTML 全文**（`https://arxiv.org/html/<id>`，LaTeXML 渲染，2024 年后论文可用），HTML → 纯文本后仍按章节定位 `span`——全文级论断必须带章节级 span 与量值（quantity）。
2. 无法解析的文献：记录 `parse_failed`，不强行切分。
3. 产物：每篇一个 `raw` 文本块，保留段落定位（`span`）。

**Gate Check**：至少 1 篇成功解析出文本。

---

### Phase 1：原子论断切分（node 构建）

对每篇文献切出**原子论断 claim**。原子论断 = 单一科学主张，可独立核验。

节点 schema（四个字段缺一不可）：

```json
{
  "claim_id": "C-<文献短名>-<序号>",
  "text": "在 400K、常压下，催化剂 X 使底物 Y 产率提升 12%",
  "literature": "<完整题名>",
  "span": "§3.2, Table 2",
  "evidence": {
    "scope": "400K、常压、底物 Y",          // 适用条件
    "quantity": {"value": 12, "unit": "%"},   // 量值（可空）
    "source_role": "实验观测"                   // 来源角色：实验观测/文献转述/假设/推论
  }
}
```

切分规则：
- 一条论断只含一个主张；复合句按主张拆开。
- 保留 `scope`（适用条件）：AskChem 强调「同一物质在不同条件下的断言不得错误合并」——条件不同必须拆成不同节点。
- `source_role` 四选一：`实验观测 / 文献转述 / 假设 / 推论`。假设与事实断言必须用不同节点，不得混为已证事实。

---

### Phase 2：四类原子关系抽取（edge 构建）

对节点对抽关系，仅限四类：

| 关系 | 含义 | 判定要点 |
|---|---|---|
| `support` | A 为 B 提供正向证据 | 需有明确证据链，不能仅「同主题」 |
| `refute` | A 与 B 冲突/反驳 | 需真冲突，非条件不同 |
| `condition` | B 仅在条件 A 下成立 | A 是 B 的适用范围/前提 |
| `source` | B 来源于/依赖于 A | A 是 B 的推导前件或数据来源 |

边 schema：

```json
{"edge_id": "E-<序号>", "src": "C-x", "dst": "C-y", "relation": "support", "evidence_span": "§5.1"}
```

抽取纪律（P0）：
- 关系必须可回接到原文 `span`；无依据不连边。
- 「图连通」不写进 relationship——只有上述四类关系才算边，主题相关/共现不算。
- 跨文献的关系同样抽取（如 A 文献支持 B 文献的论断）。

---

### Phase 3：建图与检索索引

1. 汇总所有节点 + 边 → `graph.json`：

```json
{
  "version": 1,
  "nodes": [ {node...}, ... ],
  "edges": [ {edge...}, ... ],
  "graph_stat": {"nodes": 0, "edges": 0, "literatures": 0}
}
```

2. 检索索引：为检索（LLM+GNN 原型，G-Retriever）预留 `gretriever` 字段——标记每个节点可被图编码器消费的文本表示与邻接关系。**GNN 仅做候选子图召回 + 编码，不产出真值判定**（G-Retriever 边界：引用的节点/边存在 ≠ 科学条件下支持结论）。

---

### Phase 4：《我的想法》笔记生成

每篇一篇中文笔记，固定小节：

```markdown
# <完整题名>
[原文入口] · [本地 PDF] · N 页

**一句话：**<该文一句话贡献>

**怎么做：**<方法要点>

**局限：**<作者自述 + 你识别到的边界>

**我的想法：**<结合本研究的迁移点、应做的对照、证据边界>  ← 核心，非摘要复述

原文定位：<关键章节/图表>
```

**P0**：「我的想法」必须是针对本研究的判断/对照，禁止写成论文摘要复述；局限必须区分「作者自述局限」与「我识别到的边界」。

---

### Phase 5：结构化索引 + 诊断报告

1. 生成 `entries/<文献短名>.md`（题名/方法/贡献/局限/与主线关系，四五行）。
2. 生成 `index.md`：题名 → 笔记路径 → 条目路径 → 节点 ID 范围。
3. 附诊断报告块（L0 协议）：

```markdown
## 诊断报告（diagnosis）
| 条目 | 判断 | 置信度 | 依据 | 未决项 |
|---|---|---|---|---|
| 关系抽取覆盖率 | <数值> | 高 | graph.json 节点/边统计 | 跨文献关系未人工复核 |
| 条件错配风险 | 存疑 | 中 | 抽样 span 回接 | 未全量核验每条 scope |
```

---

## 3. 断点续传

- `progress.json` 记录每篇文献的摄取状态（`parsed / claims_done / edges_done / note_done`）。
- 中断后跳过 `note_done` 的文献，从第一个未完成阶段继续。

```json
{"papers": {"<短名>": {"phase": "edges_done"}}, "graph": {"nodes": 10, "edges": 6}}
```

---

## 4. Gate Check

- `graph.json` 存在且 `nodes > 0`
- 每个节点含 `literature / span / evidence.scope` 三字段
- 每条边 `relation` ∈ 四类关系且含 `evidence_span`
- 每篇笔记含「我的想法」小节且非摘要复述
- `index.md` 存在

---

## 5. 技术参考对照

| 机制 | 参考 | 本 skill 采用 |
|---|---|---|
| 原子断言带来源/条件 | AskChem | 节点 `evidence.scope` + `span` |
| 证据检索 + 支持关系 | SciFact | `support/refute` 边 |
| 结构化语言 + 局部校验 | VeryTrace | 节点可独立核验 |
| 子图检索 + GNN 编码 | G-Retriever | Phase 3 `gretriever` 索引（仅召回，不判定真值）|
| 全局问答（基线） | GraphRAG | 可选社区摘要，但须防条件丢失 |

**首要检查**：同一物质/对象在不同实验条件下的断言是否被错误合并（AskChem 的核心风险 → 本 skill 的切分纪律）。

---

## 6. 运行机制（遵守 HARNESS.md）

本 skill 的可复现性由 `HARNESS.md` 集中定义，此处落地关键词：

- **工具调用（Tool Contract）**：PDF 解析/OCR/图构建工具失败返回 `{exit_code, stdout, stderr}`，解析失败先读 stderr 再降级（HARNESS §1.2）。
- **错误恢复**：
  - E2 降级：PDF 无文本层 → OCR；OCR 失败 → 标注 `parse_failed`，不强行切分（HARNESS §2.1）。
  - E4 断点续传：`progress.json` 记录每篇 `phase`（parsed/claims/edges/note），跳过已完成的文献（HARNESS §2.2）。
- **人的介入**：H2 审批——覆盖已存在的 `graph.json` 前须批准（HARNESS §3.3）。
- **Agent Memory**：M2 工作区——建图完成后写 `graph.json`，并在 `index.md` 记录「题名 → 笔记/条目/节点 ID 范围」，供 survey/idea/diagnosis 只读消费（HARNESS §4.2）。