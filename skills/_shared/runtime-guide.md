# Runtime 使用手册

需要 Python 3.10+。核心只有标准库；PDF 摄取另需 PyMuPDF。路径相对当前工作目录；在源码仓库使用 `python skills/_shared/runtime/research.py`，安装后把前缀换为实际 skills 目录。所有命令支持全局 `--store PATH` 与 `--output RESULT.json`（放在子命令之前）。

## 创建与执行

下面是一份实际可执行的最小 manifest。命令数组不经过本地 shell；本地命令的 `{python}` 展开为当前 runtime 的 Python 解释器，也可指定解释器绝对路径。

```json
{
  "version": 2,
  "objective": "检验给定数据中的配对差异",
  "authorization": {"effects": ["local"], "ssh_hosts": []},
  "budget": {"seconds": 300, "cost": 0},
  "stages": [{
    "id": "analysis-1",
    "skill": "statistical-analyst",
    "milestone_id": "paired-effect-estimate",
    "milestone": "得到含独立单位和区间的效果估计",
    "needs": [],
    "requires": ["data.json", "analysis.py"],
    "optional": [],
    "outputs": ["results-1.json"],
    "command": ["{python}", "analysis.py", "--input", "data.json", "--output", "results-1.json"],
    "effect": "local", "timeout": 120, "retries": 0,
    "cost_estimate": 0
  }]
}
```

inputs.json 为 `{"data.json":"/actual/source/data.json","analysis.py":"/actual/source/analysis.py"}`。输入在创建时复制到研究运行目录，后续命令 cwd 是该目录。

```text
python skills/_shared/runtime/research.py --store research-state init manifest.json --inputs inputs.json --id study-1
python skills/_shared/runtime/research.py --store research-state run study-1
python skills/_shared/runtime/research.py --store research-state status study-1
python skills/_shared/runtime/research.py --store research-state events study-1
```

`status` 返回实际 work 路径。命令成功仍需新产生的非空输出；JSON 不能有 NaN/Infinity。需要门槛时加 `checks:[{"path":"audit.json","field":"passed","equals":true}]`，字段不符会使阶段失败。科学检验的负结果也可以是一个成功执行的阶段；成功执行不自动代表假设成立。

退出码：`0` 为命令完成（科研工具可能返回负结果）；`2` 为请求错误或完整性核验失败；`run` 返回 `3` 表示运行尚未完成，包括合法暂停、等待宿主产物、阻塞、取消或执行失败。自动调用方应读取 JSON 的 `status`，不要把所有 `3` 都当作实验异常。

每个产物只由一个 stage 写；迭代用不同 ID 和版本路径，needs 明确列前驱。optional 输入若由前阶段产生也要声明依赖；不把所有技能契约合并成循环。registry `manifest.yaml` 采用 JSON-compatible YAML，无需第三方 YAML 解析器。pipelines 是路由模板，须由宿主结合具体文件绑定，不能直接当运行 manifest。

## 宿主模型阶段与修订

没有 command 的 stage 会返回 `awaiting_artifact`。宿主在 status 返回的 work 目录内，按对应 SKILL.md 实际完成任务，再调用：

```text
python skills/_shared/runtime/research.py --store research-state finish study-1 writing-1 --actor host-agent
python skills/_shared/runtime/research.py --store research-state run study-1
```

完成时复查输入未变和输出存在。runtime 不自带模型账号或一个虚构的后台 agent。若外部模型用命令适配器调用，保存实际请求/回复和模型版本，密钥用 `env_from:{"API_KEY":"MY_PROVIDER_KEY"}`。

论文修订可实例化 `draft-1 → review-1 → revise-2 → retest-2 → review-2`；每次修改只消费指定版本，保留旧稿、旧评审和补实验状态。

## 人工控制

```text
python skills/_shared/runtime/research.py --store research-state serve --port 8765
python skills/_shared/runtime/research.py --store research-state control study-1 pause
python skills/_shared/runtime/research.py --store research-state control study-1 breakpoint --stage analysis-1
python skills/_shared/runtime/research.py --store research-state control study-1 step
python skills/_shared/runtime/research.py --store research-state run study-1
python skills/_shared/runtime/research.py --store research-state annotate study-1 analysis-1 "分析单位应是独立任务"
python skills/_shared/runtime/research.py --store research-state fork study-1 analysis-1 --patch changes.json --id study-2
python skills/_shared/runtime/research.py --store research-state compare study-1 study-2
```

打开控制台打印的 `http://127.0.0.1:8765`。不会自动启动浏览器。CLI `resume/step` 改状态后需再 `run`；UI 会自动请求 worker。fork 继承断点，必要时恢复。changes.json 格式 `{"analysis-1":{"command":["{python}","analysis.py","--robust"],"milestone":"稳健性估计"}}`；允许修改 command/timeout/requires/optional/outputs/instructions/milestone/milestone_id。修改授权、预算、评分器或外部输入内容时建立有来源的新 manifest/run，不直接改旧运行。

跨运行比较先对齐两侧唯一的 `milestone_id`；没有 ID 时使用唯一的相同 milestone 标签，再回退到 stage ID。重复声明不强行一对一匹配。同 stage ID 但双方显式 milestone_id 冲突时保持未匹配并输出 `alignment_conflicts`。这些都是声明匹配，不能自动证明科学目标或估计量等价；变更目标应改 ID 并人工解释。

程序崩溃后 `recover RUN` 只在 worker 已退出时恢复状态；不会因等待久而擅自抢占。检查可能遗留的外部效果后再 retry。手工结束服务不代表远程实验已停止。

## 科研工具：结构化请求

统一格式：`research.py --store PATH --output result.json tool OP request.json`。工具输出的 `passed:false`/负结果与软件异常不同，调用方读取相应字段；workflow 可用 checks 强制质量门槛。

| OP | request 核心字段 | 结果与边界 |
|---|---|---|
| pdf | source, destination | 原 PDF、每页文本/哈希、OCR-needed |
| search | provider, query, destination, pages?, page_size? | 真实响应存档；支持 crossref/openalex/semantic-scholar/europepmc/arxiv |
| import | path, format? | csl/bibtex/ris/nbib/endnote/xml；保留原文与字段 |
| dedup | records | DOI 合并与冲突/alias |
| export | records, path, format | csl/ris/bibtex + lossless sidecar |
| citation | doi, destination | Crossref metadata；撤稿无标志为 unknown |
| zotero | library_type, library_id, destination, max_pages? | users/groups；只读，ZOTERO_API_KEY 环境变量 |
| notes | records, destination | 版本化 Markdown/Obsidian 笔记；保留 parent/key/批注原文，不写回文献库 |
| monitor | name, records | 新增/变更/flagged/暂未出现 |
| local-index | root, documents, destination?, embedding_model?, embedding_provenance? | documents 含 id/path，可附 source_id/page/sha256/embedding；索引固定源文件哈希 |
| local-search | index, query, options? | options 为 aliases/top_k/vector/embedding_model；BM25 或外部向量 RRF；源变动拒绝旧索引 |
| invalidate | graph, source_ids, reason | 下游标记 needs_review，保留旧裁决和产物；结果由调用方版本化保存 |
| paired | rows, options? | 每行 task/seed/candidate/incumbent；options 为 alpha/resamples/seed/direction |
| adjust | pvalues, method | holm 或 bh |
| meta | studies, common_estimand, independent_units_confirmed | 每项 study_id/effect/variance；原效果尺度 |
| data-audit | rows, target?, split_column?, group_column? | 质量与泄漏提示，非完整保证 |
| graph | graph, root | 来源哈希/原文/类型与裁决完整性 |
| writing-audit | document, ledger | 精确数字绑定与原结果文件核验 |
| novelty | searches, claims | 最近邻矩阵与反证搜索完整性 |
| quality | studies, outcomes | RoB/GRADE 记录完整性，不代替专家 |
| intervention | followed, matched_controls, repetitions, external_state_comparable, measurement_contracts, milestones, pairs | 遵循/对照/测量可比性不足为 Inconclusive；pairs 同 paired |
| proof | project, source, declarations, destination, allowed_axioms?, timeout? | lake env lean + axiom audit；无环境 unverified |
| grant | call, aims, work_packages, risks, budget, evidence, currency, budget_cap? | 结构与精确预算算术 |

系统综述：`review-freeze:{name,protocol}`，protocol 含 question/eligibility/databases/searches/outcomes/reviewers；`screen:{name,decisions}` 每项 record/stage/reviewer/decision/independently_assessed，exclude 加 reason，full_text 加 source_locator（unavailable 除外）。`adjudicate` 使用同样 record/stage/decision 加第三位 reviewer/reason。`review-report:{name,inventory:{identified,duplicates_removed,records:[{id,study_id}]}}`。协议修改用新 name，并在协议中记录 parent/reason。

序贯检验 `eprocess` 输入 null/design_hash/validity_review/alpha/tests。每项 test 有 id/subnull/null_implies_subnull/conditional_validity/data_use/e_value。程序累积 e-value，不证明提交的有效性论证。

干预请求需给出 `measurement_contracts.control` 与 `measurement_contracts.intervention`，两侧均含 `estimand`、`metric`、`unit`、`analysis_unit`、`evaluation_data_hash`。缺项或改变任一字段均为 Inconclusive。哈希应对应真实评价数据；换均值为中位数、换任务集合、换计分口径不能直接称为干预收益。契约相等仍依赖准确声明，程序不独立证明语义、数据来源和因果性。`milestones` 为含 achieved 的科学目标列表，`direction` 可为 higher/lower，`minimum_gain` 默认为 0。

本地检索不会自动下载或生成向量：已有向量需声明固定 embedding_model 和实际生成来源 embedding_provenance，查询向量须同模型。BM25 采用拉丁词与 CJK 双字切分，可提供显式 aliases；检索排名不是事实支持判定。

RSI 的请求格式见 [rsi-protocol.md](rsi-protocol.md)。最小可运行示例见 `examples/offline_research.py`，会实际运行计算阶段、HCI 分支、证据审计、RSI 晋升/拒绝/回滚。

`rsi-recover:{name,reason}` 只在 worker 已退出时恢复中断的 epoch，保留已使用的审计次数。`rsi-export:{name,destination}` 将当前 active 整包导出到新目录并返回后续命令/输入映射，拒绝覆盖已有目录；宿主应把该包作为下一 run 的实际输入，才能应用已验收策略。它不覆盖全局 skill 或评分器。final 始终比较 freeze 时的 reporting_baseline，与当前 active 分开。

## 排队与 SSH

`enqueue:{run,resources:{cpu:2,gpu:0},priority:0}`；`queue-next:{capacity:{cpu:8,gpu:1}}` 执行一个能容纳的任务，外部调度器可循环调用；`queue-status:{}`；`queue-cancel:{job}`。运行目录、任务状态、日志可在控制台查看。CPU/GPU 声明是调度预算，不分配物理设备。

SSH stage 加 `ssh:{host:"user@host",port:22,cwd:"/dedicated/research-run",known_hosts:"/path/to/pinned_known_hosts"}`，authorization.ssh_hosts 包含同一 host。需 Paramiko 与远程 Linux/Python 3；身份认证使用 SSH agent/identity_file，或 password_env 指向内存环境变量，不能把密码放入 manifest。父 cwd 预先存在，每次运行创建唯一目录，上传 requires/存在的 optional，执行 argv，取回有界常规 outputs。远程路径限制为字母/数字/点/下划线/横线/斜线。

客户端每 3 秒发送心跳；监督器在取消/超时/30 秒心跳失联后终止并回收后代，即使子进程调用 setsid。只有收到对应 job 的 result.json 才标记 remote_cleanup_verified；网络故障保留远程目录和未确认状态供核查。监督器管理可信实验，不是对抗代码沙箱；不会撤销外部业务写入，也不会自动删除远程研究产物。当前托管 SSH 不转发 env_from，需在远端独立配置所需环境。

## 实际模型与语义核验

`model:{config,messages,destination}` 支持 responses、chat-completions、ollama 和 codex-config；后者读取当前 Codex API-key 配置，不支持把 ChatGPT OAuth token 当作 API key。Python 3.10 另装 tomli。config 必须明确 model；可设 max_output_tokens、timeout、reasoning_effort、json_schema。请求、原始响应、实际 usage、模型返回身份、耗时与失败保存在新目录；没有返回模型身份时明确为 null。未知配置/明文密钥字段被拒绝，key_env 只记录变量名，不写入值。服务商别名内部的模型修订并不能独立认证。

`semantic-review:{config,items,destination,threshold}` 的 item 为 `{id,claim,sources:[{id,text,sha256,locator}]}`。或使用 `semantic-graph:{config,graph,root,destination}`，先核对源文件与图再读取绑定原文。输出含 model_label、保守 label、六个语义维度、精确引文偏移、拒判原因；这些是模型辅助意见，human_adjudicated 始终 false，不会覆盖人工裁决。threshold 只是自报置信度筛选，需在独立文献组人工标签上校准并报告拒判率。`semantic-metrics:{rows:[{id,gold,prediction}]}` 统计 supports/contradicts/insufficient/abstain，gold 不能为 abstain，ID 不可重复。

`embeddings:{config,texts,destination}` 调用真实向量 API；校验索引、数量、维度和有限值。离线 `representations:{config:{model_dir,layers:[-1,-2],max_length:256,expected_files},texts}` 需要 torch/transformers 与本地 safetensors 快照；逐文件哈希、实际隐藏层、池化方式和文本截断全部记录。`critic-fit` 的 rows 需 vector/gold/groups/split，encoder_hash 固定编码器与层；train/calibration/evaluation 的文献组必须隔离。`critic-predict` 只接受匹配 encoder_hash 的模型和向量。当前小样本线性诊断实测较弱，仅为实验性 triage，不能称为 Latent Critic/ReCast 复现。

Semantic Scholar relevance 受限时仍报告真实 HTTP 429。`s2-bulk:{query,destination,max_records}` 可显式选择官方 bulk 模式；它与 relevance 排序不同，记录截断和原始页，不隐式替换或声称查全。

## HCI pilot 与便携 Lean

`study-plan:{destination,participants:12,seed:20261019}` 产生平衡分配、冻结协议和空观测 CSV。`study-analyze:{protocol,observations}` 按参与者配对真实数据并报告缺失，拒绝空结果、重复和错配。源码仓库的 `docs/HCI-STUDY.md`、`benchmarks/hci_materials.py` 与 `benchmarks/hci-materials/` 提供任务和盲评材料；研究准备不计作研究结果。

`proof` 可用可选 lake 字段指定便携 lake 可执行文件；仍需完整 Lean 工具链与真实项目。检查实际编译、#print axioms、公理策略与依赖文件哈希，不能用证明编译成功代替科学命题的形式化对齐审查。

## 归档

`archive RUN`、`verify`、`verify-archive DIRECTORY`；`import-archive DIRECTORY --id NEW` 可在空 Store 恢复归档中的文件/状态/历史对象，再 fork。事件是源全局链的片段，导入记录保留来源，不伪造为新运行执行史。

命令执行不是 OS 沙箱；输入代码应可信。日志原始保存，不自动清洗所有秘密。恢复、授权与科学保证的完整边界见 HARNESS.md。
