# HARNESS — 科研 skill 运行机制规范（可复现性协议 v2）

> 本文件是所有 skill 的横切运行机制唯一真源。每个 `SKILL.md` 默认遵守本文档。
> v2 在 v1（工具契约 / E1–E6 / H0–H3 / M0–M3）之上，对标两个生产级 agent 框架补齐**可复现性根基**：**deepseek-harness**（append-only 会话日志、"Model-visible ⟺ logged"、确定性组合、快照重放）与 **OpenViking**（L0/L1/L2 上下文分层、两阶段会话提交、memory-diff 审计、freshness）。机制映射见 §9.1；我们是文档协议而非运行时，降级实现诚实声明见 §9.2。
> 目标：让本 skill 集合**可复现、可恢复、可介入、可追溯、可审计**。

---

## 0. 可复现性公理（P1–P5）

最高原则。任何 skill、任何节与本节冲突时，以本节为准。

| 公理 | 内容 | 来源 |
|---|---|---|
| **P1 模型可见 ⟺ 已记录** | agent 决策依据的每份上下文（读了什么、检索到什么、工具返回什么）必须记入本轮轨迹日志 `trace.jsonl`，事后可重建。无法从轨迹重建的「决策依据」无效。 | dsh「Model-visible means logged」 |
| **P2 产物即投影 + 归档不可变** | 产物目录可由「轨迹 + progress」推导；已提交归档 `archives/archive-NNN/` 只增不改、永不删除；发现错误 → 新归档 + errata，不改写历史。 | dsh append-only / 提交代永不改写 |
| **P3 组合即配置** | 每轮执行前固化 run-manifest（skill 清单 + 版本锚定 + 参数 + 门控阈值 + 检索配置）；重跑按 manifest 复现组合，禁止凭记忆。 | dsh profile/bundle + `--dump-config` |
| **P4 评分确定性** | 检索排序只依赖查询命中与预声明 tie-breaker（路径字典序）；时间、频率、大小等偶然因素不参与排序。检索语料不变 → 候选集不变。 | OV「访问频率/更新时间不影响排序」 |
| **P5 改动可审计** | 经验库/策略库每次写入必须产出 before/after diff（memory-diff）；无 diff 的写入视为未发生。 | OV `memory_diff.json` |

**诚实边界（P0 级声明）**：LLM 参与的摘要/提取/生成天然非确定（OpenViking 对其记忆提取亦作同样声明）。本协议的可复现性承诺限定在**输入语料 + 规则 + 组合 + 产物结构 + 哈希**层面；LLM 生成文本的逐字复现不承诺、不伪装。含外部 API 的调用在轨迹中标注 `nondeterministic: true`，原始返回存 `raw/` 供人工复核。

---

## 1. 工具调用契约（Tool Contract）

### 1.1 工具清单与分类

| 类别 | 工具 | 用途 |
|---|---|---|
| 文件 | read / write / edit / glob / grep | 读写产物、局部修订、检索文件 |
| 执行 | bash | 跑脚本、CLI（cb / python / 图工具） |
| 检索 | 知识库检索 / graph.json 子图检索 | 召回文献、论断、经验 |
| 编排 | Task（subagent）/ TodoWrite | 派发子 skill、跟踪进度 |
| 交互 | 澄清/审批 | HITL（见第 3 节） |

### 1.2 失败契约（每个工具的统一失败报告）

工具失败必须返回三要素，禁止只返回「成功/失败」布尔：

```
{exit_code, stdout, stderr}
```

agent 的**强制纪律（P0）**：
- 工具返回非零 `exit_code` 或非空 `stderr` → **先读 stderr，再决策**，禁止盲目原样重试。
- 同一调用连续失败 2 次 → 换策略（换参数/换工具/降级），不得第 3 次原样重试。

### 1.3 幂等性

- `write`：覆盖语义，写前必须先 `read`（除非新建）。
- `edit`：`oldString` 必须唯一匹配，否则失败不落盘。
- 同一输入的重复执行不得产生重复/损坏产物（产物目录以固定路径组织，重跑覆盖同文件）。

### 1.4 工具调用事件化（P1 落地）

- 每次工具调用**追加**一条事件到本轮 `trace.jsonl`：`{ts, event: tool_call, tool, args_digest, exit_code, stderr_head, side_effect, ms}`；外部 API 调用加 `nondeterministic: true`。
- **决策事件**：agent 做出分叉决策（分诊结论 / 干预选择 / 门控判定）时记 `{event: decision, what, basis[]}`——`basis` 必须指向轨迹中已记录的事件或已存在的产物路径（P1 自指闭环）。
- **上下文读取事件**：`{event: context_read, path, level: L0|L1|L2, why}`。
- **纪律**：只追加，禁止回写/删除/美化历史事件；**错误决策原样保留**（它们是 rsi-evolver 的原料）。
- 事件 schema 与写入细则：`skills/_shared/session-archive.md` §2。

---

## 2. 错误恢复（Error Recovery）

### 2.1 分级策略

| 级别 | 触发 | 动作 |
|---|---|---|
| **E1 重试** | 工具瞬时失败（超时/网络/临时锁） | 读 stderr → 换参重试，≤2 次 |
| **E2 降级** | 重试耗尽、主路径不可行 | 换降级路径（如 PDF 无文本层 → OCR；OCR 失败 → `parse_failed` 标注），产物保留降级标记 |
| **E3 隔离** | 单文献/单子 task 失败 | 记 `failed`，不阻塞无依赖的其他任务 |
| **E4 断点续传** | 中断（超时/崩溃/人为停止） | 读 `progress.json`，跳过 `completed` 阶段从断点继续 |
| **E5 回滚** | 策略进化/修改引入退化 | 回退到上一 checkpoint / 策略版本 |
| **E6 回放验证** | 结果可疑需重验 | 同一输入重跑，产物一致（或差异被明确记录）——细则升级见 §2.5 |

### 2.2 断点续传协议（progress.json）

- 每个 skill 维护自己的 `progress.json`，记录**阶段级 + 单元级**完成状态。
- 单元级 `completed/pending` 必须是**文件名或 ID 列表**，禁止 `"all"` 简写。
- 每完成一个单元/阶段，**立即落盘**（用 `edit` 局部更新优于 `write` 覆盖）。
- **并行后台任务（`&`/多路派发）的写盘路径必须用显式绝对路径**：后台任务可能不继承前置 `cd`，相对路径会落盘到错误目录（实测教训）。
- **轨迹联动（v2）**：续传后 `trace.jsonl` **追加**续写，禁止回写中断前的历史事件；`progress.json` 的 stages 与轨迹 `stage` 事件互为校验。
- 格式约定：

```json
{"status": "in_progress", "stages": {"phase_1": "completed", "phase_2": {"completed": ["a.md"], "pending": ["b.md"]}}}
```

### 2.3 回滚协议（checkpoint）

- **产物 checkpoint**：修改前，若目标产物体积大或不可逆，先复制为 `*.bak-vN`。
- **策略版本**：`memory/strategies/<skill>.md` 每条变更带版本号 + 回滚点（见 rsi-evolver）。
- **干预重跑 checkpoint（good-enough，AGDebugger）**：诊断触发的干预重跑以 `progress.json` 已完成阶段为恢复点，fork 新记录，只重执行干预点及受影响下游阶段；**原轨迹完整保留**供对比（P2；协议见 `skills/_shared/intervention-protocol.md` §3）。
- 回滚后记录到 `memory/evolution-log.md`，并触发 `diagnosis-clinician` 复核。

### 2.4 崩溃恢复

- 启动时检测 `status == "in_progress"` 的残留 → 判定是「正常中断」还是「异常崩溃」。
- 正常中断 → 断点续传；异常崩溃 → 先校验已产出的单元完整性（文件存在、JSON 可解析），损坏单元重做。
- **归档队列恢复（v2）**：归档目录存在但缺 `.done` 标记 → 重做 Phase 2 收尾（幂等），Phase 1 三件套不动（见 §5.3）。

### 2.5 回放验证（E6 升级为标准协议）

- **快照 = trace.jsonl + artifacts.json**（产物 sha256 清单）。
- **离线链路**（纯文件读写/解析/grep/本地计算）：可按 trace 重放工具调用并比对产物哈希；不一致 → 复现失败，定位差异。
- **在线链路**（外部 API）：轨迹 `nondeterministic: true`，不做逐字重放；只验证**结构契约**——同样调用序列 + 响应字段存在性 + 数量级合理性；原始返回已存 `raw/` 可人工复核（衔接反捏造红线）。
- replay 脚本随产物归档（先例：`workspace/diagnoses/interventions/replay/`）。

---

## 3. 人的介入（Human-in-the-Loop）

### 3.1 四级介入

| 级别 | 含义 | 触发 | 是否暂停 |
|---|---|---|---|
| **H0 自动** | 常规流程不问 | 一切可自动决策 | 否 |
| **H1 澄清** | 问诊式补充 | 关键变量缺失且不可从产物推断 | 是（≤3 变量/轮） |
| **H2 审批** | 不可逆操作前批准 | 见 3.3 清单 | 是 |
| **H3 阻塞** | 关键分叉无法自动决策 | 分诊类型歧义/进化门控悬而未决 | 是（给选项） |

### 3.2 介入时机表

| 场景 | 级别 | 说明 |
|---|---|---|
| 需求可自动分诊 | H0 | 不暂停 |
| 综述主题边界缺失 | H1 | 追问主题边界/范围 |
| 删除数据、覆盖产物、写策略库、git 操作 | H2 | 需批准 |
| 诊断产出决定性错误 | H2 | 呈 I1–I3 分级干预菜单（含验证条件与预期观察），批准后由 autopilot 执行干预重跑（`skills/_shared/intervention-protocol.md`） |
| 任务类型歧义（综述 or IDEA？） | H3 | 给选项 |
| 进化门控指标持平 | H3 | 给「拒绝/人工复核」选项 |

### 3.3 审批门清单（H2，不可逆/高风险操作）

- `rm` / 删除数据集、产物目录、经验
- 覆盖已存在的 `graph.json` / `strategies/`
- 写入策略库（evolve 阶段，即使过门控也需审批一次）
- `git commit` / `git push`
- 干预重跑（改写指令 / 重排 pipeline / 换 skill 配置后重执行受影响阶段）
- 请求外部 API / 下载大文件
- **删除/改写 `archives/` 已提交归档（v2）——默认拒绝（P2）**；唯一例外：用户明示同意且以新归档 + errata 记录

> 危险命令（如 `rm -rf`）即使用户显式要求，也须先列明将删除的对象再执行。

---

## 4. 上下文管理与分层记忆

### 4.1 记忆四层（M0–M3）

| 层 | 内容 | 存储 | 生命周期 |
|---|---|---|---|
| **M0 会话内** | 当前上下文、中间变量、本次推理 | 上下文窗口 | 会话 |
| **M1 项目级** | 项目约定、编码/科研规范、P0 约束 | `AGENTS.md` / `CLAUDE.md` | 跨会话恒定 |
| **M2 工作区状态** | 断点、论断图、诊断、复现结果 | `.codeartsdoer/.research/`（progress.json / graph.json / diagnoses） | 随研究累积 |
| **M3 经验库** | RSI 沉淀经验 + 策略版本 | `.codeartsdoer/.research/memory/`（experiences + strategies + evolution-log） | 跨会话，可版本化 |

### 4.2 读写时机

| 记忆 | 写时机 | 读时机 |
|---|---|---|
| M1 | 项目初始化/规范变更 | 每次会话启动 |
| M2 progress | 每完成一个单元**立即写** | 启动时恢复断点 |
| M2 graph | literature-scholar 建图完成 | survey/idea/diagnosis 执行前 |
| M3 经验 | rsi-evolver distill 后（附 memory-diff，§4.3） | 各 skill 执行前检索相关 failure_mode（按 §4.5 协议） |
| **sidecar（v2）** | 产出 skill 收尾时自底向上刷新所在目录（§4.4） | 进入任何产物目录前先读 L0（§4.4 读取纪律） |

### 4.3 失效、去重与写入审计

- **策略版本过期**：新 eval 证明旧策略退化 → 标记失效，指向回滚点。
- **经验冲突**：新经验与旧经验矛盾 → 保留「what/why/适用条件」，去重合并，不简单覆盖。
- **优先级**：M1（项目约定）> M3（经验）> M2（状态）；冲突时以高优先级为准，并记录分歧。
- **M3 写入审计（P5，v2）**：`experiences/` / `strategies/` 每次写入/更新，同步在归档目录产出 `memory-diff.json`（adds/updates/deletes 含 before/after，skipped 含稳定 reason_code）；由 rsi-evolver 负责产出，schema 见 `_shared/session-archive.md` §5。

### 4.4 目录 sidecar（L0/L1/L2 按需加载）

| 层 | 文件 | 正文预算 | 用途 |
|---|---|---|---|
| **L0** | `.abstract.md` | ≤256 字符 | 快速相关性判断（关键词/grep 检索目标） |
| **L1** | `.overview.md` | ≤4000 字符 | 结构导航，决定读哪些 L2 |
| **L2** | 原始产物 | 不限 | 确认目标后按需全文读取 |

- **适用目录**：会积累多文件的产物目录（`workspace/literature/`、`memory/`、`memory/experiences/`、`workspace/diagnoses/` 等）；sidecar 为**目录级**，不做每文件 sidecar（skill 自身无需——manifest.yaml 已是索引）。
- **格式**：YAML frontmatter（`directory / generated_by / freshness`）+ 正文（对齐 OV OKF 格式）。
- **freshness**：`total_entries / sampled_entries / pending_child_changes`；子目录变更后父 sidecar 允许**滞后可读**（frontmatter 标 pending）；pending/total ≥ 10% 或直接子项 ≤ 32 时于下一次收尾刷新；**刷新不承诺时限**。
- **生成**：产出 skill 收尾时自底向上（叶目录 → 父目录）；直接子项 > 32 时按路径字典序**稳定采样**（重复刷新取同样本）。
- **读取纪律（P0）**：进目录先读 L0 判断相关性 → 需要导航再读 L1 → **确认目标后才读 L2 全文**。禁止进目录直接全量读文件。全程记 `context_read` 事件（level=L0/L1/L2）。
- 模板与细则：`skills/_shared/session-archive.md` §1。

### 4.5 检索协议（P4 落地）

- **查询样式三分**（对齐 OV TypedQuery）：能力（动词短语，「检索文献」）/ 资源（名词短语，「S2 限速配置」）/ 经验（「XX 的失败模式」）。
- **作用域限定**：检索必须显式指定目标子树（grep/检索限定于特定目录），禁止全仓库平铺检索。
- **排序确定性**：候选只按「查询命中 + 路径字典序 tie-breaker」排序；mtime/大小/访问频率不参与（P4）。
- **失败语义**：无命中 → 输出 `EVIDENCE_MISSING`（衔接 `_shared/anti-fabrication.md`），禁止放宽匹配凑结果——**宁可漏检，不可错检**（OV 同款哲学）。

### 4.6 图检索路径（G 路径，论断图场景）

> 设计依据：遗忘幻觉的对冲 = **生成走节点、不走印象**。论断图把「论断-证据」绑定显式化（每个节点自带 `literature + span + evidence.scope`），综述/IDEA 生成从图出发，不凭上下文印象自由发挥——这是 GraphRAG 思想在科研场景的对症落点（通用场景收益有限，论断密集场景收益显著）。

- **触发**：检索/生成目标涉及「论断、结论、证据关系」且 `graph.json` 存在——survey / idea / diagnosis 的默认前置路径；图缺席 → 降级 flat 检索（§4.5）+ `EVIDENCE_MISSING`，不静默编造。
- **三步（全程确定性，P4 兼容）**：
  1. **L0 粗筛**：读 `workspace/literature/.abstract.md` 判断主题与文献库相关性（不相关即止，省 token）；
  2. **图定位**：主题关键词匹配节点 `text` → 种子节点集 → 沿边 1 跳扩展（同图 + 同查询 → 同子图，邻接遍历确定性）；
  3. **节点锚定生成**：正文每个论断标注节点锚 `[C-xxx-N]`；**无锚论断不得出现**（反捏造红线在生成层的延伸——不能回接图的论断就不写）。
- **可回接验收**：产物论断 → 节点 ID 真实存在 + 文本语义一致（无夸大/张冠李戴/scope 丢失）；**可回接率 = 有效锚数 / 总论断数**，判定明细落盘可抽查（rubric 指标「引用可回接率」）。
- **外部图引擎（GraphRAG 运行时 / 向量库 / OpenViking server）**：**可选加速层，非依赖**——默认路径纯文件操作（grep + JSON 遍历），保证零部署可跑与 P4；环境具备时挂载为召回加速，锚定纪律与验收不变。

---

## 5. 会话归档协议（commit）

### 5.1 生命周期与触发

- **执行轮** = autopilot 一次 pipeline（或单 skill 一次完整执行）。生命周期：执行 → commit 归档（两阶段）。
- **触发**：research-autopilot Phase 2 收尾执行 commit；rsi-evolver 的 distill/evolve 产出 memory-diff 并入当轮归档。
- 单 skill 独立小轮（无 autopilot 编排）：产出写 progress + evolution-log，由下一次 autopilot 归档收编（轻量降级语义，须在轨迹中可追溯）。

### 5.2 Phase 1 —— 同步封存（commit 请求内完成）

1. 分配归档号：`archives/archive-NNN`，单调递增，**永不复用**；
2. 定稿轨迹：复制 `trace.jsonl` 入归档；
3. 产物清单：对 `workspace/` + `memory/` 下产物逐文件 sha256 → `artifacts.json`；
4. manifest 封存：复制 run-manifest（若缺失则此刻重建并标 `reconstructed: true`，见 §5.5）；
5. **no-op 判定**：本轮轨迹无新事件且产物哈希无变化 → 返回 `skipped`，不产生归档目录（记 evolution-log 一行）。

### 5.3 Phase 2 —— 收尾（异步语义）

1. 结构化摘要 `summary.md`（固定格式：一行总览 `[主题]：[意图] | [结果] | [状态]` + 分析 + 核心请求与意图 + 关键概念 + 待办）；
2. 记忆提取：本轮经验/策略写入 → 产出/更新 `memory-diff.json`（§4.3）；
3. 写 `.done` 完成标记。
- **崩溃恢复**：归档目录存在但无 `.done` → 重做 Phase 2（幂等），Phase 1 三件套不动（衔接 §2.4）。

### 5.4 归档目录布局

```
.codeartsdoer/.research/archives/archive-NNN/
├── trace.jsonl       # P1 轨迹定稿
├── manifest.json     # P3 组合快照
├── artifacts.json    # 产物清单 + sha256
├── summary.md        # 固定格式摘要（Phase 2）
├── memory-diff.json  # 记忆变更审计（Phase 2，如有）
└── .done             # 完成标记
```

### 5.5 补归档（诚实规则）

对协议生效**之前**的历史执行轮，允许依据现存产物做追溯性归档，但：
- manifest 必须含 `"reconstructed": true` + `evidence[]`（依据文件路径清单）；
- trace 每行标 `"reconstructed": true`；summary 注明「追溯性归档，非实时记录」；
- **禁止伪装成实时记录**（反捏造红线在归档层的延伸）。

细则：`skills/_shared/session-archive.md` §4。

---

## 6. run-manifest（P3 落地）

- **生成时机**：autopilot Phase 1 分诊结论输出后、拉起首个子 skill 前；执行中位于 `.research/run-manifest.json`，commit 时复制入归档。
- **版本锚定**：skills 目录所在 git commit（短 SHA）；有未提交变更时标 `dirty: true`（须先提交或显式接受不可复现）。
- **重跑纪律**：同 manifest + 同输入产物哈希 → 预期同产物哈希（离线链路，§2.5）。

```json
{
  "manifest_version": 1,
  "run_id": "diagnosis-intervention-1",
  "skills": [{"slug": "diagnosis-clinician", "anchor": "42f9f29"}],
  "pipeline": ["diagnosis-clinician", "rsi-evolver"],
  "parameters": {"scope": "diagnosis+intervention"},
  "gates": {"pm_metric": "defect-unit", "validated_threshold": "3/3"},
  "retrieval": {"scope": ["workspace/literature", "memory/experiences"], "tie_breaker": "path-lexicographic"},
  "reconstructed": false
}
```

- 字段说明与生成细则：`skills/_shared/session-archive.md` §3。

---

## 7. 与各 skill 的对应关系

| Skill | 工具契约落地 | 错误恢复重点 | 介入点 | Memory 重点 | 轨迹与归档职责（v2） |
|---|---|---|---|---|---|
| research-autopilot | Task 派发 + progress 落盘 | E3 隔离 + E4 断点续传 | H1 澄清 + H2 干预重跑 + H3 分诊歧义 | M2 progress | **manifest 固化 + trace 主维护 + commit 归档执行者** |
| literature-miner | 多源 API 检索 | E1 重试 + E2 换源 + E3 隔离 | H2 批量下载 | M2 index | API 调用记 `nondeterministic: true`，raw/ 落盘 |
| literature-scholar | read/解析/建图 | E2 降级（OCR） + E4 | H2 覆盖 graph.json | M2 graph | **`literature/` sidecar 生成与刷新** |
| survey-architect | 图检索 + write | E1/E2 引用校验 | H1 主题边界 | M2 graph 只读 | 按 L0→L1→L2 读文献目录 |
| idea-forge | 图检索 + 查重 | E6 幂等重跑 | H1 方向边界 | M2 graph + M3 经验 | 检索按 §4.5 协议，记 context_read |
| experiment-designer | 方案产出 + 冒烟测试 | E6 幂等 + checkpoint | H1 补条件 + H2 下载 | M2 plan/protocol | 方案产物入 artifacts 哈希清单 |
| experiment-replicator | bash + env.lock | E1 重试 + E3 隔离 + E6 种子 | H2 下载大文件 | M2 runs | 种子/env.lock 入 manifest 与 artifacts |
| diagnosis-clinician | 图检索 + 规则层 + 依赖图 | E6 可复核 | H2 干预菜单 + H3 门控悬决 | M2 全产物只读 | 诊断只读轨迹；产物三件套入哈希清单 |
| paper-writer | read + write | E6 一致性 | — | M2 产物组装 | 组装产物入哈希清单 |
| rsi-evolver | eval 外部调用 | E5 回滚 + E4 进化续传 | H2 写策略库 + H3 门控 | M3 经验/策略（含 Validated 干预蒸馏） | **memory-diff 产出者（P5）+ Phase 2 记忆提取** |

---

## 8. 最小闭环演示（可复现性自检 v2）

一次「读文献」的最小闭环应能完成以下全部可复现检查：

```
1. 工具契约：解析失败返回 {exit_code, stderr}，agent 读错后降级为 OCR；调用入 trace
2. 错误恢复：中断后 progress.json 续传 + 轨迹追加（不回写历史）
3. 人的介入：覆盖 graph.json 前触发 H2 审批
4. 上下文：进 literature/ 先读 .abstract.md（L0）→ .overview.md（L1）→ 按需读 L2
5. 归档：收尾 commit 产出 archive-NNN（trace + manifest + artifacts 哈希 + summary + .done）
6. 审计：本轮经验写入有 memory-diff（before/after 或诚实标注不可得）
7. 重放：离线链路按 trace 重放，产物哈希一致；在线链路验证结构契约
```

---

## 9. 设计来源与降级声明

### 9.1 机制映射表

| 参考机制 | 来源 | 本协议落点 |
|---|---|---|
| Model-visible ⟺ logged；append-only 会话日志 | deepseek-harness | P1 + trace.jsonl（§1.4） |
| 提交代永不改写；fork/resume 从日志派生 | deepseek-harness | P2 + archives 不可变（§5.4） |
| profile/bundle 有序层 + `--dump-config` | deepseek-harness | P3 + run-manifest（§6） |
| keyless recorded-session replay | deepseek-harness | §2.5 回放验证（离线逐字 / 在线结构契约） |
| L0/L1/L2 目录 sidecar + freshness + 稳定采样 | OpenViking | §4.4（预算 256/4000 对齐 OV 默认值） |
| 两阶段 commit（同步归档 + 异步摘要/提取） | OpenViking | §5.2/§5.3 |
| memory_diff.json（before/after + skipped reason_code） | OpenViking | P5 + §4.3（schema 见 _shared §5） |
| 评分不依赖访问频率/更新时间；no-op skipped | OpenViking | P4 + §5.2 no-op 判定 |
| 「宁可漏检不可错检」；LLM 提取非确定性声明 | OpenViking | §4.5 失败语义 + §0 诚实边界 |

### 9.2 降级实现声明（诚实边界）

| 生产框架能力 | 本协议降级实现 | 影响 |
|---|---|---|
| 向量库 + embedding | L0 检索以 grep/关键词承担 | 召回弱于语义检索，但**确定性更强**（P4 天然成立） |
| 插件运行时（一切皆插件） | 协议以 SKILL.md 纪律承载，HARNESS 为唯一真源 | 无运行时强制力，靠 Gate Check + 验证清单约束 |
| 持久队列崩溃恢复 | `.done` 标记 + Phase 2 幂等重做（§2.4/§5.3） | 单机语义，无跨进程队列 |
| 路径锁（EXACT/TREE） | 单 agent 串行为主；并行限于无共享写目录的子任务（E3） | 干预重跑以 fork 不覆盖实现隔离（P2） |

> 细则统一入口：`skills/_shared/session-archive.md`（sidecar / trace / manifest / commit / memory-diff / artifacts 六个操作协议）。
