# 文献清单（多源检索去重排序，v2）

## 检索源状态（2026-10-19）

| 源 | 检索式 | 状态 | 命中 |
|---|---|---|---|
| arXiv | 综述/方法/评测 3 式 | ✅（HTTP 301 强制 HTTPS，修正协议后成功） | 24 条（去重后 21） |
| OpenAlex | 同 3 式 | ✅（注意：无 API key 时共享 IP 免费额度） | 24 条 |
| Crossref | 同 3 式 | ✅（method 式首试空响应，重试成功） | 24 条 |
| Semantic Scholar | 同 3 式 | ❌ 429 限速（两次尝试）→ 按 HARNESS E2 降级缺席，**EVIDENCE_MISSING** |

- 原始返回留存于 `raw/`（arxiv-\*.xml / oa-\*.json / cr-\*.json），可复核
- 全文留存于 `fulltext/`（hallulens / kghalubench / lifecycle，arXiv HTML 提取）

## 去重与排序

- 三级去重键：arXiv ID（规范化去版本号）> DOI > 规范化 title
- 合并去重后 **57 篇**（修复版本号键不一致缺陷：arXiv API 带 `v1` 后缀 vs OpenAlex DOI 无版本，曾致 3 条重复）
- 相关性 ≥5 分 **44 篇**；多源交叉验证（≥2 源命中）**4 篇**

## Top 相关文献（前 15）

| # | 题名 | 年份 | 源 | 引用 |
|---|---|---|---|---|
| 1 | HalluLens: LLM Hallucination Benchmark | 2025 | arxiv+crossref | 0 |
| 2 | Mitigating Multimodal Hallucination via Phase-wise Self-reward | 2026 | arxiv | 0 |
| 3 | Reducing LLM Hallucinations with Knowledge Graphs: A Survey | 2026 | openalex | 0 |
| 4 | Hallucinations in LLMs: A Lifecycle-Based Survey | 2026 | arxiv | 0 |
| 5 | KGHaluBench: A Knowledge Graph-Based Hallucination Benchmark | 2026 | arxiv+openalex | 0 |
| 6 | Hallucination Detection in LLMs with Metamorphic Testing | 2025 | openalex | 27 |
| 7 | Detection and mitigation of hallucination in LLMs | 2025 | openalex | 0 |
| 8 | Probabilistic distances-based hallucination detection in LLMs with RAG | 2025 | arxiv | 0 |
| 9 | Distorted or Fabricated? A Survey on Hallucination in Video LLMs | 2026 | openalex | 1 |
| 10 | Hallucination Detection and Evaluation of LLMs | 2025 | openalex | 0 |
| 11 | HalluBench: A Multi-LLM Benchmark for Hallucination Evaluation | 2026 | openalex+crossref | 0 |
| 12 | THaMES: An End-to-End Tool for Hallucination Mitigation and Evaluation | 2024 | arxiv | 0 |
| 13 | Hallucination Detection with Small Language Models | 2025 | arxiv | 0 |
| 14 | Can LLMs Lie? Investigation beyond Hallucination | 2025 | arxiv | 0 |
| 15 | OpenHalDet: A Unified Benchmark for Hallucination Detection | 2026 | arxiv | 0 |

完整清单（含 DOI/摘要/相关性分/来源）见 `papers.json`；检索式与意图见 `queries.md`。
