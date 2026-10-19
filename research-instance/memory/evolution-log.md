# 进化日志（rsi-evolver）

## rsi-1（2026-10-19）：检索/摄取实现细节进化

- **触发**: v1 最小闭环暴露四短板（单源/摘要级/跨文献稀疏/refute=0）→ v2 改进轮真实执行中又暴露两个实现缺陷
- **reflect 要点**: ① 去重键不归一（版本号）致 3 条重复；② S2 硬重试无效（429×2）；③ `&` 后台落盘竞态致文件散落；④ arXiv 80 端口 301（v1）；⑤ OA 免费额度限制
- **evaluate（独立证据，非自评）**: v1/v2 真实 API 返回（raw/ 可复核）+ Gate Check 断言通过 + 缺陷复现-修复对照
- **evolve 变更**（commit `0ef82db`，git revert 即回滚）:
  - literature-miner/SKILL.md: arXiv HTTPS、S2 降级策略、OA 额度/倒排索引、Crossref 空响应重试、去重键版本号规范化
  - literature-scholar/SKILL.md: arXiv HTML 全文摄取路径 + 全文级 span/quantity 要求
  - HARNESS.md: 并行后台任务写盘绝对路径纪律
- **distill**: 2 条经验入库（multisource-retrieval-pitfalls / parallel-task-cwd-pitfall）
- **门控判定**: 通过——全部变更有独立执行证据，无自评分数依赖
- **遗留未决**: S2 引用图数据缺席；E-10 refute 定性待 KGHaluBench 全文核验；44 相关文献仅摄取 6 篇

## 干预轮 1（2026-10-19）：lit-retrieval-v2 诊断干预验证（L1-L6 + I1-I3 首次全链路）

- **触发**: 两大创新点机制落地（commit `15d600b`）后的验证轮——用 rsi-1 真实失败轨迹走通快速定位 + 分级干预闭环
- **诊断**: L1-L6 全链路（依赖图 8 节点 13 边，裁决 DE-1 去重键不归一 / DE-2 落盘竞态为决定性错误，S2 429 为被补偿失败，计划性冗余 0）
- **干预执行（H2 批准 3/3，真实重放）**: INT-1 ID 归一化（3/3，跨源 `2602.19643` 机制复现 + 新发现同源多查询重复）→ **Validated**；INT-2 绝对路径（对照 3/3 复现 + 实验 3/3 修复）→ **Validated**；INT-3 S2 限速策略（2 轮均正确终止于降级）→ **Validated**。PM=1.0（缺陷单元尺度）。Inconclusive=0
- **distill**: INT-3 增量入 multisource-retrieval-pitfalls（30s 间隔不够，降级阈值更激进）；INT-1/2 为既有经验的验证回链
- **协议进化**: intervention-protocol.md §4 补回溯性干预 PM 备选尺度（里程碑尺度分母失义的实测发现）
- **产物**: `workspace/diagnoses/lit-retrieval-v2-{deps.json,diagnosis.md}` + `interventions/lit-retrieval-v2-intervention-1.md`（含 replay/ 可复核脚本与原始返回）

## harness-v2 落地轮（2026-10-19）：可复现性协议重写 + 首个补归档

- **触发**: 评审结论——v1 HARNESS 可复现性机制不足；对标 OpenViking（上下文数据库）与 deepseek-harness（会话日志）重写
- **变更**: HARNESS.md v2——P1–P5 可复现性公理（模型可见⟺已记录 / 归档不可变 / 组合即配置 / 评分确定性 / 改动可审计）+ L0/L1/L2 目录 sidecar + 两阶段会话归档 + run-manifest + 回放验证（离线逐字/在线结构契约）+ 检索确定性协议 + LLM 非确定性诚实边界声明；新增 `_shared/session-archive.md` 六个操作协议；autopilot（manifest 固化 + commit 入口）与 rsi-evolver（memory-diff）同步
- **实证**: 4 目录 sidecar 落地（L0 均 ≤256 字符，freshness 与实际子项一致）；`archives/archive-001` 补归档（reconstructed: true——14 事件轨迹 + 60 文件真实 sha256 + memory-diff 诚实重建 before:null + .done）
- **门控判定**: 通过——机制映射有真实来源（OV/dsh 官方文档精读，非凭空设计）；实证全部可复核（哈希清单重算命令在 _shared §6）
- **遗留未决**: 本轮为文档工程轮，按轻量降级语义记本 log，archive-002 待下一次 autopilot 执行轮收编；sidecar 自动生成工具未脚本化（协议先行，执行靠 skill 收尾纪律）

## graph-ab-1 轮（2026-10-19）：G 路径协议 + 图锚定 vs 无图基线首证

- **触发**: 用户提问「为什么记忆不用 GraphRAG 形式——论断作 node 对减少遗忘幻觉应有效」→ 协议化 + 实证验证
- **协议**: HARNESS §4.6 图检索路径（G 路径，commit `a8df01f`）——L0 粗筛 → 图定位（种子+1跳确定性）→ 节点锚定生成（无锚不写）；外部图引擎（OV/向量库/GraphRAG 运行时）为可选加速层非依赖（零部署 + P4 兼容）
- **实证**: 同主题同材料对照——图路径 18/18=100% vs 无图基线 11/17=64.7%（严格，+35.3pp）；基线 4 broken 全部命中 LLM 综述典型幻觉形态（多源泛化 B4 / 来源混淆 B6 / 弱证据强化 B8 / 编造结论 B16）；判定三档逐条落盘 traceback.json
- **distill**: graph-anchoring-discipline 入经验库（diff 见 archive-002）；evolve 走代码演进（协议 commit）而非策略库，scope 未开
- **归档**: archive-002 **实时归档首例**（reconstructed: false，16 事件轨迹 + 65 文件哈希 + memory-diff + .done）
- **局限（诚实）**: 同一 agent 双路径非盲测；notes v2 增补已含图反哺（对基线有利，图仍胜出）；N=1 规模 17 节点
- **遗留未决**: 扩图后复测；traceback 独立人评抽查；四类滑变 → diagnosis-clinician 检测规则候选

## style-mimic-1 轮（2026-10-19）：第 12 个 skill 落地 + 首次画像提取实证

- **触发**: 用户「完整落地 + 实证」决策——调研确认「从用户 PDF 动态提取风格画像」市面零先例（embodied ★15 / humanizer ★2245 / lanqing ★5056 三生态均为预置手册或负向去味）
- **skill**: style-mimic 四件套（SKILL.md + 画像模板 + AI-tel 目录中英对照 + 双段 rubric）+ manifest 注册（phase: style 新轴 + pipelines.style；paper-writer consumes +style_profile）+ paper-writer 挂钩（基线稿/风格稿双版本 + 红线 diff + rubric W6）
- **实证**: kghalubench.txt 正文区间 [233,505) 段内清洗后 4401 词/215 句——prove×0（与「动词强度不超证据」天然对齐）、However 81% 句首（最强句法信号）、英式拼写 13:0、AI-tel 白名单 5 词（novel/comprehensive/leverage/extensive/numerous）+ 零注入 23 项；画像 + stats.json + 通用脚本三件入 style-profiles/（P1 可复现）
- **踩坑**: 首版统计整行剔除含 `\mathrm` 段 → 误删 20% 正文致 suggest/indicate=0 假象；修正为段内 LaTeX 清洗（经验 latex-fulltext-style-stats.md）
- **诚实边界**: Phase 2（风格应用校验）未执行——需 paper-writer 成稿后触发；人工印象「This+NP+V 高频」被机械统计纠正（实测 2 次）——防印象填数正是画像模板强制脚本统计的动因
- **归档**: archive-003（实时归档，单 skill 小轮完整六件套）

## 管线末端补齐轮（2026-10-19）：latex-adaptor / reviewer-panel / rebuttal-drafter 落地 + style-mimic 声明修正

- **触发**: 用户要求「调查不足→全都改了」——二轮调研（K-Dense ★52744 / paperjury ★1224 / latex-doc ★790 / journal-adapt ★762 / Rebuttal-Skill ★480 / lifecycle 42 skills）确认四缺口
- **修正（诚实优先）**: style-mimic 初版「市面无先例」声明不准确——journal-adapt（★762）已是「期刊语料→动态 skill」先例；差异化收窄为四点（任意样本/量化画像/红线隔离/HARNESS 归档）并公开修正
- **三新 skill**: latex-adaptor（cite-map 三向对账 = W3 红线延伸到 .tex；编译降级链诚实声明）/ reviewer-panel（声明-证据矩阵机械回接 + 锚回接审查防评审幻觉；review.json 直通 diagnosis 闭环）/ rebuttal-drafter（triage 三档 + 无证据不让步不反驳——反捏造红线延伸到 rebuttal 场景）
- **manifest**: phase 新增 production/review/rebuttal 三轴；diagnosis consumes +review_report；routing 丢 .tex→production、审稿意见→rebuttal
- **本轮无执行实证**（纯设计落地轮）：三 skill 首执行待 writing 管线成稿后触发（latex 转换/评审/rebuttal 依赖成稿输入）——按 §5.1 轻量记录，下次 autopilot 归档收编
- **commit**: 8d80883（11th，已推 SSH:443）

## 完善轮（2026-10-19）：三项「已有但不如市面」补强（cfef780）

- **触发**: 用户核对上轮调研报告第三节三条是否落地——诚实回答均未改，本轮补齐
- **paper-writer**: 一次组装 → 逐章迭代协调（学 PaperOrchestra）：信息依赖序起草（方法→实验→引言→结论→摘要）+ 跨章状态卡 paper-state.json（术语表/数字账本/符号/结论强度，后章必读先入卡再入文）+ 不一致回流修订（非就地硬改）迭代 ≤2 轮 + rubric W7
- **experiment-replicator**: 执行二态诚实声明（real 真跑全量留痕 run-manifest sha256 / protocol_only 只产协议包，「写了脚本≠跑了实验」）；与 AI-Scientist 运行时形态差距明示
- **调研误报修正**: 上轮「literature-miner 无 PubMed」结论错误——PubMed 支持早已存在（数据源表+参数枚举），调研时未读原文凭印象下结论；真实差距仅「默认源不含 pubmed，医学主题须显式指定」→ 已加源覆盖边界声明。教训：能力矩阵结论必须逐一核对 SKILL.md 原文
- **commit**: cfef780（12th，已推 SSH:443）

## 传播力补强轮（2026-10-19）：figure-mimic / slides-builder / doc-composer 落地（5a823d9）

- **触发**: 用户决策变更——为参赛五维（内容传播力/作品可用性）补绘图+PPT+文档三 skill；早前「不做绘图」判断翻译为设计约束（数据图代码生成永不变/概念图 H2 确认/降级诚实）而非推翻
- **对称设计**: figure-mimic 与 style-mimic 对称（视觉画像 ↔ 语言画像，同构三件套：观测/例证/指令）；F2 红线「生图模型不得画数据」= 反捏造红线的视觉层延伸
- **五维对齐**: 传播力轴（outreach: doc-composer 断言登记表 + C2 零升格）补齐后评审五维每维有 skill 支撑
- **提交约束发现**: 仓库 51 文件 > 赛事 30 文件限——打包阶段合并 references/裁剪（用户已定打包最后做）
- **commit**: 5a823d9（13th，已推 SSH:443）
