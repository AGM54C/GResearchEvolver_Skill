# 原子论断与四类原子关系（共享定义）

> 被 literature-scholar / literature-miner / diagnosis-clinician / survey-architect 引用。参考 AskChem、SciFact、Stored-Is-Not-Supported、SCIRIGOR。

## 节点：原子论断（atomic claim）

文献切分为**可独立核验的单一科学主张**。节点缺下列字段即证据资格不成立：

```json
{
  "claim_id": "C-<来源短名>-<序号>",
  "text": "在 400K、常压下，催化剂 X 使底物 Y 产率提升 12%",
  "literature": "<完整题名或 DOI>",
  "span": "§3.2, Table 2",
  "evidence": {
    "scope": "400K、常压、底物 Y",
    "quantity": {"value": 12, "unit": "%"},
    "source_role": "实验观测"
  }
}
```

- `source_role` 四选一：`实验观测 / 文献转述 / 假设 / 推论`。假设与推论**不得**充当已证事实。
- 同一对象在不同条件下的断言**必须拆成不同节点**（条件不合并，AskChem 核心纪律）。

## 边：四类原子关系

| 关系 | 含义 | 判定要点 |
|---|---|---|
| `support` | A 为 B 提供正向证据 | 需明确证据链，非「同主题」 |
| `refute` | A 与 B 冲突/反驳 | 需真冲突，非条件不同 |
| `condition` | B 仅在条件 A 下成立 | A 是 B 的适用范围/前提 |
| `source` | B 来源于/依赖于 A | A 是 B 的推导前件或数据来源 |

边 schema：`{"edge_id", "src", "dst", "relation", "evidence_span"}`。

## 硬边界（P0）

**图连通 ≠ 因果/支持**。GNN/图检索只做「候选子图召回 + 编码」，证据资格裁决走规则层（来源角色/有效期/依赖），交 diagnosis-clinician。