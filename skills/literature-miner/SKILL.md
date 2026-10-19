---
name: literature-miner
description: 检索可追溯的学术元数据与全文来源，保存检索式、分页范围和原始响应。用于找文献、查新和补充证据。
---

围绕问题建立同义词、邻近术语、反例与竞争解释的检索式；按领域选择数据库。医学可用 Europe PMC/PubMed 索引，但不声称覆盖 Embase、注册试验或付费数据库；需要时导入人工检索记录。

调用 `tool search` 的 Crossref、OpenAlex、Semantic Scholar、Europe PMC、arXiv 适配器；保留 raw、query、date、pages、pagination_complete。服务失败如实报告，不以模型记忆填充检索结果。限页结果不能称系统穷尽。

用 reference-manager 去重并检查 DOI 元数据；标题近似仅作为待审候选。区分 abstract-only、full_text、unavailable。已有本地全文可直接摄取，不必为了仪式化检索重新联网。引用网络追踪应记录每一跳与停止条件。

交付检索日志、记录库、相关性及排除理由、缺口；需要新颖性判断时建立 claim-level 最近邻矩阵和反证搜索，运行 `tool novelty`。有年代限制的查新只能证明已查范围内的差异。

本地全文用 `local-index/local-search` 做可定位的 BM25 检索，可显式加入跨语言别名；已有实际生成的向量时可做余弦与 RRF 混合排序，固定 embedding_model/version 与生成依据，不伪造语义向量。来源改变后索引会拒绝继续使用，需重建。公开 API 有有界缓存与瞬时错误退避；最新动态检索可设 cache_seconds=0。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。
