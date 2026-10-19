---
name: literature-monitor
description: 对保存的检索式和文献库做增量更新，区分新增、版本变化和撤稿信号，产出本地研究摘要。
---

保存检索式、领域/日期、分页限额与上次游标；使用 literature-miner 实际获取元数据。定时任务由已授权宿主调度，不声称此技能自身持续后台运行。

`tool monitor` 按 DOI/稳定 ID 比较内容指纹，保留历史；新/变更/撤稿信号分别列出，暂未出现在限页搜索不等于删除或撤稿。日期、来源和分页是否完整写入摘要。

优先复核改变当前 claim/novelty/设计假设的记录，并提出影响评估。交付本地 digest 与 library delta；邮件、Slack、发布或自动订阅另需用户授权。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。
