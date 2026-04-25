#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${CODEX_HOME:-$HOME/.codex}/skills/mission-center"

mkdir -p "$(dirname "$TARGET")"
rm -rf "$TARGET"
cp -R "$ROOT/mission-center" "$TARGET"

echo "Installed mission-center skill to $TARGET"
echo "Restart Codex to refresh the skill list."
