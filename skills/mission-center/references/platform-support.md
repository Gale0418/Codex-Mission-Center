# Platform Support

## Supported Paths

- macOS/Linux: `~/.codex/skills/mission-center`
- Windows: `%USERPROFILE%\.codex\skills\mission-center`
- Custom Codex home: `$CODEX_HOME/skills/mission-center`

## Script Expectations

Bundled scripts should use Python 3 and `pathlib` so paths work across macOS, Linux, and Windows.
Avoid shell-specific behavior inside Python scripts.

## Install Checks

After copying the skill folder:

1. Confirm `SKILL.md` exists in the installed folder.
2. Confirm `scripts/` and `references/` are copied.
3. Restart Codex so skill metadata reloads.
4. Ask Codex to use `$mission-center` in a test workspace.

## Smoke Test

Create a temporary workspace and run:

```bash
python3 ~/.codex/skills/mission-center/scripts/bootstrap_mission_center.py .
```

On Windows PowerShell:

```powershell
python $env:USERPROFILE\.codex\skills\mission-center\scripts\bootstrap_mission_center.py .
```

Expected result:

- A `MissionCenter/` folder is created in the current workspace.
- The folder contains `project.md`, `progress.md`, `tasks.md`, `decisions.md`, `smoke-tests.md`, `notes.md`, `snapshot.md`, and `closeout.md`.
