---
name: rsi-evolver
description: RSI 进化核心。对科研 skill 的执行结果做 reflect 反思、evaluate 独立评价、distill 经验沉淀、evolve 受控策略进化。所有进化经「独立评价 + 强基线」门控、版本化可回滚，且进化本身交由 diagnosis-clinician 诊断是否引入新失败。触发条件：科研执行结束后自动触发；用户要求"复盘""进化""沉淀经验""优化skill""RSI"。
parameters:
  target_skill:
    type: string
    required: false
    description: "本次进化的目标 skill slug，缺省为最近一次执行的 skill"
  scope:
    type: string
    default: reflect+distill
    enum: [reflect+distill, full]
    description: "reflect+distill 仅反思沉淀；full 增加 evaluate+evolve 门控进化"
---

# rsi-evolver Skill

RSI 进化核心。实现「受控的递归自我改进」——这正是本研究质疑与检验的对象，所以本 skill 自身必须遵守可评价、可回滚的纪律。

> **设计根因（P0）**：SEAL 证明「自写验证不可靠，高自评分可与低部署表现并存」；清华 RLVR 证明「pass@1 提升 ≠ 能力边界扩大」。因此本 skill 的进化**绝不依赖自我打分作为唯一验收依据**，必须过独立评价门控。
>
> **验收标准**：每轮进化按 `references/evolution-qa-rubric.md` 打分；V1（独立评价）或 V4（门控回滚）= 0 → 本轮无效，策略库回滚。

---

## 1. 四阶段总览

| 阶段 | 含义 | 产物 | 是否副作用 |
|---|---|---|---|
| `reflect` 反思 | 复盘：哪个判断错了、根因 | `reflect-N.md` | 只读 |
| `evaluate` 独立评价 | 独立指标 + 强基线比较 | `eval-N.json` | 只读 |
| `distill` 沉淀 | 成功/失败提炼为经验 | `experiences/*.md` | 写经验库 |
| `evolve` 进化 | 策略变更 → 门控 → 版本化 | `strategies/{skill}.md` | **门控后写策略库** |

`scope=reflect+distill`：只执行 reflect + distill，不碰策略库。
`scope=full`：执行全部四阶段，evolve 必须过门控。

---

## 2. 工作流

### Phase 0：reflect 反思（只读）

复盘 `target_skill` 最近一次执行：
- 哪个判断/步骤错了？根因是什么（信息缺失 / 上下文组织 / 工具反馈 / 模型内部使用）？
- 是否重复了经验库中已知的失败模式？
- 本次结论的置信度与未决项是否诚实标注？

产物 `memory/reflect-<N>.md`，固定小节：`错误 / 根因 / 是否已知失败模式 / 未决项诚实性`。

**Gate Check**：`reflect` 至少给出 1 条可复核的根因判断（允许「本次无明显错误」但须说明依据）。

---

### Phase 1：evaluate 独立评价（只读，scope=full）

用**独立指标**评价本次产物，禁止用生产方自评分数：

| 评价维度 | 指标 | 强基线 |
|---|---|---|
| 文献图质量 | 关系抽取精度的外部抽样复核 | 同证据量朴素正则/关键词抽取 |
| 综述可靠性 | 论断-依据可回接率 | 同预算普通 LLM 直写（无图） |
| 诊断有效性 | 干预后净修复收益（Validated 干预的 Progress Made）/ 误修复率（Refuted 率）——数据来自 `interventions/` 判定记录，非自评 | 强模型直接诊断、简单条件规则 |
| 复现可复核性 | run 号/种子/版本锁定完整度 | 人工复现清单 |

产物 `memory/eval-<N>.json`：

```json
{"target_skill": "literature-scholar", "metric": "关系抽取精度", "value": 0.72, "baseline": 0.68, "passes_gate": false}
```

**Gate Check**：`eval-N.json` 含 `value` 与 `baseline` 两字段，且数据来源可追溯（非自评分数）。

---

### Phase 2：distill 经验沉淀（写经验库）

将三类输入源提炼为可复用经验，写入 `memory/experiences/`：
1. **reflect 结论**（本次执行的错误与根因）；
2. **evaluate 指标**（独立评价的量化结果）；
3. **Validated 干预记录**（`workspace/diagnoses/interventions/` 中判定为 `Validated` 的干预）——经验 `failure_mode` 取诊断的失败条件类别、`为什么` 取失败传播分析（L4 上游来源+下游影响）、`如何应用` 取干预操作本身（级别+具体改法）。**验证过的干预 → 可复用策略**：DoVer/AGDebugger 均止步于人工修复，本集合把验证过的修复接入蒸馏闭环，是 RSI 主题在诊断侧的落点。

经验文档格式（frontmatter + 正文）：

```markdown
---
name: <经验名>
skill: literature-scholar
failure_mode: condition-merge          ← 失败模式类型
confidence: high
---
规则：<一句话规则>
为什么：<根因，来自某次 reflect>
如何应用：<何时/何地触发这条经验>
```

**P0**：经验必须带 `failure_mode` 类型与根因，禁止只写「这样做更好」的模糊建议。成功与失败经验都记。

**memory-diff 审计（P5，HARNESS §4.3）**：每次 distill/evolve 写入 `experiences/` 或 `strategies/`，同步在当轮归档产出 `memory-diff.json`——写入前快照 before、写入后取 after；门控/审批拒绝的提案进 `skipped`（带稳定 reason_code）；协议前历史写入 before 不可得时 `before: null` + `before_note` 诚实标注，**禁止伪造快照**；无变更仍写全零 diff（证明检查过）。schema 见 `../_shared/session-archive.md` §5。

**Gate Check**：每条经验含 `skill / failure_mode / 为什么 / 如何应用`；每次写入有 memory-diff 伴随。

---

### Phase 3：evolve 策略进化（scope=full，经门控写策略库）

1. **提出策略变更**：基于 distill 的经验，对 `target_skill` 提出一条具体策略变更（改工作流/改抽取纪律/改验收规则）。
2. **门控判定（P0）**：
   - 必须有 `eval-N.json` 的独立指标支持，且 `value >= baseline`（不低于强基线）；
   - 若指标下降或持平 → **拒绝进化，策略变更不写入**。
3. **版本化写入**：`memory/strategies/<skill>.md` 追加带版本号的变更：

```markdown
## v3（2026-10-19）
- 变更：切分纪律增加「同对象不同条件强制拆分」
- 门控：eval-12 value=0.72 baseline=0.68 → 通过
- 回滚点：v2
```

4. **回滚**：任一变更有明确回滚点；用户或后续评价发现退化时回退到上一版本。

**Gate Check**：策略库每次变更必须有 `门控结果 + 回滚点`，无 eval 支持的变更禁止写入。

---

### Phase 4：进化诊断（自我指涉闭环）

**把本次进化交由 `diagnosis-clinician` 诊断**：检查这次进化是否引入新失败条件（如「为减少误改而过度拒答」导致覆盖率下降，或「为过门控而缩小任务」）。

- 若诊断发现退化 → 回滚并记录到 `evolution-log.md`。
- 进化本身也要被诊断——用本研究的论文框架约束本 skill。

---

## 3. 四种改进对象分别验收（来自 RSI Survey）

进化前必须明确「本次改了什么对象」，分别验收，禁止混为一谈：

| 改进对象 | 验收要求 |
|---|---|
| 当前输出 / 搜索轨迹 | 与同预算重采样相比 |
| 基础模型参数 | 原子技能成功率 + 组合可用率；旧技能保留 |
| 持久代码/工具/记忆/技能 | 独立任务 + 跨模型迁移 |
| 产生更新的程序 / 验收器 | 外层改进效率；验收目标是否改变 |

> 普通反思、外部 RL、跨任务自我改进、改进程序的递归增强，必须分别报告（候选 IDEA 01 明确要求）。

---

## 4. 经验库目录

```
.codeartsdoer/.research/memory/
├── .abstract.md / .overview.md ← 目录 sidecar（L0/L1，HARNESS §4.4）
├── reflect-<N>.md              ← 反思（只读产出）
├── eval-<N>.json               ← 独立评价（只读产出）
├── experiences/
│   ├── .abstract.md / .overview.md
│   └── <slug>.md               ← 经验（带 failure_mode）
├── strategies/
│   └── <skill>.md              ← 策略库（带版本号 + 回滚点）
└── evolution-log.md            ← 进化历史（时间 + 变更 + 门控 + 回滚）

> memory-diff.json 不存于 memory/ 而存于当轮归档 `archives/archive-NNN/`（P2：diff 与归档同生命周期，跨轮增量各自记录）。
```

---

## 5. 验证清单

| 检查项 | 方法 |
|---|---|
| reflect 有可复核根因 | 读 reflect-N.md |
| eval 含 value + baseline 且非自评 | 读 eval-N.json |
| 经验含 failure_mode + 根因 | grep `failure_mode` |
| 策略变更过门控 + 有回滚点 | 读 strategies/<skill>.md |
| 经验写入有 memory-diff 伴随（before/after 或诚实标注不可得） | 读当轮归档 memory-diff.json |
| 进化被 diagnosis-clinician 诊断 | 查 evolution-log.md |

---

## 6. 技术参考对照

| 机制 | 参考 |
|---|---|
| 改进对象分类 + 验收依据层级 | RSI Survey（Chen）、Ren Survey |
| 自写验证不可靠 → 独立审计 + 回滚 | SEAL |
| 隐藏评价选版本 + ignition test | AIDE² |
| 评价器共同演化 + 标准漂移 | RQGM |
| pass@k 覆盖 vs pass@1 成功率 | 清华 RLVR、ProRL |

**风险提示（P0）**：本 skill 的「evaluate」若退化成本 skill 自产分数，即落回 SEAL 揭示的陷阱。独立评价必须来自外部：外部抽样复核、独立执行、隐藏标签或领域规则——绝不接受 `research-autopilot`/`rsi-evolver` 自己生成的分数作为唯一依据。

---

## 7. 运行机制（遵守 HARNESS.md）

本 skill 的可复现性由 `HARNESS.md` 集中定义，此处落地关键词：

- **工具调用（Tool Contract）**：`evaluate` 调用外部评价时遵守失败契约 `{exit_code, stdout, stderr}`，评价失败先读 stderr 再决策，不得用「评价失败」当「未通过」或「通过」（HARNESS §1.2）。
- **错误恢复**：
  - E4 断点续传：`reflect/evaluate/distill/evolve` 四阶段在 `progress.json` 记录状态，中断后从断点继续（HARNESS §2.2）。
  - E5 回滚：策略版本回滚协议，回滚后记录 `evolution-log.md` 并交 `diagnosis-clinician` 复核（HARNESS §2.3）。
- **人的介入**：
  - H2 审批：写入策略库（evolve）即过门控也须审批一次（HARNESS §3.3）。
  - H3 阻塞：门控指标持平时暂停给「拒绝/人工复核」选项，不擅自接受（HARNESS §3.2）。
- **Agent Memory**：M3 经验库读写时机——distill 后写 `experiences/`（附 memory-diff，P5），各 skill 执行前按检索协议（HARNESS §4.5）检索相关 `failure_mode`；经验冲突去重不简单覆盖（HARNESS §4.2 / §4.3）。
- **轨迹与归档（HARNESS v2）**：本技能是 memory-diff 产出者（P5）与归档 Phase 2 记忆提取执行者；细则见 `_shared/session-archive.md` §5。