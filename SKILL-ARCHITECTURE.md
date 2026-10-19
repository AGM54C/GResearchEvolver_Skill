# 全自动化科研 Skill 架构设计文档

> 版本：v0.2（新增 Graph 基座、skill 并列关系、技术参考、LLM+GCN 边界）
> 定位：**通用科研工具**，以「LLM 幻觉研究」作为首个跑通实例
> 仓库：GResearchEvolver_Skill（完整版）；参赛版：Huawei-Redbook_Skills（华为小红书 skill 创新赛）

---

## 0. 设计哲学（一句话叙事）

> 一个研究「RSI 自我改进是否可靠」的 skill，自身就实现了**受控的** RSI；
> 一个研究「Agent 诊断」的 skill，自身就用**诊断式交互**对待用户。
> 它同时是工具和实验平台——用它在小范围试验里复现你的 IDEA，就是用产品验证论文。

三个核心原则贯穿全文：

1. **自指（self-referential）**：RSI 与 Agent 诊断既是研究对象，也是产品能力。
2. **受控进化（guarded evolution）**：盲目自我修改不可靠（正是论文质疑点），所有进化必须经「独立评价 + 强基线比较」门控，且可回滚。
3. **可复核（traceability）**：判断有可复核依据；真值未知时明确标注「未决」，绝不假装确定。

---

## 1. 总体架构

三层 + 一个贯穿协议 + 一个共享图基座：

```
┌────────────────────────────────────────────────────────────┐
│  L0 交互层 —— 诊断式 HCI 协议（横切约定，贯穿所有 skill）     │
│  triage 分诊 → clarify 问诊澄清 → diagnose 诊断报告           │
│  → uncertainty 不确定性标注 → traceability 可复核             │
└────────────────────────────────────────────────────────────┘
        ▲ 所有 skill 遵守
┌────────────────────────────────────────────────────────────┐
│  L1 编排层 —— research-autopilot（科研自动驾驶）              │
│  需求诊断、任务分诊、子 skill 编排、全局进度、最终交付          │
└────────────────────────────────────────────────────────────┘
        │ 拉起 / 编排，共享 Graph 基座
┌────────────────────────────────────────────────────────────┐
│  L2 执行层 —— 8 个正交原子 skill                             │
│  literature-miner   文献检索    literature-scholar 文献摄取  │
│  survey-architect   综述编排    idea-forge    IDEA 锻造      │
│  experiment-designer 实验设计   experiment-replicator 复现   │
│  diagnosis-clinician 诊断分析    paper-writer   论文写作     │
└────────────────────────────────────────────────────────────┘
        │ 产出 → 反思
┌────────────────────────────────────────────────────────────┐
│  L3 进化层 —— rsi-evolver（RSI 进化核心）                    │
│  reflect 反思 → evaluate 独立评价 → distill 经验沉淀          │
│  → evolve 策略版本化（经门控后生效，可回滚）                   │
└────────────────────────────────────────────────────────────┘
```

**共享图基座**：`literature-scholar` 构建一次「科学论断图（Graph）」，其余所有 skill 只读消费。图不是独立 skill，是贯穿执行层的共享数据结构。

**数据闭环**：执行层产出 → 进化层反思/评价 → 经验库（memory）→ 下次执行层消费经验 → 更优。

---

## 2. 共享图基座：科学论断图（新增）

### 2.1 节点：原子论断（atomic claim）

文献被切分为**原子论断 node**，每条保留四个字段（缺一不可，否则证据资格不成立）：

```json
{
  "claim_id": "C-042",
  "text": "在 400K、常压下，催化剂 X 使反应产率提升 12%",
  "literature": "AskChem: ...",        // 来源文献
  "scope": "400K、常压、底物 Y",         // 适用条件
  "quantity": {"value": 12, "unit": "%"},
  "span": "§3.2, Table 2"              // 原文定位（回接 PDF）
}
```

### 2.2 边：四个原子关系（atomic relations）

| 关系 | 含义 | 文献依据 |
|---|---|---|
| `support` 支持 | A 为 B 提供正向证据 | AskChem、SciFact |
| `refute` 反驳/冲突 | A 与 B 冲突或反驳 | AskChem 冲突关系、SciFact |
| `condition` 条件约束 | B 仅在条件 A（适用范围）下成立 | AskChem 条件字段、HypoKG 适用条件 |
| `source` 来源/依赖 | B 来源于/依赖于 A（证据链、推导链） | Stored-Is-Not-Supported 来源角色、SCIRIGOR 证据图 |

> 四类关系落到综述的「3.1.3 推理链-证据链-条件链对齐」与「3.1.2 事实/因果/边界/资源四类约束」。

### 2.3 检索：LLM + GCN（技术原型 = G-Retriever）

```
文献 → 原子论断 node（带来源/条件/量值/span）
     → 四类关系 边（support/refute/condition/source）
     → 检索相关节点边 → PCST 剪出子图
     → GNN 图编码器(软提示) + 节点边文本 → LLM 回答
```

### 2.4 硬边界（写入 skill 约束，P0）

> **图连通 ≠ 因果/支持**。GNN 只是「候选子图召回 + 编码」手段，不自动获得科学正确性。证据资格的裁决必须交给 `diagnosis-clinician` 的规则层（来源角色/有效期/权限，Stored-Is-Not-Supported）。图路径连通不能充当因果依据（HypoKG）。

### 2.5 共享非 skill 层（`skills/_shared/`）

`skills/_shared/` 是**非 skill 定义层**（无 `SKILL.md`、不注册），存放 ≥2 个 skill 共用的内容，避免复制漂移（参照 nature-skills 的 `_shared/` 模式）：

| 文件 | 内容 |
|---|---|
| `atomic-relations.md` | 原子论断节点 schema + 四类原子关系（定义层） |
| `diagnosis-template.md` | 诊断报告五列模板 + 分级支持标签 |
| `intervention-protocol.md` | 分级干预协议：I1–I3 类型学 + 判定四类 + Progress Made + 蒸馏接口 |
| `anti-fabrication.md` | 反捏造红线 + 占位符约定 + 反谄媚 |

治理规则：放**定义层**不放**动作层**；每个 skill 在共享词汇上应用各自不同的逻辑。

---

## 3. skill 并列关系与三条研究线（新增）

不是线性流水线，而是「图基座 + 三条研究线 + 一个反馈环」，对应三个候选 IDEA：

```
              literature-scholar（构建图基座）
                        │
      ┌─────────────────┼─────────────────┐
      ▼                 ▼                 ▼
survey-architect   idea-forge      diagnosis-clinician
                        │                 ▲
                        ▼                 │
                 experiment-designer      │
                        │                 │
                        ▼                 │
                 experiment-replicator ───┘
                        │
                    paper-writer
                        │
                    rsi-evolver（反馈环，跨全部 skill）

评估线（IDEA 01）：literature-scholar → survey-architect；idea-forge → experiment-designer → experiment-replicator → diagnosis-clinician
诊断线（IDEA 02）：diagnosis-clinician 汇聚全部 skill 产物（轨迹/文献/方案/复现）
改进线（IDEA 03）：rsi-evolver 消费诊断 → 回写策略 → 闭环
```

**汇聚关系**：`diagnosis-clinician` 是唯一"汇聚点"，输入来自所有其他 skill 的产物；`rsi-evolver` 是唯一"反馈点"，把经验回写给所有 skill。二者是并列关系中最特殊的两个节点。

---

## 4. Skill 清单与职责边界

| Skill（slug） | 中文名 | 层级 | 一句话职责 | 触发条件（示例） |
|---|---|---|---|---|
| `research-autopilot` | 科研自动驾驶 | L1 编排 | 诊断需求、分诊、编排子 skill | 「帮我研究 X」「写篇 Y 的综述」「复现论文 Z」 |
| `literature-miner` | 文献矿工 | L2 执行 | 自主联网检索多源文献、去重排序、回接论断清单 | 给定主题找文献/查最新工作 |
| `literature-scholar` | 文献学者 | L2 执行 | 摄取 PDF、生成《我的想法》笔记、构建论断图 | 丢入论文 PDF / 文献目录 |
| `survey-architect` | 综述架构师 | L2 执行 | 从文献笔记组织综述结构与正文 | 给定综述主题 + 文献集 |
| `idea-forge` | IDEA 锻造 | L2 执行 | 进化计算式：种群→适应度筛选→交叉变异→Pareto 收敛 | 给定研究方向发散/筛选 IDEA |
| `experiment-designer` | 实验设计 | L2 执行 | 猜想拆原子需求、挖意图、补条件，产出可执行方案（AI 代码 / 湿实验 SOP） | 给定猜想要求设计/验证实验 |
| `experiment-replicator` | 实验复现 | L2 执行 | 复现论文、跑基准、执行设计方案，产出可复核结果 | 指定论文/数据集复现，或执行方案 |
| `diagnosis-clinician` | 诊断临床师 | L2 执行 | 对科研推理/结论/轨迹做快速定位、失败条件诊断与分级干预 | 丢入一段推理/结论/轨迹做诊断 |
| `paper-writer` | 论文写作 | L2 执行（可选） | 组装产物为论文章节 | 组装成文 |
| `rsi-evolver` | RSI 进化核心 | L3 进化 | 反思、独立评价、经验沉淀、策略进化 | 每次执行结束后自动触发 / 用户要求进化 |

**边界**：`research-autopilot` 与 `rsi-evolver` 只编排/进化，不承载具体科研逻辑；具体逻辑下沉到 7 个 L2 原子 skill。

---

## 5. L0 诊断式 HCI 协议（横切约定）

所有 skill 执行过程必须遵守。

### 5.1 四动作协议

| 动作 | 含义 | 落地约束 |
|---|---|---|
| `triage` 分诊 | 先把需求归到「综述/复现/IDEA/诊断/写作」某类 | 禁止拿到需求直接开干；`research-autopilot` 必须先输出分诊结论 |
| `clarify` 问诊澄清 | 像医生问症，只追问影响判断的关键变量 | 每轮最多追问 3 个关键变量 |
| `diagnose` 诊断报告 | 结论附带证据链 + 置信度 | 产物统一带 `diagnosis` 块 |
| `traceability` 可复核 | 判断有依据可追溯 | 每条结论给依据来源；真值未知标「未决」 |

### 5.2 诊断报告统一格式

每个 L2 skill 的最终产物末尾必须附诊断块：

```markdown
## 诊断报告（diagnosis）
| 条目 | 判断 | 置信度 | 依据 | 未决项 |
|---|---|---|---|---|
| <结论1> | <成立/存疑/错误> | 高/中/低 | <文献:页/数据:项/实验:run> | <真值未知的部分> |
```

- `依据` 必须追溯到具体来源（文献题名、数据集条目、实验 run 号）。
- `置信度` 只允许 高/中/低。
- 真值未知时 `未决项` 必须显式写出。

**技术参考（HCI 诊断可视化）**：DiLLS（activities/actions/operations 三层行为总结）、AGDebugger（历史编辑+重跑）、XAgen（日志可视化+人工反馈+LLM 评判）、InconLens（跨运行信息里程碑对齐）。

---

## 6. L1 `research-autopilot`（科研自动驾驶）

### 6.1 frontmatter

```yaml
name: research-autopilot
description: 全自动化科研编排器。诊断用户科研需求，分诊到「综述/复现/IDEA/诊断/写作」，编排对应子 skill，维护全局进度，交付带诊断报告的结果。触发条件：用户提出任何科研诉求。
parameters:
  research_dir: {type: string, required: false, description: 研究实例根目录，默认 .codeartsdoer/.research/workspace}
  mode: {type: string, default: auto, enum: [auto, survey, replication, idea, diagnosis]}
  force: {type: boolean, default: false}
```

### 6.2 工作流（manifest-driven routing）

autopilot 是**薄路由器**：分诊/编排所需的触发词（intents）、数据契约（provides/consumes → DAG）、执行序列（pipelines）全部声明在 `skills/manifest.yaml`，SKILL.md 不内联路由细节。新增 skill = manifest 一条注册，编排器零改动；未命中 pipeline 的 skill 不加载进上下文（token 经济）。

```
Phase 0 诊断 + 分诊：读 manifest.yaml（禁止凭记忆）→ 读研究实例现状 → 按 routing_rules 匹配 → triage 输出任务类型 + pipeline → clarify（≤3 关键变量）
Phase 1 编排：按 provides/consumes 推导的 DAG 拉起 L2 skill（entry 按需加载）；维护 .codeartsdoer/.research/progress.json（断点续传）
Phase 2 交付：汇总子 skill 产物 + 诊断报告；触发 rsi-evolver 反思
```

### 6.3 Gate Check
- 分诊结论已输出且类型合法
- progress.json 可断点续传
- 交付物附带诊断报告

---

## 7. L2 八个原子 skill（含技术参考）

> **验收标准落盘（对齐 Auto-Research-Skills hub 成熟模式）**：每个 L2 skill 均带 `references/*-qa-rubric.md`，把 Gate Check 从「感觉」变成可打分、可复核的 artifact；各 rubric 定义 1–5 分维度与硬约束（0 分即作废/降级），并要求复现记录随产物留存：

| skill | rubric | 硬约束（=0 即作废） |
|---|---|---|
| literature-miner | `references/retrieval-qa-rubric.md` | R2 真实性：任何 1 条编造文献 → 整次检索作废 |
| literature-scholar | `references/graph-qa-rubric.md` | E2 可回接性：无依据连边 → 整图降级草稿 |
| survey-architect | `references/survey-qa-rubric.md` | S1 条件保留：系统性去条件化 → 作废重写 |
| idea-forge | `references/fitness-rubric.md` | F3 评价边界 / F4 强基线 → 个体直接淘汰 |
| experiment-designer | `references/design-qa-rubric.md` | X3 七维条件：任一缺失仍产出 → 方案无效 |
| experiment-replicator | `references/repl-qa-rubric.md` | P3 结果如实：粉饰失败 → 本次执行作废 |
| diagnosis-clinician | `references/diagnosis-qa-rubric.md` | D1 依据可追溯 / D2 规则层裁决 → 报告作废 |
| paper-writer | `references/writing-qa-rubric.md` | W2 未决不写死 / W3 引用真实 → 作废重写 |
| rsi-evolver | `references/evolution-qa-rubric.md` | V1 独立评价 / V4 门控回滚 → 本轮无效并回滚 |

### 7.1 `literature-miner`（文献矿工）

- **输入**：研究主题/关键词
- **输出**：多源检索去重排序后的文献清单（含真实 DOI/arXiv ID/URL）
- **工作流**：检索式生成 → 多源并发真实 API 检索 → 去重 → 相关性/新颖性排序 → 元数据+全文 → 清单+诊断报告
- **技术参考**：deer-flow、gpt-researcher（planner/executor）、paper-qa、arxiv-mcp-server、OpenAlex 概念标签
- **Gate Check**：每条结果带真实外部 ID；无编造文献；覆盖率/全文状态入诊断报告
- **映射首例**：为 LLM 幻觉研究补选新增文献

### 7.2 `literature-scholar`（文献学者）

- **输入**：PDF 论文 / 文献目录 / 文献链接列表
- **输出**：每篇一篇《我的想法》笔记（中文）+ 结构化条目 + **科学论断图（Graph）**
- **工作流**：解析 PDF → 切原子论断 → 抽四类关系 → 建图 → 写《我的想法》笔记 → 结构化索引
- **技术参考**：**AskChem**（主，原子断言+来源/条件）、SciFact（证据检索+支持判断）、VeryTrace（结构化语言+局部校验）、G-Retriever（子图检索+GNN）、GraphRAG（社区摘要基线）、SCHEMA（概念图）
- **Gate Check**：笔记含「我的想法」非摘要复述；论述论断图节点保留来源/条件/量值/span 四字段；边类型 ∈ 四类关系
- **映射首例**：仓库 `related work/` 30 篇 + `综述选题/参考论文` 106 篇

### 7.3 `survey-architect`（综述架构师）

- **输入**：综述主题 + 文献笔记集合 + 论断图
- **输出**：综述大纲（章节树）+ 各章节正文稿 + 配图建议 + 参考文献表
- **工作流**：主题分解 → 聚类文献 → 生成大纲 → 分章节成稿 → 交叉校验引用
- **技术参考**：SCIRIGOR（证据图定位断裂处）、HypoKG（弱证据是否被升级为强结论）、「科学总结过度泛化」（检测从特定结果扩张为更广结论）
- **Gate Check**：每个论断有 ≥1 条文献依据；引用可追溯到笔记条目；无「过度泛化」断言
- **映射首例**：`综述选题-20261010/`（Word 初稿 + 六幅配图）

### 7.4 `idea-forge`（IDEA 锻造，进化计算式）

- **输入**：研究方向 + 文献/数据现状 + 论断图 gap
- **输出**：进化筛选后的 Pareto 前沿 + top-k 候选（六维适应度 + 评价边界 + 强基线）
- **工作流**：gap 基准 → 种群初始化 → 六维适应度评估 → 锦标赛/精英选择 + 交叉变异 → 多代迭代 → Pareto 收敛
- **技术参考**：AI-Scientist v2（tree search）、POPPER（序贯证伪）、HypoKG、DiscoveryBench；适应度 rubric 落盘 `references/fitness-rubric.md`
- **Gate Check**：每代 gen-<g>.json 可复现；top-k 含评价边界 + 强基线 + 反驳条件
- **映射首例**：`候选IDEA集合/`（RSI 可靠性评估 / Agent+LLM 联合诊断 / 诊断指导的自我改进）

### 7.5 `experiment-designer`（实验设计师）

- **输入**：猜想/假设/IDEA（含评价边界）
- **输出**：可执行实验方案——AI 实验 `plan.json + experiment.py + config.yaml`；湿实验 SOP `protocol.md`
- **工作流**：拆原子需求（可证伪子假设）→ 挖隐含意图（深层意图+混淆变量）→ 补条件（七维，缺一不开始）→ 产出方案 → 诊断报告
- **技术参考**：DiscoveryBench（条件/变量/关系分离）、POPPER（可测推论+反证）、Tev（隐藏真值生成任务）、LAB-Bench/ProtocolQA（湿实验协议）、BioPlanner（协议转伪代码）、ChemCrow/ChemAgent（化学执行）
- **Gate Check**：猜想拆为可证伪子假设；七维条件无缺失；AI 分支含 judgement，湿实验分支 SOP 可执行级
- **映射首例**：IDEA 03 验证方案设计（RSI 前后对照实验）

### 7.6 `experiment-replicator`（实验复现）

- **输入**：目标论文 + 数据集（或下载方案），或 experiment-designer 的 plan.json
- **输出**：复现脚本 + 结果 + 与原文指标的对比报告（复现/未复现/部分复现）
- **工作流**：环境搭建 → 数据获取 → 跑基准 → 指标对齐 → 写复现报告
- **技术参考**：DiscoveryWorld/ScienceAgentBench（代码可运行 ≠ 满足科学任务）、LAB-Bench（ProtocolQA 诊断修复）、BioPlanner（协议转伪代码）、Tev（隐藏真值生成任务+过程奖励）
- **Gate Check**：结果可复核（run 号/种子/版本锁定）；未复现项明确标注
- **映射首例**：`experiments/`（空）+ `datasets/`（6 类 47 项）

### 7.7 `diagnosis-clinician`（诊断临床师）—— 唯一汇聚点

- **输入**：一段科研推理/结论/实验输出 + 论断图 + 复现结果 + 执行轨迹（trajectory）
- **输出**：快速定位（依赖图 + 失败传播 + 决定性错误四类分级）+ 失败条件分析 + 证据链 + 分级干预菜单（I1 指令级 / I2 计划级 / I3 配置级）+ 置信度 + 未决项
- **工作流**：定位断言 → 证据资格裁决（规则层三查）→ **快速定位管线 L1–L6**（轨迹分层重组 → 依赖图构建 → 候选召回 → 失败传播分析 → 决定性错误裁决 → 验证依赖核验）→ **分级干预菜单 I1–I3** → 诊断报告
- **干预闭环**：菜单经 H2 审批 → research-autopilot 执行干预重跑（good-enough checkpoint，fork 不覆盖原轨迹）→ 判定四类（Validated / Partially / Refuted / **Inconclusive 单列 agent 未遵循**）→ Validated 干预进 rsi-evolver 蒸馏
- **技术参考**：InconLens（跨运行对齐）、DiLLS（三层行为摘要 activity/action/operation + probing 降级）、AGDebugger（checkpoint/消息编辑/三类编辑类型学）、DoVer（诊断→干预→重跑验证 + 判定四类）、SAGE（多假设失败归因）、DeFA（依赖引导归因：事件依赖图+失败传播图）、ReCast（归因步骤表示学习）、DISCERN（分层诊断）、Who&When Pro（受控注入基准）
- **Gate Check**：诊断报告含五列 + 决定性错误表；快速定位管线 L1–L6 完整；干预菜单分级且带验证条件；裁决依赖规则层而非图连通
- **映射首例**：IDEA 里的「Agent 与 LLM 联合诊断」

### 7.8 `paper-writer`（论文写作，可选）

- **输入**：各 skill 产物（综述/IDEA/复现/诊断）
- **输出**：论文章节（摘要/引言/方法/实验/结论）
- **工作流**：按目标结构组装 → 引用对齐 → 图表占位 → 成稿
- **Gate Check**：引用一致；无未决断言被写成确定结论

---

## 8. L3 `rsi-evolver`（RSI 进化核心）

「RSI 自进化」的实体化，**受控进化**四阶段：

| 阶段 | 含义 | 产物 |
|---|---|---|
| `reflect` 反思 | 复盘本次执行：哪个判断错了、为什么、根因 | `reflect-N.md` |
| `evaluate` 独立评价 | 用独立指标 + 强基线比较本次产出 | `eval-N.json` |
| `distill` 经验沉淀 | 成功/失败案例 + **Validated 干预记录**提炼为可复用经验，写入经验库 | `experiences/*.md` |
| `evolve` 策略进化 | 提出策略变更 → **经门控** → 版本化写入策略库 | `strategies/{skill}.md`（带版本号）|

### 8.1 门控（guardrail，关键）

1. **独立评价门控**：策略变更必须让 `evaluate` 独立指标提升，且不低于强基线，才允许进策略库。
2. **版本化 + 可回滚**：策略库每条变更带版本号，可一键回滚。
3. **进化也被诊断**：`rsi-evolver` 的每次进化，交由 `diagnosis-clinician` 诊断是否引入新失败条件（自我指涉闭环）。

### 8.2 技术参考（RSI 四类改进对象分别验收）

| 改进对象 | 必须补充的检验 | 参考 |
|---|---|---|
| 当前输出与搜索轨迹 | 与同预算重采样相比 | 清华 RLVR（pass@k vs pass@1）|
| 基础模型参数 | 原子技能成功率 + 组合可用率；旧技能保留 | New Skills or Sharper Primitives、ProRL |
| 持久代码/工具/记忆/技能 | 独立任务 + 跨模型迁移 | AIDE²（隐藏评价 + ignition test）|
| 产生更新的程序与验收器 | 外层改进效率；验收目标是否改变 | AIDE²、SEAL、RQGM |

**验收依据层级**：形式验证 < 执行反馈 < 外部反馈 < 内在自评可靠性分层（RSI Survey(Chen)）；自写验证不可靠，需独立审计 + 整状态回滚（SEAL）。

### 8.3 经验库（memory）

```
.codeartsdoer/.research/memory/
├── experiences/              ← 经验文档（成功/失败案例，可检索复用）
├── strategies/               ← 策略库（按 skill 分文件，带版本号）
└── evolution-log.md          ← 进化历史（时间 + 变更 + 门控结果 + 回滚记录）
```

---

## 9. 技术参考总表（新增）

| 类别 | 主参考 | 辅参考 |
|---|---|---|
| 文献检索 | arXiv/S2/Crossref/OpenAlex API、deer-flow、paper-qa | arxiv-mcp-server |
| 原子论断抽取 | AskChem、SciFact、VeryTrace | — |
| 图构建与检索 | G-Retriever、GraphRAG | SCHEMA 概念图 |
| 证据资格管理 | Stored-Is-Not-Supported、SCIRIGOR | — |
| 综述组织 | SCIRIGOR、HypoKG | 科学总结过度泛化 |
| IDEA 生成 | POPPER、HypoKG、DiscoveryBench | — |
| 实验设计 | DiscoveryBench、POPPER、Tev | LAB-Bench、BioPlanner、ChemCrow |
| 实验复现 | DiscoveryWorld、ScienceAgentBench、Tev | LAB-Bench、BioPlanner |
| 失败诊断/归因 | InconLens、DoVer、SAGE、DeFA、ReCast | DISCERN、Who&When Pro |
| RSI 进化 | RSI Survey(Chen)、AIDE²、SEAL、RQGM | Ren Survey、清华 RLVR、ProRL |
| HCI 诊断交互 | DiLLS、AGDebugger、XAgen | InconLens |

---

## 10. 数据流与产物目录

```
<项目根目录>/
├── SKILL-ARCHITECTURE.md              ← 本文档
└── .codeartsdoer/
    └── .research/                     ← 科研 skill 统一产物根
        ├── workspace/                 ← 研究实例工作区（首例 = LLM 幻觉研究）
        │   ├── literature/            ← 文献摄取产物（笔记 + 结构化索引 + graph.json）
        │   ├── survey/                ← 综述产物
        │   ├── ideas/                 ← IDEA 产物
        │   ├── experiments/           ← 复现产物
        │   └── diagnoses/             ← 诊断报告
        ├── memory/                    ← RSI 经验库（见 8.3）
        └── progress.json              ← 编排器断点续传状态
```

**关键数据流**：

```
literature-scholar ──论断图+笔记──> survey-architect / idea-forge / diagnosis-clinician
idea-forge ──假说──> experiment-designer ──方案──> experiment-replicator ──结果──> diagnosis-clinician
diagnosis-clinician ──诊断报告──> rsi-evolver / paper-writer
所有 skill 产出 ──> rsi-evolver ──经验──> memory ──下次执行消费──> 所有 skill
```

---

## 11. 验证清单（落地后整体自测）

| 层 | 验证项 | 方法 |
|---|---|---|
| Graph | 论断图节点保留来源/条件/量值/span 四字段 | 抽查 graph.json |
| Graph | 边类型 ∈ 四类关系，无「图连通=支持」的越界 | 抽查 |
| HCI | 每个 L2 产物带诊断报告块 | grep `## 诊断报告` |
| HCI | 未决项非空标注 | 检查无「假装确定」断言 |
| 编排 | progress.json 可断点续传 | 中断重跑不重复已完成阶段 |
| 执行 | 文献笔记含「我的想法」非摘要 | 抽查 |
| 执行 | IDEA 含评价边界 + 强基线 | 抽查 |
| 执行 | 复现结果 run 号/种子可复核 | 抽查 |
| 执行 | 实验方案七维条件无缺失 | 抽查 plan.md |
| 进化 | 策略变更经门控且有版本号 | 查 evolution-log.md |
| 进化 | 进化可回滚 | 回滚演练一次 |

---

## 12. 首例映射（LLM 幻觉研究 → 首个实例数据）

| 架构元素 | 仓库资产 | 说明 |
|---|---|---|
| literature-miner 输入 | 检索式 + 多源 API | 自主检索补充文献 |
| literature-scholar 输入 | `related work/`（30 篇笔记）+ `综述选题/参考论文`（106 篇 PDF） | 首批摄取语料 |
| survey-architect 主题 | `综述选题-20261010/面向科学研究的大语言模型幻觉检测与治理` | 首篇综述 |
| idea-forge 输出基准 | `候选IDEA集合/` | 首批 IDEA |
| experiment-designer | IDEA 03 验证方案（RSI 前后对照实验设计） | 设计对照/判定标准 |
| experiment-replicator | `datasets/`（6 类 47 项）+ `experiments/` | 数据集清单已就绪 |
| diagnosis-clinician 场景 | IDEA 02「Agent 与 LLM 联合诊断」 | 诊断对象 = 科研推理 |
| rsi-evolver 研究对象 | 主线「评估自我改进前后的科研推理行为」 | 产品即实验 |

---

## 13. 落地路线图（确认后执行）

1. 写 `research-autopilot` SKILL.md（含 L0 诊断协议 + 断点续传 progress.json）
2. 写示例原子 skill `literature-scholar`（含本题「原子论断 + 四类关系 + Graph」的构建与检索规范）
3. 跑通最小闭环：`autopilot → literature-scholar → 产出论断图 + 诊断报告`
4. 写 `rsi-evolver`（先做 reflect + distill，evaluate/evolve 门控后置）
5. 补 `survey-architect`、`idea-forge`（用仓库已有综述和 IDEA 验证）
6. 补 `experiment-designer`、`experiment-replicator`、`diagnosis-clinician`、`paper-writer`
7. 全链路用 LLM 幻觉实例跑通，产出可演示的完整科研流水线

---

## 附：与现有 skill 的关系

本套科研 skill 与 `repo-simple-wiki` / `codebase-crossrepo-pipeline` **正交**：
- 已有 skill：面向「代码仓库」生成工程知识文档；
- 本套 skill：面向「科研文献/数据/IDEA」生成科研推理产物。

可组合：`experiment-replicator` 复现论文时若涉及代码，可委托 `repo-simple-wiki` 生成该复现代码的知识文档，供诊断追溯。