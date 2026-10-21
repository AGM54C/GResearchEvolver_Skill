# 小规模真实工具链检查

本记录仅用于算术与工具链集成检查，不是科学能力研究，也不构成专家科学认可。未联网，未调用命令执行工具。

## 项目与调用

project_status 实际返回项目 live-long，目标为 Test real long-project tools and stop for actual human review；policy.require_review=true，decisions=[]，reviews={}，memtx_revision=3。已存在图前提 holm-fixture-v1，指纹为 32a66a30f15dfc0a5b97d2a89b7068263832be0c4968b945515a9fa3bbbf3487。本次未重复写入图或 MemTX 前提。

实际调用 research_operation：

```json
{"operation":"adjust","arguments_json":"{\"pvalues\":[0.01,0.03,0.2],\"method\":\"holm\"}"}
```

真实工具返回如下（完整响应）：

```json
{"attempt_token":"1f18ff86b6574301b8faa163e49be79d","ok":true,"value":{"adjusted":[0.03,0.06,0.2],"assumptions":"valid p-values; BH needs independence or suitable positive dependence; Holm controls FWER","method":"holm"}}
```

## 结果与解释

输入顺序对应的 Holm 校正 p 值为 [0.03, 0.06, 0.2]。本例输入已升序排列；依次乘以 3、2、1，再取截至当前位置的累计最大值并限制在 1 以内，得到上述结果。这一算术解释与实际工具输出一致，不代表额外独立软件验证。

## 适用局限

- Holm 方法要求各原始 p 值在对应原假设下有效，并针对完整、适当界定的假设检验族控制族错误率（FWER）；不能修复无效 p 值、选择性报告或遗漏比较。
- Holm 的 FWER 控制不要求各检验独立。工具 assumptions 字段中关于 BH 独立性或适当正依赖的文字属于另一方法，不是本次 Holm 校正的前提。
- 未提供真实研究数据、假设检验族的科学定义或显著性阈值，因此仅记录数值变换，不作科学显著性或研究效应结论。p 值也不表示效应量或假设为真的概率。
- 单个三元素样例只能提供该路径的集成检查证据，不能证明实现对所有边界输入正确，也不能证明科学能力。

## 审查状态

下一步拟绑定并提交 stage=validation 的 report_stage，purpose=conclude，evidence=["results.md"]，review_required=false。该参数不取代项目 policy.require_review=true 的真实研究者审查门控。当前无真实研究者批准；结论暂未批准，等待控制器审查流程。本文件不声称报告已保存或门控已通过。
