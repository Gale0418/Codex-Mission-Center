# Persistent Project Map

`project_map.py` derives a bounded, read-only map from `MissionCenter/project.md`
and `MissionCenter/tasks.md`. It writes `output/mission-center-project-map/`
with a canonical source fingerprint, `project-map.json`, an escaped
`project-map.html`, and a `project-map.manifest.json` commit marker. JSON and
HTML are individually atomic; consumers must validate the manifest's generation
and file hashes before treating the pair as one published view. RuntimeState
remains under `output/mission-center-runtime/` and is never read or changed by
this map. The public JSON shape is described by
`skills/mission-center/schemas/project-map.schema.json` and is also checked by
the stdlib validator in `project_map.py`.

Run from the checkout with `py -3 skills/mission-center/scripts/project_map.py .`
on Windows or `python3 .../project_map.py .` on Unix. The command does not
change `MissionCenter/tasks.md`; rerun it after an approved task/project edit.
An existing lock is always treated as busy, including a stale-looking lock;
there is no automatic stale deletion. For recovery, stop competing publishers,
inspect the exact lock's recorded `pid` and `token`, verify that the recorded
owner process is gone, remove only that exact lock, and rerun the publisher.
