# 经验：LaTeXML 转存全文做风格统计必须段内清洗，整行剔除产生系统性假象

- **skill**: style-mimic（及一切对 arXiv HTML→txt 全文做文本统计的场景）
- **failure_mode**: 证据扭曲（清洗规则误杀——不是编造，但同样污染数值）
- **为什么**: kghalubench 画像首跑（2026-10-19）：首版把含 `\mathrm`/`_{\text}`/`\displaystyle` 的行整行剔除，而 arXiv LaTeXML 转存的数学符号残留（如 "HaluBOK\mathrm{Halu}_{\mathrm{BOK}}"）恰好密集出现在**结果分析段**——误删约 20% 正文（3543 vs 4401 词），suggest/indicate 计数为 0（实际 4/3），hedging 谱整体失真且**无任何报错**，若直接入画像则 P1（忠实于样本）静默违规。
- **如何应用**: 对 LaTeXML 转存 txt 先做**段内替换**（`\mathrm{...}`/`\text{...}`/`_{...}`/`^{...}`/`\displaystyle.*` 剔除后再判段去留），禁整行剔除含公式残段的正文；统计后必做 sanity 对照——关键特征计数与人工抽读段落交叉验证（抽 2-3 段确认含该特征的段落确实进了语料）；正文区间用行号锚点（Abstract 正文起 → References 前）并在画像头部声明口径，保证 E6 重跑幂等。
