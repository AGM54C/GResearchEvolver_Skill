---
name: research-autopilot
description: 全自动化科研编排器（orchestrator）。诊断用户科研需求，分诊到「摄取/综述/IDEA/复现/诊断/写作」，编排对应子 skill，维护全局断点续传进度，交付带诊断报告的结果。不承载具体科研逻辑，只做诊断与编排。触发条件：用户提出任何科研诉求，如"帮我研究X""写篇Y的综述""复现论文Z""诊断这段推理""发散IDEA"；关键词：研究、科研、综述、复现、IDEA、诊断、写作。
parameters:
  research_dir:
    type: string
    required: false
    description: "研究实例根目录，默认 .codeartsdoer/.research（含 workspace/ + memory/）"
  mode:
    type: string
    default: auto
    enum: [auto, retrieval, intake, survey, idea, design, replication, diagnosis, writing, evolution]
    description: "强制任务类型；auto 由分诊决定"
  force:
    type: boolean
    default: false
    description: "忽略已有 progress.json，重新开始"
---

# research-autopilot Skill

全自动化科研编排器。对用户科研需求的唯一入口：**诊断 → 分诊 → 编排 → 交付 → 反思**。

> **强制约束（P0）**：本 skill 执行过程中，除 `clarify` 问诊阶段外，**禁止向用户询问非关键的分步决策**。流程分支均由本技能规则决定。
>
> **路由纪律（P0，manifest-driven）**：本 SKILL.md 是**薄路由器**，不内联任何子 skill 的触发词、DAG 或产物契约。分诊与编排一律读 `skills/manifest.yaml`（声明式注册表），按需加载命中 skill 的 `entry` 文件。**禁止凭记忆路由**——即使你认为记得分诊表，也必须重读 manifest。新增 skill = manifest 一条注册 + 按需一行 pipeline，本文件零改动。

---

## 1. 路由数据源：`skills/manifest.yaml`

编排所需的全部声明都在 manifest（与 SKILL.md 同级的 `manifest.yaml`）：

| manifest 键 | 用途 |
|---|---|
| `skills.<slug>.intents` | 意图匹配（分诊依据） |
| `skills.<slug>.provides / consumes` | 数据契约 → 推导 DAG 与可并行性 |
| `skills.<slug>.entry` | 子 skill 的 SKILL.md 路径（按需加载，未命中的不进上下文） |
| `skills.<slug>.rubric` | 交付时按此验收（详见各 skill `references/`） |
| `pipelines.<mode>` | 分诊结论 → skill 执行序列 |
| `routing_rules` | 分诊优先级（intents → artifacts → context → 歧义 H3） |

DAG 不单独维护：`consumes` 的 provides 方即前驱；前驱全部完成（或产物已存在）才可执行后继；相邻无数据依赖的可并行。

---

## 2. 分诊（读 manifest，不凭记忆）

分诊 = 按 `routing_rules` 优先级匹配：

1. **match_intents**：诉求关键词命中 `skills[].intents` → 所属 pipeline。
2. **match_artifacts**：丢入 PDF/文献目录/链接 → `intake`；丢入推理/结论文本 → `diagnosis`；丢入 plan.json → `replication`。
3. **match_context**：无显式意图时读 workspace 现状（`graph.json` 缺失则前置 literature-scholar；已有产物的 phase 不重复执行）。
4. **ambiguity**：多 mode 互斥命中且不可消解 → H3 暂停给选项。

示例（仅示意，真实匹配以 manifest 为准）：

| 用户诉求（示例） | 任务类型 | pipeline（manifest.pipelines） |
|---|---|---|
| 「帮我找 X 方向的文献」 | `retrieval` | literature-miner → literature-scholar |
| 「帮我写篇 X 的综述」 | `survey` | literature-scholar → survey-architect |
| 「复现论文 Z」 | `replication` | experiment-replicator → diagnosis-clinician |
| 「诊断这段推理」 | `diagnosis` | diagnosis-clinician |

---

## 3. 前置条件

1. 子 skill 的 SKILL.md 与本技能在同一 skills 目录下（`skills/*/SKILL.md`）
2. 研究实例根目录 `.codeartsdoer/.research/` 已初始化（不存在则创建）
3. 首次运行前无 `progress.json`，进入全量模式

---

## 4. 工作流

### Phase 0：诊断 + 分诊（triage + clarify）

**目标**：把模糊需求归为明确任务类型，识别缺失的关键变量。

1. **triage 分诊**：
   - 读 `skills/manifest.yaml`（禁止凭记忆，每次重读）
   - 读入研究实例现状（`.codeartsdoer/.research/workspace/` 下已有哪些产物、`graph.json` 是否存在）
   - 按 `routing_rules` 优先级匹配 → 输出任务类型 + `pipelines.<mode>` 序列
   - **必须先输出分诊结论**（含命中的 intents 与 pipeline），禁止直接开干。

2. **clarify 问诊澄清**（仅当关键变量缺失时）：
   - 每轮最多追问 3 个变量，只问影响分诊/编排的（如：综述主题边界、复现目标论文、数据集是否已下载）
   - 已有默认值或可从产物推断的变量，不追问。

**输出**：任务清单 JSON

```json
{
  "task_type": "survey",
  "pipeline": ["literature-scholar", "survey-architect"],
  "assumptions": {"topic": "面向科学研究的大语言模型幻觉检测与治理"},
  "missing": []
}
```

**Gate Check**：`task_type` 合法；`pipeline` 非空且每个 skill 存在。

---

### Phase 1：编排执行

**目标**：按依赖图顺序拉起子 skill，维护断点续传。

0. **固化 run-manifest（HARNESS §6，P3）**：分诊结论输出后**立即**生成 `.research/run-manifest.json`（pipeline + skills 版本锚定 git 短 SHA + 关键参数 + 门控阈值 + 检索作用域），本轮全部执行按此组合，重跑按 manifest 复现；schema 见 `../_shared/session-archive.md` §3。

1. **检查 `progress.json`**：
   - 不存在 / `force=true` → 全量模式，初始化进度
   - `status == "completed"` → 全量模式，清空重跑
   - `status == "in_progress"` → 断点续传，跳过已完成阶段

2. **拉起子 skill**：
   - 按 manifest `provides/consumes` 推导的 DAG 顺序执行；无数据依赖的 skill 可并行（本技能用 Task 工具派发 subagent 执行各子 skill）
   - 子 skill 的执行指令从 manifest `entry` 指向的 SKILL.md 按需加载；**未命中 pipeline 的 skill 不加载、不进上下文**（token 经济）
   - 每个子 skill 独立执行，各自写产物到 manifest `outputs` 声明的目录
   - 每完成一个子 skill，立即更新 `progress.json` 并落盘

3. **错误隔离**：单个子 skill 失败不阻塞后续无依赖的 skill；记录失败到 `progress.json`，最终报告汇总。

4. **干预重跑**（diagnosis 产出决定性错误后，本技能为执行者）：
   - 读 `workspace/diagnoses/interventions/` 的干预菜单，仅执行 **H2 审批通过**的项，未批准不跑；
   - 按级别执行：I1 改指令重派对应子 skill / I2 调整 pipeline 序列重跑受影响阶段 / I3 换 skill 或配置重派；
   - **good-enough 恢复**：以 `progress.json` 已完成阶段为 checkpoint，fork 新记录，只重执行干预点及受影响下游；**原轨迹保留不覆盖**（HARNESS §2.3）；
   - 重跑后按 `../_shared/intervention-protocol.md` §4 判定四类（Validated / Partially Validated / Refuted / Inconclusive，agent 未遵循单列），Progress Made 按 manifest `pipelines` 里程碑数计算，写回 `interventions/<N>.md`；
   - `Validated` 干预交 `rsi-evolver` 蒸馏（验证过的干预 → 可复用策略）。

**progress.json 格式**：

```json
{
  "status": "in_progress",
  "task_type": "survey",
  "started_at": "<ISO>",
  "updated_at": "<ISO>",
  "stages": {
    "literature-scholar": {"status": "completed", "graph_nodes": 0, "notes": 0},
    "survey-architect": {"status": "in_progress"},
    "rsi-evolver": {"status": "pending"}
  }
}
```

> **强制（P0）**：`stages` 的键必须是 skill slug 列表，状态值 ∈ `pending/in_progress/completed/failed`。每完成一个阶段立即 `write` 落盘，不得批量延迟。用 `edit` 工具局部更新优于 `write` 整体覆盖。

---

### Phase 2：交付 + 反思

1. **汇总诊断报告**：收集各子 skill 产出的诊断块，汇总成总交付报告。
2. **触发进化**：调用 `rsi-evolver` 对本次执行做 reflect + distill（默认 scope），写入经验库（附 memory-diff，P5）。
3. **输出总报告**：任务类型、执行了哪些 skill、各产物路径、诊断摘要、未决项、成本。
4. **会话归档 commit（HARNESS §5）**：按 `../_shared/session-archive.md` §4 执行两阶段归档——Phase 1 同步封存（trace 定稿 + manifest + artifacts 哈希清单 + no-op 判定）；Phase 2 收尾（结构化摘要 + 记忆提取 memory-diff + `.done` 标记）。归档号单调递增；已提交归档永不改写（P2）。

**Gate Check**：
- 每个完成的子 skill 有对应产物目录且非空
- 交付报告含「诊断摘要 + 未决项」
- `rsi-evolver` 已触发或明确跳过（`mode=auto` 时若管线仅含 intake 可跳过进化）
- `run-manifest.json` 已固化且 anchor 与 skills 目录 git HEAD 一致（`dirty` 须已处理）
- 本轮归档 `archives/archive-NNN/` 三件套（trace/manifest/artifacts）+ `.done` 齐全，或明确记录 `skipped`

---

## 5. 产物目录

```
.codeartsdoer/.research/
├── workspace/
│   ├── literature/            ← literature-scholar 产出（笔记 + graph.json）
│   ├── survey/                ← survey-architect 产出
│   ├── ideas/                 ← idea-forge 产出
│   ├── experiments/           ← experiment-replicator 产出
│   ├── diagnoses/             ← diagnosis-clinician 产出
│   └── paper/                 ← paper-writer 产出
├── memory/
│   ├── experiences/           ← rsi-evolver 经验库（写入须附 memory-diff，P5）
│   ├── strategies/            ← rsi-evolver 策略库（版本化）
│   └── evolution-log.md       ← 进化历史
├── archives/
│   └── archive-NNN/           ← 会话归档（trace/manifest/artifacts/summary/diff/.done；只增不改，P2）
├── run-manifest.json          ← 本轮执行组合快照（P3）
└── progress.json              ← 本编排器断点续传状态
```

---

## 6. 验证清单

| 检查项 | 方法 |
|---|---|
| 分诊结论已输出且类型合法 | 查 Phase 0 输出 |
| progress.json 可断点续传 | 中断后重跑跳过已完成 `stages` |
| 每个已完成 skill 有非空产物目录 | `ls workspace/<领域>/` |
| 交付报告含诊断摘要 + 未决项 | grep `未决` / `## 诊断报告` |
| 进化已触发或明确跳过 | 查 `memory/evolution-log.md` 或报告 |
| 干预判定记录完整（四类 + 遵循状态 + PM） | 读 `workspace/diagnoses/interventions/*.md` |
| run-manifest 已固化且 anchor 一致 | 读 `run-manifest.json` + `git rev-parse --short HEAD` 比对 |
| 本轮归档三件套 + `.done` 齐全 | `ls archives/archive-NNN/` |

---

## 7. 与其他 skill 的边界

| 能力 | 本技能 | 子 skill |
|---|:--:|:--:|
| 需求诊断与分诊 | ✅ | ❌ |
| 依赖图编排 + 断点续传 | ✅ | ❌ |
| 错误隔离 + 汇总交付 | ✅ | ❌ |
| 原子论断图构建 | ❌ | literature-scholar |
| 综述/IDEA/复现/诊断/写作 | ❌ | 各自原子 skill |
| 干预重跑执行（I1–I3 落地 + 判定四类） | ✅ | ❌（菜单生成在 diagnosis-clinician） |
| RSI 反思进化 | ❌ | rsi-evolver |

**本技能核心价值**：唯一入口、自动分诊、依赖编排、断点续传、统一交付——把「全流程科研」变成一次可触发、可恢复、可复盘的单次调用。

---

## 8. 运行机制（遵守 HARNESS.md）

本 skill 的健壮性由 `HARNESS.md` 集中定义，此处落地关键词：

- **工具调用（Tool Contract）**：用 Task 派发子 skill 时，subagent 返回约定 `{exit_code, stdout, stderr}`；失败先读 stderr 再决策，禁止原样重试（HARNESS §1.2）。
- **错误恢复**：
  - E3 错误隔离：单个子 skill 失败不阻塞无依赖的子 skill（HARNESS §2.1）。
  - E4 断点续传：`progress.json` 的 `stages` 对象阶段级/单元级续传，单元级用文件名列表，禁止 `"all"`（HARNESS §2.2）。
  - 崩溃恢复：启动检测 `status=="in_progress"` 残留，校验产物完整性后从断点继续（HARNESS §2.4）。
- **人的介入**：
  - H1 澄清：仅当关键变量缺失时问诊，≤3 变量/轮（HARNESS §3.1）。
  - H3 阻塞：分诊类型歧义时暂停给选项，不擅自选择（HARNESS §3.2）。
- **Agent Memory**：M2 工作区状态（`progress.json`）每完成一个阶段**立即落盘**，用 `edit` 局部更新优于 `write` 覆盖（HARNESS §4.2）。
- **轨迹与归档（HARNESS v2）**：本技能是 trace 主维护者与 commit 执行者——分诊后固化 run-manifest（P3），收尾按 `_shared/session-archive.md` §4 两阶段归档（P1/P2）；决策与工具调用入 `trace.jsonl`，**只追加不回写**。进入产物目录先读 L0 sidecar（HARNESS §4.4 读取纪律）。