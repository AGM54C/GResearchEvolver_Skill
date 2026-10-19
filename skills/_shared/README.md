# `_shared/` — 共享定义层（非 skill）

本目录**不是 skill**：没有 `SKILL.md`，不会被 skill 加载器注册。它存放被 ≥2 个 skill 引用的**定义层**内容，避免复制漂移。

## 治理规则

1. **提升条件**：仅当 ≥2 个 skill 需要同一内容时才放到这里。
2. **放定义层，不放动作层**：多个 skill 共享同一套词汇/分类/模板，但各自在其上应用**不同的动作**。
   - 例：`diagnosis-template.md`（诊断报告格式）被 diagnosis-clinician / survey-architect / idea-forge / literature-miner 共享，但每个 skill 的判定逻辑各不相同。
3. 引用方式：`../_shared/<file>`（相对路径）。

## 文件清单

| 文件 | 内容 | 被谁引用 |
|---|---|---|
| `atomic-relations.md` | 原子论断节点 schema + 四类原子关系 | literature-scholar / literature-miner / diagnosis-clinician / survey-architect |
| `diagnosis-template.md` | 诊断报告五列表格 + 分级支持标签 | 所有 L2 产出 skill |
| `intervention-protocol.md` | 干预三级类型学（I1–I3）+ 判定四类 + Progress Made + 蒸馏接口 | diagnosis-clinician / research-autopilot / rsi-evolver |
| `anti-fabrication.md` | 反捏造红线 + 占位符约定 + 分级支持 | 所有 skill |

> **维护**：新增共享内容时先问「是否 ≥2 个 skill 需要」，否则留在各自 skill 目录内。