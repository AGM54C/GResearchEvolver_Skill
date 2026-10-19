# 研究实例：LLM 幻觉方向（真实运行数据）

> 这不是构造的 demo——是 GResearchEvolver 首个研究案例「LLM 幻觉」的真实运行轨迹：检索了什么、建了什么图、跑了什么对照实验、踩了什么坑、蒸馏出什么经验，全部原始落盘。

## 推荐阅读顺序（15 分钟理解系统）

1. **[memory/evolution-log.md](memory/evolution-log.md)** —— 5 轮进化日志：每轮「触发→做了什么→踩了什么坑→归档在哪」，系统的成长史
2. **[workspace/survey/graph-ab-1/result.md](workspace/survey/graph-ab-1/result.md)** —— 核心对照实验：图锚定 18/18 vs 无图基线 11/17，4 条坏论断逐条可抽查（traceback.json）
3. **[archives/archive-002/summary.md](archives/archive-002/summary.md)** —— 上述实验的实时归档：17 事件 trace + 66 文件哈希清单
4. **[workspace/literature/graph.json](workspace/literature/graph.json)** —— 30 节点论断图本体（原子论断 + 支持/反驳/条件/相关四类边）
5. **[workspace/paper/style-profiles/kghalubench-style-profile.md](workspace/paper/style-profiles/kghalubench-style-profile.md)** —— 风格画像实证：4401 词样本的量化风格档案，重跑 style_stats.py 数值一致

## 目录说明

```
├── archives/          三轮归档（HARNESS §5 两阶段归档协议产物）
│   ├── archive-001/     补归档（reconstructed: true——协议前的轨迹诚实补录）
│   ├── archive-002/     首次实时归档（graph-ab-1 对照实验轮）
│   └── archive-003/     style-mimic 画像提取轮
│       每轮含：trace.jsonl（逐事件）/ manifest.json（参数+gate）/ artifacts.json（sha256 清单）
│              / memory-diff.json（本轮经验库变更）/ summary.md / .done
├── memory/
│   ├── experiences/     经验库（4 条蒸馏经验：图锚定纪律/LaTeXML 清洗/多源检索坑/并行任务坑）
│   └── evolution-log.md 进化日志（rsi-1 → 干预轮 → harness-v2 → graph-ab-1 → style-mimic-1 → …）
└── workspace/          研究工作区（目录级 sidecar：.abstract.md L0 / .overview.md L1）
    ├── literature/       检索+建图产物：inbox/（queries/raw 原始层/papers.json 去重清单）
    │                    entries/（6 篇精读条目）notes/（6 份《我的想法》）graph.json（30 节点图）
    ├── diagnoses/        lit-retrieval-v2 诊断（依赖图 L1-L6）+ 3 个干预验证（含 replay/ 可复核重放）
    ├── survey/graph-ab-1/  对照实验五件套（subgraph/graph-path/baseline-path/traceback/result）
    └── paper/style-profiles/  kghalubench 风格画像三件套（画像/stats/通用脚本）
```

## 怎么验证「真的可复现」

```bash
# 1. 重跑风格统计：与 kghalubench-stats.json 逐数值一致（E6 幂等）
cd workspace/paper/style-profiles
python style_stats.py ../../literature/inbox/fulltext/kghalubench.txt 233 505

# 2. 抽查归档哈希：artifacts.json 里的 sha256 与对应文件实算值一致
python -c "import json,hashlib; arts=json.load(open('../../archives/archive-002/artifacts.json')); print(sum(1 for a in arts if hashlib.sha256(open('../../'+a['path'],'rb').read()).hexdigest()==a['sha256']), '/', len(arts))"

# 3. 对照实验回查：traceback.json 里每条 broken 论断标注了原文位置，可人工核
```

## 与 skill 集合的关系

本实例由 `skills/` 中的 skill 产出（literature-miner → scholar → survey-architect / style-mimic / diagnosis-clinician / rsi-evolver …）；skill 定义看主仓库，本目录是它们跑起来的样子。
