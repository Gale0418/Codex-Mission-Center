# Codex Mission Center

Mission Center is an offline, file-based Codex plugin and skill for turning vague goals into a local task workspace.
It is inspired by Linear-style project tracking and Superpowers-style execution discipline, but it does not connect to Linear or any external app.

Mission Center is per-project only.
Use it inside the current repo/workspace.
It creates or reads `./MissionCenter/`.
It does not monitor all repositories.
It does not merge tasks across projects.

![skills/mission-center/assets/visual-hub/readme-hero.png](https://pbs.twimg.com/media/HGvWLdmbcAAckSd.jpg)

## What It Does

- Asks exactly one focused intake question per turn until the goal is clear.
- Runs a creative cross-domain council when analogy can produce feasible ideas.
- Searches prior art before implementation, with Jina fallback and license checks.
- Presents approaches and writes only the user-approved rolling task draft.
- Creates or reuses `MissionCenter/` in the current workspace.
- Tracks project summary, progress, tasks, decisions, notes, snapshots, and smoke tests.
- Keeps task state local and readable as Markdown.
- Follows the user's language for generated workspace files, including Traditional Chinese.
- Shows one animated HUD helper per task and moves it with the task lifecycle.

## Plugin Layout

```text
.codex-plugin/plugin.json
assets/mission-center.svg
skills/mission-center/
```

Codex plugin hosts should read `.codex-plugin/plugin.json`, then load the bundled skill from `skills/mission-center/`.

## Read Here

Call your Codex:

```text
Use $mission-center to plan this goal, ask intake questions first, then create a MissionCenter workspace.
```

Install helpers live in `scripts/`. They delegate to one deterministic publisher so
the personal Skill and local marketplace plugin cannot silently drift apart.

The skill will create files like:

```text
MissionCenter/
  project.md
  progress.md
  tasks.md
  decisions.md
  smoke-tests.md
  notes.md
  snapshot.md
  closeout.md
  visual-hub.md
output/
  mission-center-assets/
    visual-summary.html
    visual-state.json
    update-visual-state.ps1
    mission-base-main.png
    mission-helper-roster-8-fixed.png
    mission-helper-roster-8-girls-2.png
```

Open `output/mission-center-assets/visual-summary.html` to view the local visual HUD.

The shortest local workflow is:

```bash
python skills/mission-center/scripts/bootstrap_mission_center.py . --language zh-TW
python skills/mission-center/scripts/sync_mission_center.py .
python skills/mission-center/scripts/doctor_mission_center.py .
```

## Local Publishing

The repository is the only authoring source. Preview changes before publishing:

```text
python scripts/publish_local.py --repo . --personal-skill ~/.codex/skills/mission-center --marketplace-plugin ~/.codex/local-marketplaces/mission-center/plugins/mission-center --dry-run
```

Use `--write` to replace both derived copies through staging directories, then use
`--verify` to detect drift. Add `--register` when you also want Codex to refresh the
local marketplace registration and reinstall the plugin with its icon metadata.
The bundled `scripts/install-unix.sh`, `scripts/install-plugin-unix.sh`,
`scripts/install-windows.ps1`, and `scripts/install-plugin-windows.ps1` wrappers
do this automatically for `--write`.

## Visual Assets

Mission Center bundles the HUD assets needed for offline use:

- `skills/mission-center/assets/visual-hub/mission-base-main.png`
- `skills/mission-center/assets/visual-hub/mission-helper-roster-8-fixed.png`
- `skills/mission-center/assets/visual-hub/mission-helper-roster-8-girls-2.png`
- `skills/mission-center/assets/visual-hub/visual-summary.html`
- `skills/mission-center/assets/visual-hub/update-visual-state.ps1`

## macOS Notes

The bundled Python scripts use `pathlib` and should work on macOS, Linux, and Windows with Python 3.
Shell examples use `~/.codex/skills` on macOS/Linux and `%USERPROFILE%\.codex\skills` on Windows.

## Attribution

This project is independently written and maintained.
It is inspired by the workflow concepts of Linear and Superpowers, but it does not include their app integrations, trademarks, code, documentation, icons, or branding.

## License

MIT License. See [LICENSE](LICENSE).
