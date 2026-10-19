---
name: reviewer-panel
description: 投稿前评审压力测试。组建 2-4 名领域专家评审人格（程序主席按论文子领域分配）+ 合规/统计审查，对成稿做 holistic 全文评审，产出结构化 review.json（致命缺陷/可修 nit 分级 + 位置 + 建议），发现的问题直通 diagnosis-clinician 形成评审→诊断→修订闭环。触发条件：要求"模拟评审""审稿意见""压力测试""投稿前检查"。
parameters:
  paper_path:
    type: string
    required: false
    description: "评审对象，默认 .codeartsdoer/.research/workspace/paper/paper.md"
  n_reviewers:
    type: integer
    default: 3
    description: "评审人数，2-4；领域跨度大的稿可到 4"
  harshness:
    type: string
    default: standard
    enum: [standard, harsh]
    description: "standard=严苛但公允；harsh=顶会最黑评审模式（暴露最坏情况，用于压力测试）"
  out_dir:
    type: string
    required: false
    description: "产物目录，默认 .codeartsdoer/.research/workspace/reviews"
---

# reviewer-panel Skill

对抗性自查。**定位：rubric 是自查（产出者视角），本 skill 是他查（评审者视角）——用评审人格找自查找不到的盲区。**

> **验收标准**：按 `references/review-qa-rubric.md` 打分；R2（锚回接审查——评审发现的每个声明-证据断裂必须真实存在）= 0 → 评审作废（编造问题的评审比没有评审更糟）。
>
> **诚实边界**：模拟评审是 LLM 扮演的**压力测试**，不是真同行评审；评审分数不可作为投稿决策唯一依据（写入每份评审报告头部）。

---

## 1. 工作流

### Phase 0：程序主席分诊

1. 读成稿，识别子领域（如「KG 幻觉评测 / 基准构建」）；
2. 生成 N 名评审人格：共享「不妥协的学术守门人」内核（挑真问题、不堆礼貌、不发明问题装彻底、致命缺陷与可修 nit 分级），叠加**领域 overlay**（每人的专长子域、偏好审查维度、已知挑剔点由论文主题动态生成——不是固定人名库）；
3. 分配：每人 expertise 匹配论文子领域（模拟 PC 分配逻辑）。

### Phase 1：holistic 全文评审（每人独立）

每人通读全文一遍，产出个人报告，维度：

| 维度 | 检查内容 |
|---|---|
| **声明-证据矩阵** | 逐论断核对 claim 锚：有锚且证据支撑 / 有锚但强度不匹配（「suggest 证据写 show 结论」）/ 无锚裸奔——**机械回接我们独有的 claim_id/run 号体系** |
| 统计可复现性 | 指标定义清晰度 / 基线公平性 / 显著性声称有无检验支撑 / 样本量合理性 |
| 方法-实验一致性 | 摘要 vs 结果 vs 结论的数字与强度三角一致；贡献声称 vs 实验覆盖 |
| 表述与红线 | 未决标记是否被措辞软化（「初步表明」被写成「表明」）/ scope 限定丢失 / over-claiming 动词 |
| 领域 nit | 术语/相关工作遗漏/图表引用（格式层，severity=minor） |

评分尺度（1-10）+ 总评（accept/borderline/reject）+ 致命缺陷清单（若有）。

### Phase 2：程序主席汇总

- 冲突裁决：多名评审对同一处的矛盾意见并陈（不合并平均）；
- 去重合并 → 结构化 `review.json`：`{reviewer, dimension, severity: fatal/major/minor, location, issue, suggestion, claim_ref}`；
- **锚回接审查**：每条 fatal/major 抽查成稿原文——问题必须真实存在于所指位置（防评审幻觉，R2 红线）；
- 汇总报告：分数分布 / fatal 清单 / 修订优先级排序。

### Phase 3：直通诊断

review.json 作为 diagnosis-clinician 输入（manifest 契约）：评审发现的「声明-证据断裂」类问题进诊断流程定位根因（文献缺失/实验缺失/写作滑变），修订建议带 claim_ref 可回接。

---

## 2. 产物

```
out_dir/
├── review.json           ← 结构化评审（可机读，直通 diagnosis）
├── panel-report.md       ← 汇总报告（分数/fatal/优先级 + 诚实边界声明）
└── personas.md           ← 本轮人格档案（领域 overlay + 分配依据，可复现）
```

---

## 3. Gate Check

- 人格由论文主题动态生成且分配依据落盘（E6：同稿同参数 → 同人格档案）
- 每条 fatal/major 通过锚回接审查（所指问题真实存在）
- 声明-证据矩阵逐论断核对过（有锚/锚弱/无锚 三态标注）
- 冲突意见并陈未静默合并
- 报告头部含「模拟评审≠真同行评审」声明

---

## 4. 与其他 skill 的边界

| 能力 | 本技能 | diagnosis-clinician | paper-writer rubric |
|---|:--:|:--:|:--:|
| 对抗性评审（他查视角） | ✅ | ❌（根因诊断） | ❌（自查） |
| claim 锚机械回接 | ✅（独有底座） | 消费 review.json | 产出锚源 |
| 修订执行 | ❌（只诊断不修） | 定位根因 | paper-writer 重写 |

---

## 5. 技术参考对照

| 机制 | 参考 |
|---|---|
| N 名 holistic 领域专家 + 程序主席分配（不做逐段 fan-out——全文规模会淹没） | paperjury v3（reviewer-personas：Unflinching Gatekeeper 内核 + 领域 overlay） |
| 声明-证据矩阵 / 统计可复现性模板 | K-Dense peer-review（claim_evidence_matrix / statistical_reproducibility） |
| 评审幻觉防护（锚回接审查） | 本 skill 独有（反捏造红线在评审侧的延伸） |
| 评审→诊断闭环 | 本项目独有（review.json 直通 diagnosis-clinician） |

---

## 6. 运行机制（遵守 HARNESS.md）

- **工具调用**：锚回接抽查用确定性文本匹配（claim_ref 定位原文 span），失败标 `ref_not_found` 并降级人工抽查。
- **错误恢复**：E6 幂等（人格生成种子 = 论文标题 + 子领域 + 参数）；E5 多评审并行时冲突不静默合并（Phase 2 并陈纪律）。
- **人的介入**：H1（评审人数/严苛度由用户定，harsh 模式显式声明用途）；H2（无不可逆操作）。
- **Agent Memory**：M2 存 `workspace/reviews/`；sidecar 刷新。
- **轨迹与归档**：人格分配决策 + 锚回接结果入 trace；review.json 入 artifacts。
