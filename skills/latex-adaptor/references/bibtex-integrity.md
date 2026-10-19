# BibTeX 完整性规则

> 被 `latex-adaptor` Phase 2 引用。refs.bib 的生成、校验与对账口径。

## 1. 生成来源纪律

- 条目**只从检索原始层生成**（literature/inbox 的 papers.json / raw/ API 返回），字段从原始 JSON 映射，**禁止凭记忆补字段**（题目记不清就回原始层查，查不到该字段留空并标 `field_missing`——缺字段的诚实引用好过编造的完整引用）；
- 正文未引用的文献不入 bib（.bib = 被引集合，非文献库全量镜像）。

## 2. 字段校验

| 检查 | 规则 | 违规处理 |
|---|---|---|
| 必填字段 | article: author/title/journal/year/(volume/pages)；inproceedings: author/title/booktitle/year；arXiv: author/title/year/eprint | 缺 → `field_missing` 标注，不静默编造 |
| DOI 格式 | `10.xxxx/...` 前缀模式 | 不匹配 → 剔除该 DOI 字段（错误 DOI 比没有更糟） |
| arXiv id | `NNNN.NNNNN` 或旧式 `cs/NNNNNNN`；`eprint` + `archivePrefix` 配套 | 同上 |
| 年份合理 | 1900 ≤ year ≤ 当前年+1 | 越界 → 标 `suspect_year` 人工核 |
| 转义 | & % # _ 在字段中转义 | LaTeX 编译前自动修复 |

## 3. 去重

- 同文多 key：合并保留规范 key，main.tex 中 `\cite` 全量替换并记 trace；
- 判重键：DOI > arXiv id > (作者姓 + 年份 + 标题前 8 词归一化)。

## 4. key 命名规范

`authorYEARkeyword`（如 `robertson2026kghalubench`）——首作者姓 + 年份 + 标题关键词；中文作者姓用拼音。全库唯一；冲突加序号后缀。

## 5. cite-map.json 对账（W3 在 .tex 世界的延伸）

```json
{"cite_key": "robertson2026kghalubench",
 "appears_in_tex": ["§1 段3", "§2 相关工作"],
 "backed_by": "claim_id C-kghalu-3 / inbox 条目 kghalubench",
 "status": "ok"}
```

三向对账：**正文 \cite 集合 = refs.bib 条目集合 = cite-map 条目集合**。不平衡形态：

| 形态 | 含义 | 处理 |
|---|---|---|
| 幽灵引用（tex 有 bib 无） | 编译断链 | 阻断：补条目或删引用 |
| 孤儿条目（bib 有 tex 无） | 死库存 | 从 bib 剔除 |
| 无锚引用（cite 有 claim_id 无） | 内容层断链 | 标 `unanchored`——内容问题回流 paper-writer，本 skill 不擅自补锚 |
