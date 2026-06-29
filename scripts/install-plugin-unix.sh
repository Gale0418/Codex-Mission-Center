#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CODEX_ROOT="${CODEX_HOME:-$HOME/.codex}"
PERSONAL_SKILL="${MISSION_CENTER_PERSONAL_SKILL:-$CODEX_ROOT/skills/mission-center}"
MARKETPLACE_PLUGIN="${MISSION_CENTER_MARKETPLACE_PLUGIN:-$CODEX_ROOT/local-marketplaces/mission-center/plugins/mission-center}"
MODE="${MISSION_CENTER_PUBLISH_MODE:---write}"

case "$MODE" in
  --dry-run|--write|--verify) ;;
  *) echo "MISSION_CENTER_PUBLISH_MODE must be --dry-run, --write, or --verify" >&2; exit 2 ;;
esac

python3 "$ROOT/scripts/publish_local.py" \
  --repo "$ROOT" \
  --personal-skill "$PERSONAL_SKILL" \
  --marketplace-plugin "$MARKETPLACE_PLUGIN" \
  "$MODE" \
  $( [ "$MODE" = "--write" ] && printf '%s' "--register" )

case "$MODE" in
  --dry-run) echo "Dry-run completed. No files were modified." ;;
  --write) echo "Published Mission Center to personal Skill and local marketplace plugin, then refreshed Codex plugin registration." ;;
  --verify) echo "Verification completed successfully." ;;
esac
