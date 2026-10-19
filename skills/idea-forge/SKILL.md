---
name: idea-forge
description: IDEA 锻造（进化计算式）。生成大量候选 IDEA 种群，用多目标适应度（新颖性/可行性/评价边界/强基线/可证伪性/成本）打分，经锦标赛选择、精英保留、交叉与变异多代迭代，收敛到 Pareto 前沿，产出最优 top-k 候选。每个 IDEA 强制标注真值未知时的评价边界与强基线。触发条件：给定研究方向，要求"发散IDEA""候选idea""研究点子""选题""收敛最优方案"。
parameters:
  direction:
    type: string
    required: true
    description: "研究方向描述"
  population_size:
    type: integer
    default: 40
    description: "种群规模（初始候选 IDEA 数），建议 20-60"
  generations:
    type: integer
    default: 4
    description: "进化代数（筛选轮数），建议 3-6"
  elites:
    type: integer
    default: 8
    description: "每代精英保留数（直接进入下一代）"
  top_k:
    type: integer
    default: 5
    description: "最终输出的最优 IDEA 数"
  graph_path:
    type: string
    required: false
    description: "论断图路径，用于新颖性 gap 基准"
  restarts:
    type: integer
    default: 2
    description: "不同随机种子重启次数（规避局部收敛）"
  out_dir:
    type: string
    required: false
    description: "产物目录，默认 .codeartsdoer/.research/workspace/ideas"
---

# idea-forge Skill（进化计算式）

候选 IDEA 的**进化式生成与筛选**。不是一次发散就手工排序，而是像进化计算：**大量候选 → 适应度筛选 → 选择/交叉/变异 → 多代迭代 → Pareto 收敛**。

> **方法先例**：AI-Scientist v2（agentic tree search）、POPPER（序贯证伪）、aide-ml（把搜索当优化）。
> **约束（P0）**：每个 IDEA 必须标注「真值未知时的评价边界」+「强基线」，缺失则适应度 F3/F4 归零，不进入精英。

---

## 1. 适应度函数（多目标，详见 `references/fitness-rubric.md`）

六维，各 1–5 分，带权重（默认见 rubric）：

| 维度 | 含义 |
|---|---|
| F1 新颖性 | 与文献 gap / 近邻的距离，低重复 |
| F2 可行性 | 数据/方法/资源可及 |
| F3 评价边界 | 真值未知时能否评、缺什么 |
| F4 强基线 | 同预算下可比方法是否明确 |
| F5 可证伪性 | 有明确反驳条件 |
| F6 成本 | 资源/时间效率 |

综合适应度 = Σ(权重 × 分数)。**F3 或 F4 为 0 的个体直接淘汰**（硬约束）。

---

## 2. 工作流（进化循环）

### Phase 0：现状归纳（gap 基准）

从论断图 + 文献归纳：已知什么、争议在哪（refute 密集处）、证据缺口（source 断裂处）。产出 `gap-map.md`，作为 F1 新颖性的对照基准。

### Phase 1：种群初始化（第 0 代）

生成 `population_size` 个候选 IDEA，**刻意宽泛发散**（不同问题×不同方法×不同数据×不同粒度），沿「评估/诊断/改进」三条主线 + 随机扰动扩种。避免初期同质。

### Phase 2：适应度评估

对每个个体按 `fitness-rubric.md` 六维打分，记录 `gen-<g>.json`（个体 ID、六维分、综合分、淘汰理由）。

### Phase 3：选择 + 繁殖

- **精英保留**：前 `elites` 名直接进入下一代。
- **锦标赛选择**：从剩余个体随机抽 k=3，取最优者，重复填满种群。
- **交叉**：两个父代组合（问题×方法、方法×数据）。
- **变异**：改条件 / 换方法 / 调粒度 / 翻转假设。变异率随代数衰减（前期探索、后期收敛）。

### Phase 4：迭代收敛

重复 Phase 2→3，直到达到 `generations` 或连续 2 代综合分无提升（收敛）。用 `restarts` 个不同种子重启，规避局部最优。

### Phase 5：输出 Pareto 前沿 + top-k

- 对最终代做非支配排序，输出 Pareto 前沿（新颖性与可行性等多目标不可同时优化的个体）。
- 取综合分 top-k 作为最终推荐。

### Phase 6：诊断报告

```markdown
## 诊断报告（diagnosis）
| 条目 | 判断 | 置信度 | 依据 | 未决项 |
|---|---|---|---|---|
| 种群多样性 | 高/中/低 | 中 | 初始代个体相似度 | ... |
| 收敛性 | 已收敛/未收敛 | 中 | 连续代数适应度差 | ... |
| top-k 中 F3/F4 完整率 | 100% | 高 | rubric 打分 | ... |
```

---

## 3. 产物

```
out_dir/
├── gap-map.md                  ← 现状 gap 基准
├── gen-<g>.json                ← 每代种群 + 六维分（可复现）
├── pareto-frontier.md          ← Pareto 前沿
├── ideas/<ID>-<标题>.md        ← 最终 top-k 各一档（含评价边界+强基线+反驳条件）
└── ranking.md                  ← 进化历程 + top-k 排序
```

**每个最终 IDEA 固定字段**：核心问题 / 评价边界 / 强基线 / 新颖性风险（近邻查重）/ 反驳条件 / 六维适应度分。

---

## 4. Gate Check

- 每代有 `gen-<g>.json`（可复现）
- 最终 top-k 每个含「评价边界 + 强基线 + 反驳条件」（F3/F4 满分才入选）
- 已做近邻查重（不把 AskChem/AIDE²/SEAL 等已有方法包装成新发明）
- 附诊断报告（多样性/收敛性/完整率）

---

## 5. 运行机制（遵守 HARNESS.md）

- **工具调用**：打分脚本失败读 stderr 再重试（HARNESS §1.2）。
- **错误恢复**：E6 幂等——`gen-<g>.json` 落盘使每代可独立复现，中断后从最后一完整代续（HARNESS §2.2）。
- **人的介入**：H1 澄清——方向边界缺失时追问；H3 阻塞——达 `generations` 若误指标上升，暂停给「继续/停止」选项。
- **Agent Memory**：M3——distill 后记录「哪些变异算子在本领域无效」，供下轮进化检索（HARNESS §4.2）。

---

## 6. 技术参考对照

| 机制 | 参考 |
|---|---|
| 树搜索/优化式探索 | AI-Scientist v2、aide-ml |
| 序贯证伪（可测推论） | POPPER |
| 假设强度 vs 证据 | HypoKG |
| 条件/变量/关系分离 | DiscoveryBench |
| 进化算法范式 | 遗传算法（锦标赛/精英/Pareto/变异衰减）|