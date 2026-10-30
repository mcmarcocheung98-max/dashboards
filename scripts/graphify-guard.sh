#!/usr/bin/env bash
# For a PreToolUse hook: graphify's reminder to query the map before searching or reading code.
# A no-op until graphify is installed and the map exists (scripts/graphify-setup.sh builds both).
command -v graphify >/dev/null 2>&1 && [ -f "$(dirname "$0")/../graphify-out/graph.json" ] || exit 0
exec graphify hook-guard "$@"
