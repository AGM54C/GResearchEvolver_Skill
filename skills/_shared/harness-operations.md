# Harness 运维与科研图谱记忆

适用范围：Windows / Linux 单机、可信命令、本地文件系统上的 SQLite Store。CPU/GPU 队列是合作式配额；多机器共享 SQLite、恶意命令隔离、高可用和大规模图查询不属于该后端的保证。对抗候选使用既有 Docker RSI 边界。本文所称复现是输入、软件、执行与证据可核对；硬件差异、随机算法和模型服务仍可能改变结果。

下列命令使用源码入口 `skills/_shared/runtime/research.py`；安装后改为 `<skills-dir>/_shared/runtime/research.py`。科学辅助工具和记忆操作均采用 `tool OPERATION request.json`，可加全局 `--output result.json` 保存结果。

## 执行与恢复

本地命令由独立监督器启动。Windows 使用 Job Object 和启动闸门，Linux 使用 subreaper；私有控制管道断开、取消、期限到达、日志超限都会停止任务。退出成功也清理遗留后代。Linux 若监督器本身被 SIGKILL，脱离进程组的后代需要外部 cgroup/容器治理；这和杀死工作流控制进程是不同故障。

运行和队列使用进程退出即释放的 OS 文件锁。锁文件不可手动删除：删除可能创建两个独立锁。状态带 worker token、generation、heartbeat、attempt ID、启动/完成时间和分类错误；心跳是观测信号，不用于按时间抢占活跃 worker。新运行不依赖 PID 判断所有权；旧存储保留保守 PID 检查。

```text
python skills/_shared/runtime/research.py --store state doctor
python skills/_shared/runtime/research.py --store state status RUN
python skills/_shared/runtime/research.py --store state events RUN
python skills/_shared/runtime/research.py --store state control RUN cancel
python skills/_shared/runtime/research.py --store state recover RUN
python skills/_shared/runtime/research.py --store state control RUN retry --stage STAGE --reason "已检查失败原因与外部状态"
python skills/_shared/runtime/research.py --store state run RUN
```

`recover` 要求控制进程锁已释放，并核对 active attempt 的清理回执。活跃监督器仍持锁时等待其完成后重试。缺失回执/未知效果不会自动恢复为可重跑；操作员实际核对后可提供 `--reconciliation reconciliation.json`：

```json
{"actor":"researcher-id","reason":"说明检查了哪些进程和外部作用，及其结果","effects_checked":true}
```

此记录是人工对账，不是 exactly-once 证明。队列崩溃条目使用 `tool queue-recover`，请求 `{"job":"JOB_ID","reconciliation":{...}}`；无不确定效果时省略 reconciliation。确认清理后释放容量，将任务记为 interrupted，不自动重跑有副作用的工作。

本地 stage 可声明 `retries:0..2`、`idempotent:true`、非零 `retry_exit_codes` 和 `retry_backoff`（默认 0.25 秒，指数退避）。重试与退避共享阶段截止时间，保留每次退出码和日志哈希。校验失败、输入被修改、超时、取消均不自动重试；SSH / external_write 禁止该自动重试路径。成本仍是按声明预留，不是云账单限额。

`max_log_bytes` 默认每流 10 MB，超限失败并停止；`max_output_bytes` 默认每个声明产物 100 MB，超限不能验收。它们不限制可信命令写入其他文件的总磁盘量。大数据任务应声明合适的产物上限并使用外部磁盘配额/容器资源策略。

## 环境与复现

每次运行保存 Python 实现/版本/解释器哈希、平台架构、已安装 Python 包版本、runtime 源码哈希及允许记录的确定性环境变量。`reproducibility.packages` 可显式限定包集合；lockfile、代码与数据必须同时作为不可变 inputs 保存。

先建立锁，`environment-request.json`：

```json
{"root":"inputs-directory","packages":["numpy"],"files":["requirements.lock","analysis.py"]}
```

```text
python skills/_shared/runtime/research.py --output environment-lock.json tool environment-lock environment-request.json
```

将返回对象放入 manifest 的 `reproducibility:{"mode":"strict","lock":...}`，并把相同文件映射进 run。严格模式在命令启动前比较；差异记录到 `environment_error` 并阻塞。`record` 模式记录事实而不阻塞。省略 packages 会记录全部已安装包；`packages:[]` 则只核对解释器/runtime/声明文件等。

stage 的 `seed` 设置 `GRESEARCH_SEED` 和 `PYTHONHASHSEED`，调用程序仍需用该值初始化自身 RNG；不自动宣称 CUDA/LLM 确定性。Python 包版本不能替代带 hash 的依赖锁、系统库、驱动、容器摘要和远端模型版本；将这些作为声明输入及研究协议保存。未记录的宿主环境仍可能影响可信子进程。

## 存储与备份

SQLite 使用 WAL + FULL synchronous，拒绝未来 schema。CAS 对象先写 staging、fsync，再原子发布；半写文件不会占据内容哈希名。`verify` 同时检查 SQLite、事件链、现存对象和运行/记忆引用的缺失对象。这是完整性检查，不是同权限安全封印。

```text
python skills/_shared/runtime/research.py --store state backup backups/snapshot-001
python skills/_shared/runtime/research.py verify-backup backups/snapshot-001
python skills/_shared/runtime/research.py restore-backup backups/snapshot-001 restored-state
```

备份要求受管 worker/队列已静止，包含 SQLite、CAS、工作区和科研图谱历史。目标必须是源 Store 外的新目录；恢复只写新目录，逐文件验哈希后检查 Store。不能用普通文件复制替代 SQLite 在线备份接口。外部 OpenViking 服务、SSH 目录、仪器和数据库状态不包含在这个备份中。中断留下的 `.pending-*` / staging 对象不是已提交备份；确认无工作进程后可由运维清理。磁盘/文件系统实际断电持久性仍需部署环境验证。

## 科研条目与关系

记忆模型始终是属性图：`nodes[]` 中保存科研条目，`edges[]` 中保存带类型的有向关系。节点类型可为 source、claim、hypothesis、experiment、data、code、result、method、decision 等；边保留 from/to/relation、引文、页码、哈希、适用范围、人工裁决等原始字段。持久化只核对结构，不把记忆写入当作证据验收；科学证据继续使用 `graph` / `semantic-graph` 检查。

`memory-put` 请求：

```json
{
  "project":"my-study","expected_revision":0,"actor":"researcher","reason":"记录研究计划",
  "graph":{
    "nodes":[{"id":"hypothesis-1","type":"hypothesis","text":"待检验的命题","status":"proposed"},
             {"id":"experiment-1","type":"experiment","text":"对应控制实验"}],
    "edges":[{"id":"test-1","from":"hypothesis-1","to":"experiment-1","relation":"tested_by","status":"planned"}]
  }
}
```

新项目用 `expected_revision:0`；后续提交必须匹配当前 revision，冲突失败，不做静默最后写入覆盖。历史快照和人工修订来源保留。节点 ID 可包含 DOI 等字符，OpenViking 路径由哈希生成，避免路径穿越及大小写冲突。

| 操作 | 请求关键字段 |
|---|---|
| `memory-get` | project，选填 revision |
| `memory-search` | project、query；options 中可设 limit/revision，本地 BM25 |
| `memory-neighbors` | project、nodes（起点 ID 列表）；options 中可设 hops、direction、max_nodes、revision |
| `memory-invalidate` | project、source_ids、expected_revision、actor、reason；传播失效并保留旧裁决 |
| `memory-export` | project、destination，选填 revision |
| `memory-import` | path、project、expected_revision、actor、reason；核对导出哈希 |

当前遍历和本地检索从指定版本快照计算，适合项目级图谱；大规模图库吞吐尚未测量。撤回/修订生成新版本，不自动删除历史证据；需要隐私删除时，应按实际保留策略处理本地备份和远端所有版本。

## OpenViking 适配

OpenViking 负责可选的持久化副本和检索。本地 SQLite/CAS 保存权威科研图、索引和待同步记录，服务不可用时仍可记录和查询。OpenViking 当前公开接口不提供本适配器所需的通用属性图事务；因此显式存储 `graph.json`、每个 `nodes/*.json`、每个 `edges/*.json`，边同时带端点 URI。摘要或向量不能覆盖这些记录。

服务配置示例：

```json
{"endpoint":"http://127.0.0.1:1933","namespace":"viking://resources/gresearch","api_key_env":"OPENVIKING_API_KEY","account":"my-account","user":"my-user","timeout":120,"processing_mode":"vectors_only"}
```

按实际认证省略不需要的字段；非 loopback 地址要求 HTTPS，密钥仅经环境变量传递。此适配器不安装全局宿主 hooks，也不上传整个聊天记录。`vectors_only` 调用服务已配置的向量模型；如显式选 `semantic_and_vectors`，服务还会调用其语义处理模型，应按原有数据与预算授权配置。

| 操作 | 请求关键字段 |
|---|---|
| `memory-sync` | project、config，选填 revision |
| `memory-remote-search` | project、config、query，选填 revision/limit |
| `memory-pull` | config、source_project、snapshot（可信 SHA-256）、project、expected_revision、actor、reason |

每次同步有独立持久化 outbox 状态，按目标和快照加锁；每个远端 URI 不可变，创建前后核对原字节。回执丢失先读取对账，冲突不覆盖。所有文件验收后才发布 commit.json；部分上传不能当完整图读取。重试 `memory-sync` 可续传，失败 CLI 返回 3，待同步状态可由 `doctor` 查看。外部检索只接受当前项目与指定版本的节点 URI，并再次核对原文；目录摘要、其他项目或旧版本命中不会直接进入科研节点结果。

`memory-pull` 在完整核对 commit、图和节点/边后导入新本地版本。OpenViking 账户 ACL、备份及多租户服务配置由服务端负责；本轮真实集成仅验证隔离开发服务，未验证生产账户权限矩阵或托管云版。

上游固定源码与验证范围见仓库 `docs/HARNESS-RELIABILITY.md`。OpenViking 固定版本主项目为 AGPL-3.0；本项目使用 HTTP 协议适配，不捆绑或移植服务器源码。服务部署和再分发遵守对应版本许可。
