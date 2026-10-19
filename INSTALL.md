# 安装 GResearchEvolver

> 本质很简单：**把 `skills/` 目录放进你 Agent 运行时的 skill 目录**。以下任选其一。

## 方式一：一行命令（Claude Code，推荐先试这个）

```bash
git clone ssh://git@ssh.github.com:443/AGM54C/GResearchEvolver_Skill.git
cd GResearchEvolver_Skill && sh install.sh          # 装到全局 ~/.claude/skills/
# 或: sh install.sh --project                       # 只装到当前项目 .claude/skills/
```

装完在 Claude Code 里说一句验证：

```
读一下 skills 清单，然后用 literature-scholar 精读这篇论文：<拖入 PDF>
```

## 方式二：下载 zip（不想装 git 的话）

1. 打开 [Releases](https://github.com/AGM54C/GResearchEvolver_Skill/releases)，下载最新 `GResearchEvolver-vX.Y.Z.zip` 并解压
2. 把解压出的 `skills/` 下所有内容复制到 `~/.claude/skills/`（Windows: `%USERPROFILE%\.claude\skills\`）

## 方式三：其他 Agent 运行时（CodeArts / 任何支持 SKILL.md 的运行时）

```bash
sh install.sh --dest <你运行时的 skill 目录>
```

或手动：`skills/` 下每个 `<skill-name>/SKILL.md` 就是完整定义，按你运行时的规范放置即可（16 个 skill 目录 + `manifest.yaml` 一个文件，别拆散 manifest——编排器靠它路由）。

## 三分钟试用路径（装完后）

| 你说 | 它做 |
|---|---|
| 「精读这篇论文」+ PDF | literature-scholar：结构化条目 + 论断图节点 + 每个观点标注原文出处 |
| 「找一下 XX 方向最新文献」 | literature-miner：5 个真实学术源检索，失败明说，绝不编造 |
| 「对比这几篇的综述」 | survey-architect：图锚定综述——每个论断可回接，无证据不写 |
| 「帮我组会 slides」 | slides-builder：论点式幻灯片 + 讲稿 |

## 卸载

删除 skill 目录即可（`rm -rf ~/.claude/skills/<skill-name>`）；项目级同理删 `.claude/skills/` 下对应目录。

## 常见问题

- **装了没反应？** 确认运行时支持 SKILL.md 规范（Claude Code / CodeArts 均可）；重启会话让 skill 目录重新扫描。
- **research-instance/ 需要装吗？** 不需要——那是真实研究运行数据（归档/经验库/对照实验），留着阅读用：[导读](research-instance/README.md)。
- **Windows 能用吗？** install.sh 在 git-bash / WSL 下可跑；或直接用方式二手动复制。
