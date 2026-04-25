#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_NAME="mission-center"
PLUGIN_ROOT="$HOME/plugins/$PLUGIN_NAME"
MARKETPLACE_DIR="$HOME/.agents/plugins"
MARKETPLACE_PATH="$MARKETPLACE_DIR/marketplace.json"

mkdir -p "$PLUGIN_ROOT" "$MARKETPLACE_DIR"
rm -rf "$PLUGIN_ROOT/.codex-plugin" "$PLUGIN_ROOT/assets" "$PLUGIN_ROOT/skills" "$PLUGIN_ROOT/scripts"
cp -R "$ROOT/.codex-plugin" "$ROOT/assets" "$ROOT/skills" "$ROOT/scripts" "$PLUGIN_ROOT/"
cp "$ROOT/README.md" "$ROOT/LICENSE" "$ROOT/NOTICE.md" "$PLUGIN_ROOT/"

python3 - "$MARKETPLACE_PATH" "$PLUGIN_NAME" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
plugin_name = sys.argv[2]
entry = {
    "name": plugin_name,
    "source": {"source": "local", "path": f"./plugins/{plugin_name}"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity",
}

if path.exists():
    data = json.loads(path.read_text(encoding="utf-8"))
else:
    data = {"name": "local", "interface": {"displayName": "Local Plugins"}, "plugins": []}

data.setdefault("name", "local")
data.setdefault("interface", {"displayName": "Local Plugins"})
data["plugins"] = [plugin for plugin in data.get("plugins", []) if plugin.get("name") != plugin_name]
data["plugins"].append(entry)
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY

echo "Installed Mission Center plugin to $PLUGIN_ROOT"
echo "Updated marketplace at $MARKETPLACE_PATH"
echo "Restart Codex to refresh the plugin list."
