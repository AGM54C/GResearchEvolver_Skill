---
name: reference-manager
description: 导入、去重、验证和导出科研文献库，保留 Zotero 标识、笔记、附件元数据、引用来源与更新状态。
---

`import` 支持 CSL JSON、RIS、BibTeX 字面量、EndNote tagged/XML、PubMed nbib/XML。保留原文件文本/哈希、原始字段及导入索引。复杂 BibTeX 宏需完整解析器规范化，不能静默丢字段。

`dedup` 只自动合并相同 DOI 且标题无冲突的记录，alias 保存全记录；DOI 相同但标题不同保留待裁决。无 DOI 的近似题名匹配只是建议。区分预印本/正式版/勘误/撤稿通知。

`citation` 核验 Crossref 元数据并保存原响应。未发现撤稿标志返回 unknown；进一步核对 publisher/Crossmark、通知和日期，不能把 absent 当 clean。引用存在仍需原文 entailment 检查。

`zotero` 从 users/groups 库读取，密钥来自环境变量，保留 notes/attachments/parent keys/version 原始元数据；不自动写库或下载附件。`export` 输出 CSL/RIS/BibTeX 并附完整 preserved.json，明确目标格式字段损失。

`notes` 生成带稳定身份映射和父子链接的 Obsidian/Markdown 版本目录，保留笔记、批注、附件元数据和完整 records.json；不是远端双向同步。来源更正/撤稿后，用 `invalidate` 标记所有可达下游需复核，保留原始证据与旧裁决；引用被撤稿研究作为研究对象可有不同语义，不一概删除。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。

受管阶段遵循 [阶段报告、科研讲解与受控进化协议](../_shared/human-guided-research.md)：说明为什么这样做、具体方法与结果；由 runtime 保存版本化 report.md，按需调用 research-explainer，记录研究者的实际反馈并落实到暂停、修改分支或后续执行。改进本技能时使用 `capability-freeze/propose/evaluate/review/activate`，目标为 `skill:reference-manager`；未经冻结评估及研究者接受，不把候选标记为已采用或能力提升。
