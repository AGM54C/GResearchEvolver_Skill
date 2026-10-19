# 检索式与意图（literature-miner，v2）

| 检索式 | 意图 | 源（v2） | 命中 |
|---|---|---|---|
| all:LLM hallucination survey | 综述类：LLM 幻觉综述/全景 | arXiv / OpenAlex / Crossref / S2 | 8+8+8 / S2 降级 |
| all:hallucination detection large language models | 方法类：幻觉检测方法 | arXiv / OpenAlex / Crossref / S2 | 8+8+8 / S2 降级 |
| all:hallucination benchmark evaluation LLM | 评测类：幻觉基准与评测 | arXiv / OpenAlex / Crossref / S2 | 8+8+8 / S2 降级 |

- 原始返回留存于 `raw/`（arxiv-\*.xml / oa-\*.json / cr-\*.json，可复核）
- 检索协议：HTTPS（v1 实测 HTTP 80 被 301 强制跳转，按 HARNESS E2 修正后重发成功）
- v2 源状态：S2 三式两次 429 → 降级缺席（EVIDENCE_MISSING）；Crossref method 式空响应重试成功；OA 无 key 共享额度（响应头 notice 实录）
- 去重：三级键（arXiv ID 规范化去版本号 > DOI > 规范化 title），合并后 57 篇
