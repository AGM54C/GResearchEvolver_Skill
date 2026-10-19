# AI-tel 目录（负向清单 + 中文版）

> 用途：Phase 0 交叉核对（样本含 → 画像照录标「样本特有」；样本不含 → 生成零注入）+ Phase 2 注入检查（生成稿中的 AI-tel 必须全部在样本白名单内）。
> 来源：academic-humanizer Layer 1-2 目录（实测有效、社区验证 ★2245）+ 中文学术 AI 腔扩展（humanizer-zh-academic 方向 + 本项目补充）。原则：**宁可漏学，不可错加**。

## 1. 通用 AI 腔词汇（样本不含则零注入）

| 英文 | 中文对应 |
|---|---|
| delve, underscore, intricate, tapestry, testament, pivotal, showcase, foster, leverage (filler), realm, seamless, landscape (abstract) | 深入探讨（滥用）、赋能、抓手、着力点、新篇章 |
| marking a pivotal moment / a testament to | 具有里程碑意义 / 彰显了 |
| rich / vibrant / groundbreaking | 丰富的（空洞义）/ 突破性的（无对照时） |

## 2. 过度声明（over-claiming）

| 类型 | 英文 | 中文 |
|---|---|---|
| 动词越界 | prove / establish / guarantee（实证工作只应 show / provide evidence） | 证明 / 确保（实证只应 表明/提示） |
| significance hype | paves the way for / opens new avenues / sheds light on / of paramount importance / bridges the gap | 为...奠定基础 / 开辟了新途径 / 具有重要意义 / 填补了空白 |
| 空洞强调 | extensive/comprehensive experiments, a wide range of, numerous, various（无数/大量/广泛） | 大量实验 / 丰富的数据集 / 全面的（无数值时） |
| novelty padding | novel >1 次/节、to the best of our knowledge、for the first time | 首次提出（重复）、据我们所知、全新的 |

## 3. 公式化结构

| 类型 | 英文 | 中文 |
|---|---|---|
| 公式化 opener | "In recent years, X has attracted increasing attention" / "With the rapid development of..." | 近年来，X 受到越来越广泛的关注 / 随着...的快速发展 |
| 连接词滥用 | 连续句首 Moreover/Furthermore/Additionally | 此外/另外/与此同时 连续句首堆叠 |
| 排比填充 | rule-of-three padding | 不仅...更是...还...（三连排比凑节奏） |
| 引用倾倒 | Many methods exist [3,7,9,12,15]（不说明为何引） | 已有大量研究[1-15] |
| 负向平行 | not just X, but Y | 不仅仅是X，更是Y |

## 4. 微观痕迹

| 类型 | 说明 |
|---|---|
| em-dash 滥用（en） | 破折号成段插入——AI 高频痕迹；样本不用则零注入 |
| "-ing" 尾巴 | "..., highlighting/showcasing..." 假深度尾句 | ..., 这凸显了... |
| copula 回避 | serves as → is | 作为...（滥用时） |
| 空转填充词 | it is worth noting that / in order to | 值得注意的是 / 为了（冗余时） |
| 优雅变体 | 同一概念轮换同义词（model → framework → approach → paradigm） | 同一概念轮换叫法 |
| 句长失控 | 从句堆叠超长句 | 多重定语嵌套长句 |

## 5. 裁决规则

1. **画像忠实优先**：目标样本自身包含某 AI-tel 特征（如作者就爱用 delve）→ 画像照录，生成按样本执行（标 `[样本特有：模仿优先于去味]`）——本 skill 的职责是模仿不是纠偏。
2. **零注入**：样本不含的特征，生成稿出现即 Phase 2 不通过（注入检查）。
3. **内容红线永不让位**：即便样本用 prove，我们只有部分验证的证据时仍按证据强度选词（SKILL.md §1 冲突裁决）。
