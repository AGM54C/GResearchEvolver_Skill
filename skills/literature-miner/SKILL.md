---
name: literature-miner
description: 文献矿工。自主联网检索学术文献：按研究主题生成检索式，跨多源（arXiv / Semantic Scholar / Crossref / OpenAlex / PubMed）并发检索，去重、相关性排序、获取元数据与全文，产出结构化文献清单并回接科学论断图。触发条件：给定研究主题/关键词，要求"找文献""检索论文""搜集相关研究""补充文献""查最新工作"。
parameters:
  query:
    type: string
    required: true
    description: "研究主题或关键词"
  sources:
    type: string
    default: "arxiv,semanticscholar,crossref,openalex"
    description: "逗号分隔的数据源：arxiv / semanticscholar / crossref / openalex / pubmed"
  max_results:
    type: integer
    default: 30
    description: "每源最大返回数"
  year_range:
    type: string
    required: false
    description: "年份范围，如 2023-2026"
  out_dir:
    type: string
    required: false
    description: "产物目录，默认 .codeartsdoer/.research/workspace/literature/inbox"
---

# literature-miner Skill

自主文献检索。是 `literature-scholar`（摄取并建图）的**前置**：miner 负责「找到对的东西」，scholar 负责「吃进去变成论断图」。

> **P0 反捏造（遵守 `../_shared/anti-fabrication.md`）**：必须真实调用下列公开 API，检索结果带真实 URL/DOI/arXiv ID。检索失败或空结果，输出 `EVIDENCE_MISSING`，**绝不编造文献**。禁止生成不存在的题目/DOI/作者。
>
> **验收标准**：检索按 `references/retrieval-qa-rubric.md` 打分；R2（真实性）= 0 → 整次检索作废。

---

## 1. 数据源（真实 API，禁止模拟）

| 源 | Endpoint 模式 | 返回 | 特点 |
|---|---|---|---|
| arXiv | `https://export.arxiv.org/api/query?search_query=all:<q>&start=0&max_results=<n>` | Atom XML | 预印本，含摘要；**必须 HTTPS**（80 端口 301 强制跳转，实测） |
| Semantic Scholar | `https://api.semanticscholar.org/graph/v1/paper/search?query=<q>&limit=<n>&fields=title,abstract,url,year,authors,citationCount,externalIds` | JSON | 带引用数、DOI/arXivID；**未认证限速严格（实测连发 429）**：串行调用+间隔，失败 2 次即降级缺席，勿硬重试 |
| Crossref | `https://api.crossref.org/works?query=<q>&rows=<n>&filter=from-pub-date:<y>` | JSON | 官方 DOI 元数据；偶发空响应，重试一次即恢复 |
| OpenAlex | `https://api.openalex.org/works?search=<q>&per-page=<n>` | JSON | 免费、字段全、概念标签；**无 key 时共享 IP 每日免费额度（约 $0.10）**，高频调用需申请 API key；摘要为倒排索引需重建 |
| PubMed | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=<q>` → `esummary` | XML | 生物医学 |

**源覆盖边界声明**：默认源（arxiv/semanticscholar/crossref/openalex）覆盖 CS 与交叉学科。**生物医学主题必须显式 `sources` 含 `pubmed`**——PubMed 是医学主库而 arXiv 几乎无医学文献，医学 query 用默认源会系统性漏检；此为已知边界（显式声明），非静默缺陷。诊断报告须记录本次实际启用的源清单。

## 2. 工作流

### Phase 0：检索式生成

- 把 `query` 扩展为多个检索式（同义、子主题、方法名、评测名），覆盖不同角度。
- 标注每个检索式的意图（如「综述类」「方法类」「评测类」）。

**Gate Check**：≥3 个检索式，覆盖「综述/方法/评测」三类。

### Phase 1：多源并发检索

- 对每个检索式 × 选定源，真实发起 API 请求（失败返回 `{exit_code, stderr}`，遵守 HARNESS §1.2）。
- 汇合 raw 结果，记录每条的**真实 URL/DOI/arXiv ID**。

**Gate Check**：每条结果带真实外部 ID；无 ID 的结果丢弃。

### Phase 2：去重

- 按 DOI > arXiv ID > 规范化 title 依优先级去重。**arXiv ID 先规范化去版本号**（`2602.19643v1` → `2602.19643`）：arXiv API 返回带版本后缀而 OpenAlex DOI 提取不带，不归一会致同一文献重复入库（实测教训）。同一文献被多源/多检索式命中时 sources 去重追加，并同步维护 DOI 与 arXiv ID 双键索引。

### Phase 3：相关性 + 新颖性排序

- 相关性：标题/摘要与 `query` 的匹配度。
- 新颖性：引用数、年份、与已有论断图（若存在）的覆盖差异——**优先召回论断图中没有的新证据**。

### Phase 4：元数据 + 全文获取

- 开放获取（OA）→ 尝试全文；否则保留摘要 + 链接。
- 记录获取状态：`fulltext / abstract_only / paywalled / EVIDENCE_MISSING`。

### Phase 5：清单 + 回接 + 诊断报告

产物 `literature/index.md`（题名 / 作者 / 年份 / DOI / 摘要 / 来源 / 全文状态 / 相关性分）。

回接：产出的文献清单可作为 `literature-scholar` 的输入（`input` 参数直接指向本清单）。

---

## 3. 产物

```
out_dir/
├── queries.md            ← 检索式及意图
├── raw/<source>.json     ← 各源原始返回（可复核）
├── index.md              ← 去重排序后的文献清单
└── report.md             ← 诊断报告
```

---

## 4. Gate Check

- 每条结果带真实外部 ID（无 ID 丢弃）
- 无编造文献（可核查 raw/ 与 index.md 一致性）
- 附诊断报告（含检索覆盖率、去重数、全文获取状态）

---

## 5. 运行机制（遵守 HARNESS.md）

- **工具调用**：API 失败读 stderr 后换源重试，≤2 次原样（HARNESS §1.2）。
- **错误恢复**：E1 重试 + E2 降级（某源不可用 → 换 OpenAlex 兜底）+ E3 隔离（单源失败不阻塞）。
- **人的介入**：H2 审批——批量下载大文件/全文前批准（HARNESS §3.3）。
- **Agent Memory**：M2 写 `index.md`；检索前读已有 `graph.json` 避免重复召回（HARNESS §4.2）。

---

## 6. 技术参考对照

| 机制 | 参考 |
|---|---|
| 多源检索 + 计划 | deer-flow、gpt-researcher（planner/executor）|
| 高精度语料 QA | paper-qa（FutureHouse）|
| 引用图/新颖性 | Semantic Scholar Graph API、OpenAlex 概念标签 |
| MCP 参考实现 | arxiv-mcp-server |