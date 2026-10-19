---
name: experiment-replicator
description: 实验复现与执行。复现目标论文、按数据集跑基准，或执行 experiment-designer 产出的实验方案（plan.json），产出可复核的执行结果与「复现/未复现/部分复现」对比报告。触发条件：指定论文/数据集要求复现、跑基准、"复现论文Z"，或执行已设计的实验方案。
parameters:
  target:
    type: string
    required: true
    description: "目标论文（题名/arXiv）、数据集路径，或 experiment-designer 产出的 plan.json"
  out_dir:
    type: string
    required: false
    description: "产物目录，默认 .codeartsdoer/.research/workspace/experiments"
---

# experiment-replicator Skill

复现与基准。**代码能跑 ≠ 满足科学任务**；复现报告必须可复核（环境锁定 + 种子 + 指标对齐）。

> **技术参考**：DiscoveryWorld/ScienceAgentBench（代码运行 vs 科学目标分离）、LAB-Bench（ProtocolQA 诊断修复）、BioPlanner（协议转伪代码）、Tev（隐藏真值生成任务 + 过程奖励）。
>
> **验收标准**：执行按 `references/repl-qa-rubric.md` 打分；P3（结果如实）= 0 → 本次执行作废重跑。

---

## 1. 工作流

### Phase 0：环境与数据准备

- 锁定依赖版本、随机种子、数据集版本，写 `env.lock`。
- 数据不可得时，明确下载方案或标注「未取得」（不假装已复现）。

### Phase 1：跑基准

- 跑目标论文主指标，记录 run 号、超参、输出日志。

### Phase 2：指标对齐

- 与原文指标对比，判定：`复现 / 部分复现 / 未复现`（阈值在前说明）。
- 未复现项明确标注，不得归因于猜测。

### Phase 3：复现报告 + 诊断报告

报告固定含：环境、数据、脚本、与原文指标对照表、未复现项、复现成本。

---

## 2. 产物

```
out_dir/
├── env.lock                ← 依赖/版本/种子锁定
├── scripts/                ← 复现脚本
├── runs/<run-id>/          ← 每次运行产物（日志/指标）
└── report.md               ← 对比报告 + 诊断报告块
```

---

## 3. Gate Check

- `env.lock` 存在且有版本/种子
- 产出「复现/未复现/部分复现」明确判定
- 未复现项显式列出，不假装成功
- 附诊断报告（含置信度 + 未决）

---

## 4. 诊断报告（必含维度）

| 检查项 | 判断 | 依据 |
|---|---|---|
| 复现判定 | 复现/部分/未复现 | run 指标 vs 原文 |
| 可复核性 | 有无 | env.lock + run 号 + 种子 |
| 未决项 | 列表 | 数据缺失/超参未公开 |

---

## 5. 运行机制（遵守 HARNESS.md）

- **执行二态（诚实声明，禁止混淆）**：
  - `execution: real`——有执行环境（本地/沙箱）时真跑代码产数据：每次 run 记 trace（`tool_call`：命令摘要 / exit_code / 时长）+ `runs/<run-id>/run-manifest.json`（产物逐文件 sha256 + 指标快照 + env.lock 哈希）；
  - `execution: protocol_only`——无环境时只产**复现协议包**（scripts/ + env.lock + 步骤说明），报告头部显式标注。**「写了脚本」不得表述为「跑了实验」**——P3（结果如实）在该二态上的直接应用。
- **与运行时形态的差距明示**：AI-Scientist / Agent Laboratory 是运行时形态（自带代码执行栈，产数据是内建能力）；本 skill 是文档协议形态（HARNESS §9）——执行产物入 trace 是本形态下可复现性的最大补强（真跑时全量留痕，协议级时不虚报）。
- **工具调用**：执行失败返回 `{exit_code, stderr}`，读后分类（环境/数据/代码三档）再决定重试或降级（§1.2）。
- **错误恢复**：E1 重试 ≤2；E2 降级（GPU 不可用 → CPU 小样本规模并标注量级差异）；E6 幂等（同 env.lock + 同种子 → 同 run-manifest 指标）。
- **人的介入**：H2 审批——长任务（>10 min）/大批量下载/任何写仓库外路径的操作前批准。
- **Agent Memory**：M2 产物存 `workspace/experiments/`；run-manifest 供 diagnosis-clinician 回放取证（§4.2）。