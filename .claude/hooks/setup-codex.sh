#!/bin/bash
# 클라우드 세션 시작 시 Codex CLI 설치 + 이미지 생성 기능 설정
set -euo pipefail

# Claude Code 웹(원격) 세션에서만 실행
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

if ! command -v codex >/dev/null 2>&1; then
  npm install -g @openai/codex >/dev/null 2>&1
fi

mkdir -p "$HOME/.codex"
if [ ! -f "$HOME/.codex/config.toml" ]; then
  cat > "$HOME/.codex/config.toml" <<'TOML'
# Codex CLI 설정
# 이미지 생성(내장 image_gen 도구) 활성화 — ChatGPT 계정 로그인 시 동작
[features]
image_generation = true
TOML
fi
