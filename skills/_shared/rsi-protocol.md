# 可执行 RSI 协议

策略包与评分器是实际目录。协议将文件保存进 CAS，后续调用使用快照；不要把未运行的策略文本当评估结果。CLI 使用 `tool rsi-freeze request.json` 等结构化请求。

freeze 请求含 name/protocol/evaluator_dir/incumbent_dir/incumbent_command。protocol 例子：

```json
{
  "tasks":[
    {"id":"audit-a","split":"audit","domain":"toy","input":{"x":1},"expected":2},
    {"id":"audit-b","split":"audit","domain":"toy","input":{"x":3},"expected":4},
    {"id":"audit-c","split":"audit","domain":"toy","input":{"x":5},"expected":6}
  ],
  "seeds":[0,1], "scorer_command":["{python}","score.py"],
  "protected_checks":["finite"], "required_domains":["toy"],
  "max_trials":3,"min_gain":0.01,"max_task_regression":0,
  "direction":"higher","alpha":0.05,"resamples":4000,
  "timeout":30,"trial_seconds":300,"max_time_ratio":2
}
```

这三个 toy 任务只能演示接口，不能支撑研究能力结论。真实验收需要预先选定的独立任务、足够样本和领域/难度/失败族覆盖。development/selection/audit/final/anchor 各自用明确 split，不能由同一任务简单改 ID 伪装隔离。用户有责任验证语义相似性与数据污染。

strategy argv 后追加 `--task INPUT.json --seed N --output PREDICTION.json`，input 文件只含任务 id/input；scorer argv 后追加 `--task PRIVATE_TASK.json --prediction PREDICTION.json --output SCORE.json`。评分器输出 `{"metric":0.8,"checks":{"finite":true}}`；actual metric 必须有限。策略自行输出的分数不参与门槛。`{python}` 由当前 Python 解释器替换。

evaluate 请求含 name/candidate_dir/candidate_command/split/promote。分别执行两包、交替先后顺序、相同任务/种子/每次超时；保存原始输出及评分证据。task means 做配对 bootstrap，CI 下界严格超过 min_gain，并满足每任务最大回归、域覆盖、protected_checks 与时间比率门槛。runtime ratio 含机器负载噪声，必须以适当重复和容差配置。

alpha/max_trials 只提供保守阈值分配，bootstrap 和固定 audit 反复自适应使用并没有严格的有限样本错误率保证。max_trials 限制审计复用；一次失败/崩溃也已消耗。final 仅一次报告且不能 promote。不要把 final 看完后改代码继续声称它未参与选择。

通过且显式 promote=true 才原子更换 active；保存整包 prompts/code/tests/config。`rsi-rollback:{name,index,reason}` 回到 history[index]，不删除失败。`rsi-status:{name}` 看完整记录。策略目录可同时保留多个候选，不必抛弃全部探索分支。

`rsi-export:{name,destination}` 将当前 active 全包写到新的目录，给出 strategy.json、实际 command 和可传给下一次 init 的 inputs 映射。宿主读取导出的提示/配置，或用该命令执行下一任务，并把 strategy_hash 记入 manifest；不会静默改全局技能或核心评分器。

final 使用 epoch 创建时冻结的 reporting_baseline，而不是晋升后的 active，报告中 comparison_role=frozen_reporting_baseline；audit 仍与当前 incumbent 比较。最终报告任务与 audit 保持隔离，且 final 不能批准晋升。

新评分器须新 name/epoch；`rsi-compare:{left,right}` 只判断协议是否相同和是否有一致 anchor，不能校准评分语义。实际校准要把两评分器放在同一固定外部 anchor 上运行，审查一致性/漂移，所有依赖评分变更的统计失效；历史产物不删。

本地代码可信时，文件哈希检查可发现误改。**同权限候选可读取隐藏文件或改数据库，当前实现不构成密封评估**。对抗优化需要独立可信服务、隔离账号/容器权限及签名验收。这是部署依赖，不用提示词或本地“只读”标记冒充。

RSI 中断时先检查运行进程与外部状态；当前 epoch 的 running 记录不会被自动清理，以免并发重评估。使用 `rsi-recover:{name,reason}`，只有 worker 已退出才标记该 trial 失败并释放 lease，审计次数继续保留。不要手工抹掉 trials 重新获得审计次数。
