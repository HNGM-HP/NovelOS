#!/usr/bin/env bash
set -euo pipefail

# ====== 可配置项 ======
USER="HNGM-HP"
REPO="NovelOS"
DEFAULT_BRANCH="main"
FEATURE_BRANCH="feature/x"

# ===== Git identity（仅当前仓库，避免全局污染） =====
if ! git config user.name >/dev/null 2>&1; then
  git config user.name "HNGM-HP"
fi

if ! git config user.email >/dev/null 2>&1; then
  git config user.email "542869290@qq.com"
fi
# ======================================================

# 远端地址（HTTPS）
REMOTE_URL="https://github.com/${USER}/${REPO}.git"

# 是否自动创建 GitHub 仓库（需要 gh；true/false）
AUTO_CREATE_REPO="${AUTO_CREATE_REPO:-false}"
PRIVATE_REPO="${PRIVATE_REPO:-true}"   # true=private false=public（仅 AUTO_CREATE_REPO=true 时生效）
# ======================

die() { echo "ERROR: $*" >&2; exit 1; }

need_cmd() { command -v "$1" >/dev/null 2>&1 || die "缺少命令：$1"; }

# 在项目根目录执行
need_cmd git

if [ ! -d .git ]; then
  echo "[1/7] 初始化 git 仓库..."
  git init
fi

# 载入本地 .env（不进 git）
if [ -f ./.env ]; then
  # shellcheck disable=SC1091
  source ./.env
fi

TOKEN="${GITHUB_TOKEN:-}"
[ -n "$TOKEN" ] || die "未设置 GITHUB_TOKEN。请创建 .env：echo 'export GITHUB_TOKEN=\"<token>\"' > .env"

# 保护：确保 .env 不入库
touch .gitignore
grep -qxF ".env" .gitignore || echo ".env" >> .gitignore

# 保护：忽略 Python 缓存（可选但推荐）
grep -qxF "__pycache__/" .gitignore || echo "__pycache__/" >> .gitignore
grep -qxF "*.pyc" .gitignore || echo "*.pyc" >> .gitignore

# 如果 .gitignore 被修改而且还没提交，不强制你提交；但为了推送干净，自动提交一次
if ! git diff --quiet -- .gitignore; then
  echo "[2/7] 自动提交 .gitignore 更新（保护 .env/__pycache__）..."
  git add .gitignore
  git commit -m "chore: ignore env and pycache" >/dev/null 2>&1 || true
fi

# 如果没有提交，创建一个初始提交（否则 GitHub 无法推）
if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "[3/7] 创建初始提交..."
  git add -A
  git commit -m "chore: initial commit"
else
  # 如果工作区有改动，自动提交一次（你也可以改成 exit 1）
  if [ -n "$(git status --porcelain | grep -v '^?? ' || true)" ] || [ -n "$(git status --porcelain | grep '^?? ' || true)" ]; then
    echo "[3/7] 检测到未提交改动，自动提交一次..."
    git add -A
    git commit -m "chore: sync local changes" || true
  fi
fi

# 确保默认分支存在且为 DEFAULT_BRANCH
echo "[4/7] 切换/创建分支：${DEFAULT_BRANCH}"
git branch -M "${DEFAULT_BRANCH}"

# 可选：自动创建 GitHub 仓库（需要 gh）
if [ "$AUTO_CREATE_REPO" = "true" ]; then
  need_cmd gh
  echo "[5/7] 尝试自动创建 GitHub 仓库（若已存在会提示）..."
  VISIBILITY="--public"
  [ "$PRIVATE_REPO" = "true" ] && VISIBILITY="--private"
  # 若仓库存在，gh 会报错；忽略即可
  gh repo create "${USER}/${REPO}" ${VISIBILITY} --source=. --remote=origin --push 2>/dev/null || true
fi

# 设置 origin（不带 token）
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

# 推送 main（使用临时带 token 的 url，不落盘）
echo "[6/7] 推送 ${DEFAULT_BRANCH}..."
git push -u "https://${USER}:${TOKEN}@github.com/${USER}/${REPO}.git" "${DEFAULT_BRANCH}" --force-with-lease

# 推送 feature 分支（如果不存在就从 main 创建）
if git show-ref --verify --quiet "refs/heads/${FEATURE_BRANCH}"; then
  echo "[7/7] 推送 ${FEATURE_BRANCH}..."
else
  echo "[7/7] 创建并推送 ${FEATURE_BRANCH}..."
  git switch -c "${FEATURE_BRANCH}"
  git push -u "https://${USER}:${TOKEN}@github.com/${USER}/${REPO}.git" "${FEATURE_BRANCH}" --force-with-lease
  git switch "${DEFAULT_BRANCH}"
fi

echo "Done. origin 保持为不含 token 的 URL：${REMOTE_URL}"
