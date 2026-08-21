# Steelman Evolution Gate

Steelman Evolution is a bounded advisory artifact, never a task lifecycle source or smoke-test record. Its `taskId` must exist in canonical `MissionCenter/tasks.md`; the validator rechecks that file without writing it.

## Routes

- `skip`: only for deterministic, low-risk, reversible work. It requires a `skipReason` and `maxRounds: 0`.
- `steelman_lite`: medium-risk bounded material trade-off; use at most one round and at least two explicitly labelled perspectives.
- `steelman_full`: high-risk evolution work; use at most two rounds and at least three perspectives.

`skip` is intentionally minimal: it needs only the base routing fields, a non-empty `skipReason`, `maxRounds: 0`, an empty-or-labelled perspective list, and `realSubagentsCompleted: false`. Lite and Full require the complete Steelman fields. `unknowns` must be a list; an empty list is valid when no unknown is honestly identified.

Every non-skip artifact records `trueGoal`, `currentBest`, `strongestOpposition`, `thirdRoute`, `flipVariables`, `smallestDiscriminatingTest`, `materialDissent`, `reopenConditions`, `qualityContract`, `architectureContract`, `evidenceRefs`, `unknowns`, `selectedRoute`, and `maxRounds`. Material dissent and reopen conditions may not be empty.

Perspectives must be labelled `simulated` or `real_subagent`. Simulated perspectives are reasoning aids and do not imply independent execution. `realSubagentsCompleted` is accepted only when at least one real perspective is marked completed and the artifact contains `authorization.explicitAuthorization: true` plus positive `budgets.total`, `perSeat`, `tool`, and `wallClock`. Missing authorization or any budget fails closed; the router never dispatches or claims a subagent completed.

```bash
python skills/mission-center/scripts/steelman_contract.py route . MC-048 --risk high
python skills/mission-center/scripts/steelman_contract.py validate artifact.json --workspace .
```

The output is bounded advisory data. It must not update `tasks.md`, `smoke-tests.md`, progress, closeout, HUD state, or any other lifecycle/evidence file.
