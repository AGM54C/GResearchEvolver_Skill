# Agent 与 Skill 的维护边界

两个仓库是两个产品入口。为让克隆、源码 ZIP 和宿主安装保持可离线使用，消费端提交固定版本的依赖快照，而不是在启动时追踪对方的 main 分支。

| 唯一维护源 | 内容 | 消费端 |
|---|---|---|
| [GResearchEvolver_Agent](https://github.com/AGM54C/GResearchEvolver_Agent) | `skills/_shared/runtime/`、MemTX vendor、Agent/长程手册、启动与打包脚本、测试、`tools/bundle_sync.py`、Agent/长程实现报告 | Skill 的 `dependencies/runtime.lock.json` |
| [GResearchEvolver_Skill](https://github.com/AGM54C/GResearchEvolver_Skill) | 26 个技能、注册表、其他共享协议/辅助脚本，以及安装器、HARNESS 和技能架构说明 | Agent 的 `dependencies/skills.lock.json` |
| 各仓库自身 | README、许可证范围、产品标识、CI、依赖锁、拆分与发布报告 | 不相互覆盖 |

运行时代码继续使用原路径以兼容已安装宿主、子进程和实验脚本。生成快照不是第二个维护源；`.gitattributes` 保留其原始字节并标记为 generated。Skill 内的兼容启动器也不意味着独立维护另一套 Agent。

## 更新技能

先在 Skill 仓库编辑、检查并提交技能。再在 Agent 仓库执行：

```text
python tools/bundle_sync.py sync --source ../GResearchEvolver_Skill --revision <Skill完整40位提交SHA>
python tools/bundle_sync.py verify --source ../GResearchEvolver_Skill
python -B tests/run_checks.py --report validation.json
```

同步读取 Git 提交中的 blob，忽略源工作区尚未提交的改动。核对差异和锁文件后提交 Agent 更新。

## 更新执行引擎

先在 Agent 仓库实现、测试并提交引擎。再在 Skill 仓库执行：

```text
python tools/bundle_sync.py sync --source ../GResearchEvolver_Agent --revision <Agent完整40位提交SHA>
python tools/bundle_sync.py verify --source ../GResearchEvolver_Agent
python -B tests/run_checks.py --report validation.json
```

两边可以使用不同产品版本。先发布被依赖的提交，再发布依赖锁更新；同步只提取对方负责的路径，不递归同步其依赖副本，因此没有循环构建依赖。回退使用已审阅的旧提交重新同步。

## 检查与恢复

`verify` 离线检查逐文件哈希、字节数、缺失或额外文件；`verify --source` 还检查锁内容与真实 Git 提交一致。CI 检出锁定的来源提交执行后者，因此单独重算本地哈希不能冒充上游来源。哈希固定版本，不构成敌对同权限环境的安全密封。

已有锁时，直接修改消费副本会阻止下一次同步，防止覆盖未提交工作。请把修改迁移到维护源，或在保留修改后用 Git 恢复消费副本。每文件替换为原子写入，锁最后写入；整个跨文件同步不是文件系统事务。中断时依赖检查会失败，应保留改动、恢复消费端到上一 Git 提交，再重新同步。

`--initialize` 仅用于第一次迁移；本次使用前已在产品外保留完整工作区备份。它不会绕过已存在的锁。同步拒绝路径穿越、符号链接和 Windows reparse points。

MemTX 保留其固定提交与 `NOASSERTION` 状态；无许可证不等于 MIT。产品根 MIT 只覆盖本项目原创内容，见 [第三方说明](../skills/_shared/THIRD_PARTY.md)。
