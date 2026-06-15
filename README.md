# Codex Mission Center

Mission Center is an offline, file-based Codex plugin and skill for turning vague goals into a local task workspace.
It is inspired by Linear-style project tracking and Superpowers-style execution discipline, but it does not connect to Linear or any external app.

![skills/mission-center/assets/visual-hub/readme-hero.png](https://pbs.twimg.com/media/HGvWLdmbcAAckSd.jpg)

## What It Does

- Asks focused intake questions before work starts.
- Runs a lightweight multi-angle intake council.
- Creates or reuses `MissionCenter/` in the current workspace.
- Tracks project summary, progress, tasks, decisions, notes, snapshots, and smoke tests.
- Keeps task state local and readable as Markdown.
- Follows the user's language for generated workspace files, including Traditional Chinese.
- Bundles a local animated visual HUD with a 16-character helper roster.
- Supports a future global overview mode without mixing unrelated workspace tasks.

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

Install helpers live in `scripts/` if you want the plugin or skill on disk.

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

## Visual Assets

Mission Center bundles the HUD assets needed for offline use:

- `skills/mission-center/assets/visual-hub/mission-base-main.png`
- `skills/mission-center/assets/visual-hub/mission-helper-roster-8-fixed.png`
- `skills/mission-center/assets/visual-hub/mission-helper-roster-8-girls-2.png`
- `skills/mission-center/assets/visual-hub/visual-summary.html`
- `skills/mission-center/assets/visual-hub/update-visual-state.ps1`

## Global Overview Safety

Mission Center is intentionally local-first.
If you later build a global overview for multiple Codex workspaces, treat it as a dashboard only:

- Each workspace keeps its own `MissionCenter/` as the source of truth.
- A global hub may read summaries from multiple workspaces.
- A global hub must not merge task tables across folders.
- A global hub must not mutate another workspace's task files unless that workspace is explicitly selected.
- Every global card should include a workspace path or workspace ID.

In short: global overview, not global task soup.

## macOS Notes

The bundled Python scripts use `pathlib` and should work on macOS, Linux, and Windows with Python 3.
Shell examples use `~/.codex/skills` on macOS/Linux and `%USERPROFILE%\.codex\skills` on Windows.

## Attribution

This project is independently written and maintained.
It is inspired by the workflow concepts of Linear and Superpowers, but it does not include their app integrations, trademarks, code, documentation, icons, or branding.

## License

Apache-2.0. See [LICENSE](LICENSE).

123
