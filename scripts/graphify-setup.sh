#!/usr/bin/env bash
# Make sure graphify is installed and build a fresh map of the current code (graphify-out/, ignored by git).
# Code-only rebuild: no LLM, no API key, about 20 s. Never fails: if PyPI is unreachable it just stops.
# Run it at session start (the environment's setup script, or a SessionStart hook): see CLAUDE.md.
cd "$(dirname "$0")/.." || exit 0
if ! command -v graphify >/dev/null 2>&1; then
  pip install -q graphifyy==0.9.97 >/dev/null 2>&1 || pip install -q --break-system-packages graphifyy==0.9.97 >/dev/null 2>&1 || exit 0
  hash -r
fi
command -v graphify >/dev/null 2>&1 || exit 0
[ -d "$HOME/.claude/skills/graphify" ] || graphify install --platform claude >/dev/null 2>&1
graphify update . >/dev/null 2>&1 || true
exit 0
