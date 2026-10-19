# 安装与运行

在完整源码目录运行 Python 3.10+。不需要先启动云服务；大部分辅助工具只用标准库。PDF 摄取需要项目环境中的 PyMuPDF。

```text
python install.py --dest /absolute/path/to/host/skills
python install.py --project
python install.py --dest /absolute/path/to/host/skills --force
```

`--project` 使用当前目录的 `.claude/skills`。未给参数时默认 `~/.claude/skills`；Codex 等其他宿主请明确 `--dest`。本次开发只在临时隔离目录检验安装，没有修改用户全局技能目录。

`--force` 在目标目录先完整 staging，再逐项替换；原条目移动到 `.gresearch-backup-*`。失败会回滚本次替换；不同进程不要同时运行安装器。默认遇已有 bundle 条目会停止，避免新旧共享协议混装。保留其他无关技能。不会递归把同名目录套进去，也不自动删除备份。

安装内容为 25 个技能、`_shared/`（含 runtime、协议与示例）、manifest.yaml 和 HARNESS.md，另写 `.gresearch-install.json` 原字节清单。Unix `sh install.sh` 是 Python 安装器的兼容入口。

在宿主中使用 research-autopilot 处理跨阶段任务，或单独使用具体技能。runtime CLI 的相对前缀取决于实际安装位置：源码为 `skills/_shared/runtime/research.py`，安装后为 `<skills-dir>/_shared/runtime/research.py`。先 `--help`，再按 [运行手册](skills/_shared/runtime-guide.md) 建立具体 manifest。

验证可运行示例：`python skills/_shared/examples/offline_research.py --output demo-run`。查看控制台：`python skills/_shared/runtime/research.py --store demo-run/state serve`。控制台仅绑定 127.0.0.1，不自动打开浏览器。示例明确是合成数据。

外部适配依赖：检索需要网络（部分 API 需 key）；Zotero 需要可读库和可选 ZOTERO_API_KEY；SSH 需要 OpenSSH、host key、认证与专用工作目录；Lean 需要实际 lake 项目。工具不可用时报告未验证，不自动将协议标为完成。绘图/PPT 模块功能保持原版。
