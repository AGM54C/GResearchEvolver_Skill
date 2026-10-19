---
name: experiment-designer
description: 实验设计师。把要验证的猜想拆成原子需求（可独立证伪的子假设），挖掘隐含意图（真正想证明什么、混淆变量），补齐先决条件/控制变量/测量/判定标准，产出可执行实验方案。AI 实验产出可运行代码+配置交给 experiment-replicator 执行；化工/生物湿实验产出带条件与判定的 SOP 方案文档。触发条件：给定猜想/假设/IDEA，要求"设计实验""怎么验证""实验方案""要做实验"。
parameters:
  hypothesis:
    type: string
    required: true
    description: "要验证的猜想/假设"
  domain:
    type: string
    required: false
    enum: [ai, chemistry, biology, material, general]
    description: "实验领域；决定产出可执行 AI 代码还是湿实验 SOP 方案"
  graph_path:
    type: string
    required: false
    description: "论断图路径，用于对齐已有证据与条件"
  out_dir:
    type: string
    required: false
    description: "产物目录，默认 .codeartsdoer/.research/workspace/experiments/<design-<N>>"
---

# experiment-designer Skill

实验设计（design）——从「我要验证 X」到「具体怎么做、缺什么条件、什么算验证成功」。是 idea-forge（假说）与 experiment-replicator（执行）之间的关键桥梁。

> **核心方法论（P0，三步缺一不可，条件不全不开工）**：
> 1. **拆原子需求**：把大猜想拆成可独立验证/证伪的子假设
> 2. **挖隐含意图**：分析「真正想证明什么」+ 混淆变量
> 3. **补条件**：先决条件/控制变量/测量/判定标准/失败条件全部显式补齐
> 技术参考：DiscoveryBench（条件/变量/关系分离）、POPPER（可测推论+反证）、Tev（隐藏真值生成任务+检查器）、LAB-Bench/ProtocolQA（湿实验协议）、BioPlanner（协议转伪代码）、ChemCrow/ChemAgent（化学执行）。
>
> **验收标准**：产出按 `references/design-qa-rubric.md` 打分；X3（七维条件）= 0 → 方案无效，「条件不全不开工」。

---

## 1. 工作流

### Phase 0：拆原子需求

- 把 `hypothesis` 拆成若干**可独立验证、可证伪**的子假设 `H1, H2, ...`。
- 每个子假设必须能被一个实验直接验证，不能多个假设混在一检验里。
- 拆分边界参照 DiscoveryBench：把假设的**条件 / 变量 / 关系**分开表示，禁止「A 在条件 S 下比 B 好」与「A 无条件比 B 好」混为一条。

输出（`plan.md` 第一块）：

```markdown
## 原子需求
- H1: <子假设>（判定：<什么结果算成立/证伪>）
- H2: ...
```

**Gate Check**：每个 H 有明确「判定」；未拆出可证伪子假设 → 退回 idea-forge 补评价边界。

---

### Phase 1：挖隐含意图

- 分析 `hypothesis` 背后**真正想证明的东西**：用户嘴上说的是验证 X，实际可能想证明 X 的因果、X 的迁移、X 的机制。
- 列出**混淆变量**与**隐含因果链**：哪些变量没被控制会让结论站不住（自证偏差）。
- 反向提问：如果只验证了弱版本，是否等于验证了强版本？（Answer: 否，必须标注）

输出 `plan.md` 第二块：

```markdown
## 隐含意图
- 表面目标：<...>
- 深层意图：<真正想证明的强结论>
- 混淆变量：<未控制会导致结论失效的变量清单>
- 强弱版本差异：<弱结论 ≠ 强结论，哪里会过度推断>
```

**Gate Check**：识别出 ≥1 个深层意图与混淆变量；若无，视为意图未挖尽，继续问 H1 澄清。

---

### Phase 2：补条件（缺一不开始）

把实验可执行所需全部条件显式列出，任一缺失即**不允许进入执行**：

| 条件维度 | 内容 | 缺失后果 |
|---|---|---|
| 先决条件 | 数据/试剂/设备/算力是否可得 | 不可执行 |
| 控制变量 + 对照组 | 控制谁、对照什么（正/负/空白） | 结论无因果 |
| 测量方法与指标 | 怎么测、指标定义、单位 | 无法判定 |
| 判定标准 | 什么算成立/证伪（阈值、统计） | 无法下结论 |
| 重复与样本量 | 重复次数、样本量、随机种子 | 不可复现 |
| 失败条件 | 什么结果意味着猜想被推翻 | 无法证伪 |
| 安全与资源 | 危险性/伦理/预算 | 无法执行 |

输出 `plan.md` 第三块（逐维度填写，缺失标 `[缺失]` 并触发 H1 澄清）。

**Gate Check**：七维无 `[缺失]`，否则不进入 Phase 3（「条件不全不开工」，写入报告未决项）。

---

### Phase 3：产出方案（按领域分支）

**AI / 可编码实验**（domain=ai 或 general 且可编码）：

```
out_dir/
├── plan.json          ← 原子需求/判定标准/种子/指标（结构化，供复现消费）
├── experiment.py      ← 主实验脚本
├── config.yaml        ← 环境/依赖/种子/数据路径
└── README.md          ← 运行说明 + 判定标准 + 失败条件
```

- `plan.json` 的 `judgement` 字段定义「成立/证伪/部分支持」的判定规则，供 experiment-replicator 直接执行并回填判定。

**湿实验（化工/生物/材料，domain=chemistry/biology/material）**：

```
out_dir/
└── protocol.md        ← SOP：材料/试剂/步骤/条件(温度压强当量)/测量/对照/安全/判定
```

- `protocol.md` 必须达到「拿到就能照着做」的粒度，步骤可逐步执行；本 skill **不假装能替人做实体实验**，但方案可供人工执行或后续自动化（BioPlanner 转伪代码）。

---

### Phase 4：诊断报告

```markdown
## 诊断报告（diagnosis）
| 条目 | 判断 | 置信度 | 依据 | 未决项 |
|---|---|---|---|---|
| 原子需求可证伪性 | ... | 高 | plan.md H1..Hn | ... |
| 条件完整性 | 七维齐全/缺X | 中 | 补条件表 | ... |
| 判定标准明确性 | ... | 高 | plan.json judgement | ... |
```

---

## 2. 产物

```
.codeartsdoer/.research/workspace/experiments/<design-<N>>/
├── plan.md            ← 原子需求 + 隐含意图 + 补条件三块
└── (AI: experiment.py/config.yaml/plan.json) 或 (湿实验: protocol.md)
```

---

## 3. Gate Check

- 猜想已拆为可证伪子假设（含判定）
- 隐含意图 + 混淆变量已识别
- 七维条件无缺失（否则不产出方案）
- AI 分支产出 `plan.json`（含 `judgement`）；湿实验分支产出可执行级 SOP
- 附诊断报告

---

## 4. 运行机制（遵守 HARNESS.md）

- **工具调用**：产出验证脚本时遵守失败契约，脚本先在极小样本冒烟（smoke test）再交给复现（HARNESS §1.2）。
- **错误恢复**：E6 幂等——设计稿可重跑，`plan.json` 覆盖前留 `*.bak-vN`（HARNESS §2.3）。
- **人的介入**：H1 澄清——七维条件有缺失时追问（≤3/轮）；H2 审批——下载试剂级/大额数据前批准（HARNESS §3）。
- **Agent Memory**：M2——写 `plan.json` + `protocol.md`；设计过程中读 M3 相关 `failure_mode`（如「条件缺失导致不可复现」）避免重蹈（HARNESS §4.2）。

---

## 5. 与上下游 skill 的关系

| 方向 | skill | 数据流 |
|---|---|---|
| 上游 | idea-forge | 假说（含评价边界）→ 本 skill 的 hypothesis |
| 上游 | literature-scholar | 论断图的已知条件/证据 → 补条件对齐 |
| 下游 | experiment-replicator | plan.json → 直接执行并回填判定 |
| 下游 | diagnosis-clinician | 方案/结果 → 失败条件诊断 |
| 下游 | paper-writer | 方案 + 结果 → 实验章节 |