#!/bin/sh
# GResearchEvolver skill 集合安装器
# 用法:
#   sh install.sh              → 安装到 Claude Code 全局 ~/.claude/skills/
#   sh install.sh --project    → 安装到当前目录 .claude/skills/（项目级）
#   sh install.sh --dest PATH  → 安装到任意运行时的 skill 目录
#   sh install.sh --force      → 覆盖已存在的同名 skill（默认跳过并提示）
set -e

SRC="$(cd "$(dirname "$0")" && pwd)/skills"
DEST="$HOME/.claude/skills"
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --project) DEST="$PWD/.claude/skills"; shift ;;
    --dest)    DEST="$2"; shift 2 ;;
    --force)   FORCE=1; shift ;;
    *) echo "未知参数: $1（支持 --project / --dest PATH / --force）"; exit 1 ;;
  esac
done

if [ ! -d "$SRC" ]; then echo "错误: 未找到 $SRC（请在仓库根目录运行）"; exit 1; fi

mkdir -p "$DEST"
installed=0; skipped=0

for d in "$SRC"/*/; do
  name=$(basename "$d")
  if [ -d "$DEST/$name" ] && [ "$FORCE" -ne 1 ]; then
    echo "跳过 $name（已存在，加 --force 覆盖）"; skipped=$((skipped+1)); continue
  fi
  cp -r "$d" "$DEST/$name"
  echo "安装 $name"; installed=$((installed+1))
done

cp "$SRC/manifest.yaml" "$DEST/manifest.yaml"

echo ""
echo "完成: $installed 个 skill 装入 $DEST（跳过 $skipped 个）"
echo "验证: ls $DEST 应看到 skill 目录 + manifest.yaml"
echo "试用: 在 Claude Code 里丢一篇论文 PDF，说「用 literature-scholar 精读这篇」"
