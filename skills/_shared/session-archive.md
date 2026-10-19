# 会话归档与上下文 sidecar 协议（HARNESS v2 落地细则）

> HARNESS.md §1.4 / §2.5 / §4.4 / §4.5 / §5 / §6 的操作层细则。分工：HARNESS 定「是什么 / 为什么 / 何时」，本文件定「怎么做」。与 `intervention-protocol.md` 同级。
> 设计来源：OpenViking（OKF sidecar、两阶段 commit、memory_diff）与 deepseek-harness（会话日志投影、快照重放），映射表见 HARNESS §9.1。

---

## 1. 目录 sidecar（L0/L1/L2）

### 1.1 文件与格式

L0 `.abstract.md` 与 L1 `.overview.md` 均为 YAML frontmatter + Markdown 正文：

```markdown
---
directory: workspace/literature/
generated_by: {skill: literature-scholar, trigger: pipeline_complete}
freshness: {total_entries: 6, sampled_entries: 6, pending_child_changes: 0}
---
（正文）
```

- **L0 正文**：一句话（≤256 字符），陈述该目录**提供什么**；截断优先保完整句。
- **L1 正文**（≤4000 字符）：`# 目录名` + Brief Description 段（H1 后、首个 `##` 前，此段即 L0 的提取来源）+ `## Quick Navigation`（关键子目录/文件 + 一句话说明）。
- **schema 校验**：未知 frontmatter 键静默丢弃；`directory` 缺失或 YAML 损坏 → 生成失败（fail loud，不静默降级）。
- 两个 sidecar 可独立存在：新建目录只建 L0（目录名即默认摘要），有实际产出后再建 L1。

### 1.2 生成与刷新

- **时机**：产出 skill 收尾（Phase 1 同步段）。
- **自底向上**：叶目录文件摘要 → 叶 L1 → 叶 L0（从 L1 的 Brief Description 提取）→ 父目录（聚合**子目录 L0 正文**；frontmatter 不入摘要输入，对齐 OV「嵌入白名单」精神——重建不改变摘要输入）。
- **稳定采样**：直接子项 > 32 时按「路径字典序取前 32」确定性采样；重复刷新取同样本。
- **滞后与刷新**：子目录内容变化 → 父目录 `pending_child_changes += 1`；`pending/total ≥ 0.10` 或直接子项 ≤ 32 时，下一次收尾刷新；未刷新时**可读但滞后**——不阻塞读取，禁止当作已同步使用。
- **写保护**：正文允许人工 `edit` 修订；frontmatter 的 `directory` / `generated_by` 不可改，改动即失效重建。

### 1.3 读取纪律

```
1. read .abstract.md（L0）→ 判断相关性
2. 相关 → read .overview.md（L1）→ 定位目标文件
3. 确认目标 → read L2 全文
```

- 全程记 `context_read` 事件（level=L0/L1/L2, why=决策目的）入 trace。
- 违例示例（禁止）：进目录后 `read` 全部 `.md`；`glob` 后逐个读全文。

---

## 2. 轨迹日志 trace.jsonl

### 2.1 事件 schema（每行一个 JSON 对象）

| event | 必填字段 | 说明 |
|---|---|---|
| `tool_call` | ts, tool, args_digest, exit_code, ms | `stderr_head`（非空时必填）；`side_effect`（写盘路径，有则必填）；外部 API 调用加 `nondeterministic: true` |
| `context_read` | ts, path, level, why | level ∈ L0/L1/L2；why 记决策目的 |
| `decision` | ts, what, basis[] | basis 引用**轨迹内已记录事件或已存在产物路径**（P1 自指闭环：决策依据必须可回溯） |
| `stage` | ts, skill, phase, status | status ∈ pending/in_progress/completed/failed；与 progress.json 互为校验 |
| `gate` | ts, gate, result, evidence | 门控判定（含 H2 审批结果、RSI 门控值） |

- `ts` 为 ISO 8601；`args_digest` 为参数摘要（≤120 字符，敏感值脱敏）。

### 2.2 写入纪律

- **只追加**：任何情况下不修改/删除已写入行；错误决策原样保留（rsi-evolver 原料）。
- 每次 decision / tool_call 失败 / stage 状态变化，**立即落盘**。
- 并行后台任务的 trace 写盘用**显式绝对路径**（HARNESS §2.2 实测教训）。
- 执行轮结束（commit Phase 1）后定稿复制入归档，原文可留存供续轮比对。

---

## 3. run-manifest

### 3.1 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `manifest_version` | int | 当前 1 |
| `run_id` | string | `<task_type>-<序号或日期>`，人类可读 |
| `skills[].slug / anchor` | — | pipeline 涉及的 skill 与版本锚定（hw_repo git 短 SHA） |
| `dirty` | bool | skills 目录有未提交变更时 true（须先提交或显式接受不可复现） |
| `pipeline` | string[] | 分诊结论的 skill 执行序列 |
| `parameters` | object | **影响行为**的参数（门控阈值/检索作用域/模型档位）；纯展示项不记 |
| `gates` | object | 本轮启用的门控及其阈值 |
| `retrieval` | object | `scope[]`（检索作用域目录）+ `tie_breaker`（固定 path-lexicographic） |
| `reconstructed` | bool | 补归档时 true（HARNESS §5.5），并附 `evidence[]` |

### 3.2 生成与锚定

- autopilot Phase 0 输出分诊结论后**立即**生成，先写 `.research/run-manifest.json`；
- `anchor` 取 skills 目录 git HEAD 短 SHA：`git -C <skills所在仓> rev-parse --short HEAD`；
- commit Phase 1 时复制入归档并补 `archived_at`。

---

## 4. 会话归档 commit

### 4.1 Phase 1（同步封存）

1. `.research/archives/` 不存在则创建；`NNN = 现有最大归档号 + 1`；
2. 复制 `run-manifest.json` → `archives/archive-NNN/manifest.json`（补 `archived_at`）；
3. 定稿 `trace.jsonl` 复制入归档；
4. 按 §6 命令生成 `artifacts.json`；
5. **no-op 判定**：本轮 trace 无新事件**且** artifacts 哈希与上一归档比对无变化 → 记 `skipped`（evolution-log 一行），不建归档目录。

### 4.2 Phase 2（收尾）

`summary.md` 固定格式（对齐 OV 会话摘要结构）：

```markdown
# 会话摘要（archive-NNN）

**一行总览**：[主题]：[意图] | [结果] | [状态]

## 分析
（关键步骤列表，含失败与转折，不粉饰）

## 核心请求与意图
（用户/上游的原始目标）

## 关键概念
（本轮涉及的核心概念，供后续 L0 检索命中）

## 待办
（未决项，衔接下轮 planning）
```

- 记忆提取：本轮 `experiences/` / `strategies/` 有写入 → 产出 `memory-diff.json`（§5）；
- `.done`：`{"done_at": "<ISO>", "phase2": "complete"}`。

### 4.3 崩溃恢复（对齐 HARNESS §2.4）

- 归档目录存在但无 `.done` → **重做 Phase 2**（摘要重生成幂等；memory-diff 重算）；Phase 1 三件套（trace/manifest/artifacts）不动。
- `.done` 存在但 Phase 1 三件套缺一 → 归档无效：保留现场，新开归档号 + errata 说明（P2：不改写、只增补）。

### 4.4 补归档（reconstructed）

适用于本协议生效**之前**的历史执行轮：

1. 从现存产物重建：`progress.json` / `evolution-log.md` / 产物文件 / git 历史 / `raw/` 原始返回；
2. manifest 必须含 `"reconstructed": true` + `"evidence": [依据文件路径...]`；
3. trace.jsonl 每行加 `"reconstructed": true`；只记**可从证据重建**的事件，粒度允许粗于实时记录；
4. summary 首行注明「追溯性归档，非实时记录」；
5. **禁止**补造实时 ts 伪装（ts 用重建时刻，原始时间进事件 `original_date` 字段）。

---

## 5. memory-diff.json（M3 写入审计，P5）

### 5.1 schema（对齐 OV memory_diff 结构）

```json
{
  "archive": "archive-001",
  "extracted_at": "<ISO>",
  "operations": {
    "adds":    [{"path": "memory/experiences/<slug>.md", "after": "<全文或结构摘要>"}],
    "updates": [{"path": "...", "before": "<全文；不可得时为 null 并加 before_note>", "after": "<全文>"}],
    "deletes": [{"path": "...", "deleted_content": "<全文>"}]
  },
  "skipped": [{"op": "...", "reason_code": "gate_rejected|approval_denied|dedup_merged|schema_invalid", "reason": "<一句话>"}],
  "summary": {"adds": 0, "updates": 0, "deletes": 0, "skipped": 0}
}
```

### 5.2 产出纪律（rsi-evolver 执行）

- distill/evolve **写入前**先快照目标文件 before，写入后取 after；
- proposed 但被门控/审批拒绝的操作进 `skipped`（带稳定 reason_code，禁止空 reason）；
- 协议前历史写入的 before 不可得 → `before: null` + `before_note: "协议前执行，首版未留快照，变更范围依据 evolution-log 重构"`——**诚实标注，不伪造快照**；
- 无任何变更时仍写**全零 diff**（证明「检查过」而非「没检查」）；
- diff 存于当轮归档目录；跨轮增量在新增归档中各自记录，不改写旧 diff（P2）。

---

## 6. artifacts.json（产物哈希清单）

生成命令（在 `.research/` 下执行；**排除** sidecar、progress.json、归档目录——sidecar 可从产物再生成，属投影非真源）：

```bash
python - <<'EOF'
import hashlib, json, os
out = []
for root in ["workspace", "memory"]:
    for dirpath, dirs, files in os.walk(root):
        for f in sorted(files):
            p = os.path.join(dirpath, f).replace("\\", "/")
            if "/.abstract.md" in p or "/.overview.md" in p or p.endswith("progress.json"):
                continue
            out.append({"path": p, "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest()})
out.sort(key=lambda x: x["path"])
json.dump(out, open("archives/archive-NNN/artifacts.json", "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print(f"{len(out)} files hashed")
EOF
```

- 清单按路径字典序排序（P4 tie-breaker 同源规则）。
- **回放验证**（HARNESS §2.5）：对清单重算哈希比对，全一致 → 快照成立；不一致项即回归定位点。

---

## 7. 验证清单

| 检查项 | 方法 |
|---|---|
| sidecar 三件可读且 L0 ≤256 字符 | `wc -c` + 读 frontmatter |
| freshness 与实际子项数一致 | 数目录项 vs frontmatter |
| trace 只追加无回写 | 轮内 diff 只增行 |
| manifest anchor 与 git HEAD 一致 | `git rev-parse --short HEAD` 比对 |
| artifacts 哈希可复核 | §6 命令重算比对 |
| 归档含 `.done` 且三件套齐全 | `ls archives/archive-NNN/` |
| memory-diff 与实际写入一致 | diff 内 path 均存在且内容匹配 after |
| 补归档标 reconstructed + evidence | grep manifest.json |
