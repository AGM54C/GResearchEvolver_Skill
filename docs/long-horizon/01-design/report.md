# 长程科研 Agent：设计与代码来源

## 为什么这样做

长任务的困难不仅是上下文长度。来源会修订，实验结果会延迟，研究者会改方向，多次续接还可能重复花预算或执行动作。本轮在既有 Agent、DAG、SQLite/CAS、科研图谱与受控 RSI 上增加持久项目层，不另造一个实验执行器。

用户明确要求复制 MemTX 的代码。因此采用上游执行核心，保持原文件字节不变；项目适配层承担持久化和科研约束。此前的 19 篇调研材料提供设计线索；这里不把阅读、哈希核验或接口测试当成论文实验复现。

## 实际参考与采用情况

| 来源及固定版本 | 实际查看内容 | 本项目处理 |
|---|---|---|
| [MemTX `4e1124c`](https://github.com/lxy1134/MEMTX_/tree/4e1124ccd5fd384857463020e3497aa73ec93be6) | manager、schema、状态机、冲突检测、依赖图、基类、mock 声明及 README | 原样复制 9 个文件；实际调用 begin/stage/commit/retrieve/abort 等原方法。未复制 benchmark 数据或声称复现其指标 |
| [DeepRewind `9282f0f`](https://github.com/AmirAbaskohi/DeepRewind/blob/9282f0f2800aca31fdf5227a75fe8e382986ca9d/src/open_deep_research/world_model_rollback.py) | world_model_rollback、epistemic_graph | 参考类型化依赖修复与替代支持路径；本项目由上游 MemTX 执行撤回，科研关系由适配层投影。没有复制其回滚算法 |
| [GRACE `9f170a1`](https://github.com/RedMind-Research/GRACE/tree/9f170a1436a4c4d13a9f96963e8ac7da26ebf3e3) | graph/neighborhood、validation、reproduction/tau2_telecom/harness/attempt_ledger | 参考操作前预留、结果后结算及结构检查；沿用本项目 SQLite 事务与监督器，不引入它的 Pydantic 执行栈 |
| [Slipstream `05d48f4`](https://github.com/chenzhuofu/slipstream/tree/05d48f4ddf4fbab146f95b49f802db26e303e6f4) | 论文调研与仓库 baseline `agents/default.py` | 未复现异步轨迹判别／压缩算法。这里使用确定性归档与交接，明确区别 |
| [JANUS `40f8d7f`](https://github.com/bilemond/JANUS/tree/40f8d7ff90fea070675744c1d0ebcb6d1ee5a26d) | README 方法与能力声明 | 采用“先记录预测、再记录实际结果”的经验结构；该版本未提供可接入的完整实现，本项目未训练 world model |

DeepRewind 为 MIT，GRACE 为 Apache-2.0，Slipstream 为 MIT；它们没有被复制进产品。MemTX 在上述提交没有声明许可证，保留 `NOASSERTION`，不推定为 MIT。具体清单见 [第三方说明](../../../skills/_shared/THIRD_PARTY.md) 和 [上游清单](../../../skills/_shared/vendor/memtx/UPSTREAM.json)。

## 方法与取舍

1. **项目是长期账本。** 目标、约束、真实人工决定、研究条目、预测／结果、报告索引、实验回执与预算独立于会话上下文保存。每次更新生成 CAS 快照和事件。
2. **上下文交接保留原文入口。** 只在所有调用结算、没有待审决定时归档；复制人工反馈、未决信息、材料哈希和当前项目状态。原轨迹可分页读取。如果必保留信息过大则停止，不能悄悄删除约束。
3. **科学动作绑定具体前提。** 节点内容哈希、图快照、MemTX 快照、研究者决定及实际条件一起约束动作。图是 prerequisite → consumer；相关／同题／引用等关系不自动作为因果依赖。多条支持边默认共同需要，只有显式 `support_sets` 才表示可替代的支持组合。
4. **实际使用 MemTX。** 原 manager 决定事务状态与撤回。适配层加强原始检查：动作所依赖的每条前提及祖先都必须可用，不能拿无关的 action_safe 记忆“借通行证”；快照读取不能混入稍后提交的记录。
5. **预算贯穿续接。** 执行前与 Agent 意图在同一个事务中预留，结算与回执一起提交。模型请求／输入字符／输出上限保守计费；未知用量不退款。工作流另预留其声明成本；不能把这些数值冒充提供方账单。
6. **等待真实结果。** Agent 只等待已登记的现有 DAG；本地／SSH 运行器仍是实际执行器。观察器读取持久回执而不调用模型。失败或人工阶段审阅会回到真人。
7. **经验不直接变成策略。** 带预测、结果和证据的条目可作为改进提案来源。仍需冻结基线、实际评估、研究者审阅和显式版本采用；执行中的权限与评分器不自行改写。

## 需要研究者判断的事项

默认开启科学结论的实际人工审阅。探索报告可以先写，但不能凭它标记科学交付完成。研究者应确认来源独立性、支持组合、适用条件、测量是否有效，以及预测与真实结果是否值得产生改进提案。

没有加入“自动无限研究”承诺；此版本属于**有界长程执行与人工监督的受控进化**。可以继续扩展任务范围，采用新策略仍有明确边界。
