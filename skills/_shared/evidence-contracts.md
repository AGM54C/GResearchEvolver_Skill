# 证据与写作契约

所有 path 均为指定 root 内的 POSIX 相对路径；sha256 对原字节计算。标识存在/哈希正确/引文匹配只是可追溯性，不自动支持语义。

## 来源与图

`pdf` 生成 source.pdf、source.json、page-XXXX.txt。source 节点含 id/type=source/path=source.pdf/sha256/extraction=source.json；evidence 边引用 page-XXXX.txt 的 path/sha256/quote/page。验证器核查 extraction 确实对应 PDF 哈希和该页文本。

data、code、result 节点含 id/type/path/sha256。claim 含 id/type/text/scope/certainty/status，可附 quantities（最多一个），数量需 value/metric/condition/unit/run。多个数值或条件拆多个 claim。

执行关系：data/source/result → code 的 used_by，code → result 的 produces，source/result → claim 的 supports/contradicts，claim → claim 的 qualifies，以及 claim/source → claim 的 motivates。后两类不是事实支持。

每条支持/反驳边含 id/from/to/relation/evidence；adjudication 含 status/reviewer/rationale/scope_checked。只有有 accepted 支持的 claim 才可声明 verified；仍应在报告说明该状态是记录的裁决，不是绝对科学真值。source_role、自然语言 semantic_relation、反例及不确定性可额外保存。

## 写作 ledger

```json
{
  "root":"/actual/run/work",
  "results":[{
    "id":"gain-A", "value":2.0, "metric":"paired gain", "condition":"heldout tasks",
    "unit":"points", "run":"study-1",
    "source":{"kind":"computed","path":"results.json","sha256":"ACTUAL_SHA256","pointer":["gain"]}
  }],
  "bindings":[{
    "start":5,"end":9,"literal":"2.00","result_id":"gain-A","decimals":2,
    "metric":"paired gain","condition":"heldout tasks","unit":"points","run":"study-1"
  }],
  "references":[]
}
```

以上绑定对应完整文本 `gain 2.00 points`；start/end 是 Python Unicode 字符偏移，不是 UTF-8 字节。results.json 的 gain 对象必须有相同 value/metric/condition/unit/run。数值按给定小数位容差核对；百分比值按展示尺度保留，不能默默乘 100。

文献数值的 source.kind=literature，需 path/sha256/quote/page/reviewer/rationale；原文与值、条件和单位的语义对应由记录的审查负责。年份、编号等 non_result 必须有 span/literal/reason，审查其是否被滥用。引用写 `[@key]`，references[].id 对齐；引用存在后仍需原文 entailment。

artifact checks 可强制 `writing-audit` 的 passed=true。数值无未绑定项不保证非数值论断、因果、否定、修辞和范围正确；这些列为 semantic_review_required。
