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
cd ../../..

# 2. 归档哈希抽查（注意：Windows 下必须 -X utf8，否则中文路径被 GBK 误读产生假报错）
python -X utf8 -c "
import json,hashlib,os
SKIP={'.html','codeartsagent-llms.txt'}          # 有意未入库：原始 html（txt 已含清洗后全文）+ 无效残留
LIVE={'memory/evolution-log.md'}                  # 活文件：归档后已追加新轮进化记录（快照 vs 现行，属预期）
ok=skip=bad=0
for a in json.load(open('archives/archive-003/artifacts.json',encoding='utf-8')):
    if a['path'].endswith('.html') or os.path.basename(a['path']) in SKIP or a['path'] in LIVE: skip+=1; continue
    p=a['path'].replace('workspace/','workspace/').replace('memory/','memory/')
    h=hashlib.sha256(open(p,'rb').read()).hexdigest()
    ok+=h==a['sha256']; bad+=h!=a['sha256']
print(f'哈希一致 {ok} / 不符 {bad} / 预期跳过 {skip}（应 70 一致 + 0 不符 + 10 跳过 = 80 项）')"

# 3. 对照实验回查：traceback.json 里每条 broken 论断标注了原文位置，可人工核
```

> 说明：归档清单（artifacts.json）是归档时刻的全量快照（含 8 篇原始 html 与 1 个无效残留文件，本仓库有意未带入，故验证命令按 SKIP 跳过）；`evolution-log.md` 在归档后持续追加新进化轮记录，哈希与快照不符属预期——这正是「归档不可变（P2）+ 记忆可进化」的活例子。

## 与 skill 集合的关系

本实例由 `skills/` 中的 skill 产出（literature-miner → scholar → survey-architect / style-mimic / diagnosis-clinician / rsi-evolver …）；skill 定义看主仓库，本目录是它们跑起来的样子。
