# venue 模板协议（获取/骨架/编译环境）

> 被 `latex-adaptor` Phase 0 引用。原则：**不自动信任 web 上的模板副本**（Overleaf/个人镜像的过期 .sty 是 desk-reject 常见根因），官方源报告 + 人为确认后才获取；取不到就诚实用通用骨架。

## 1. 模板三分支决策

```
用户提供 .sty/.cls/.tex？
 ├─ 是 → 直接用；记录 {来源: user, 文件哈希} 入 format-report
 ├─ 否 → 能定位官方源？
 │    ├─ 是 → 报告链接 + 版本判定（检测到的 vs CFP 要求的）→ H2 等确认 → 获取
 │    └─ 否（或确认失败）→ 通用骨架 + template: generic 标注
```

## 2. 官方源定位口径

| venue 类型 | 官方源 | 判定要点 |
|---|---|---|
| ML 会议 | 官网 author kit 页（NeurIPS/ICML/ICLR 年度 kit） | 年份匹配（neurips_2025.sty ≠ 2026 CFP） |
| 期刊 | 出版社 author guidelines（Nature/Elsevier/Springer） | .bst 与引用样式配套 |
| arXiv 预印本 | arXiv 通用（无 venue 约束） | 用 generic 单栏即可 |

报告格式示例：`检测到 main.tex 使用 neurips_2025.sty；2026 CFP 要求 neurips_2026.sty <链接>——不匹配，请确认目标年份`。

## 3. 通用骨架（generic，自产无版权风险）

两式，均为标准 article 类：

- **会议式**：双栏 `twocolumn` + `booktabs` 表 + `\bibliographystyle{plainnat}`——视觉近似 ML 会议但不冒充任何具体模板；
- **期刊式**：单栏 11pt + 1.5 节标题深度——投稿前须替换为官方模板（format-report 中提示）。

骨架固定结构：`\title/\author`（匿名模式下作者块替换为 Anonymous）→ abstract → sections → bibliography。禁自定义宏包堆叠（保持零依赖可编译性）。

## 4. 编译环境检测与降级链

```
latexmk 存在？
 ├─ 是 → latexmk -pdf（CJK: -xelatex）主路径
 └─ 否 → pdflatex/xelatex 裸跑两遍（.bib 需 bibtex 一遍：pdflatex → bibtex → pdflatex ×2）
      └─ 均无 → compile: skipped_no_env：输出 .tex + refs.bib + 编译说明（本地装 TeX Live / 上传 Overleaf 的两步指引）
```

- CJK 判定：正文含中日文字符 → 强制 xelatex + ctex 宏包提示；
- 编译错误三档分类：**缺包**（! LaTeX Error: File `X.sty' not found → 报告缺失清单）/ **语法**（! Undefined control sequence → 修复并记录）/ **字体**（CJK 乱码 → 换 xelatex）；
- 修复纪律：每次修复记 trace（改了什么/为何），连续 3 次修复失败 → 停，输出当前 .tex + 错误清单给用户（E2 降级，不无限循环）。

## 5. 匿名化检查清单（anonymous: true）

- [ ] 作者/机构/邮箱块剔除（替换 Anonymous）
- [ ] 致谢与资助号整节剔除
- [ ] 自引改第三人称（"our prior work [X]" → "prior work [X]"）
- [ ] PDF 元数据 author 字段清空
- [ ] 仓库链接匿名（anonymous.4open.science 式或删除）
