# Execution Pulse／Handoff

Execution pulse 是可丟棄的 bounded evidence，不是任務生命週期資料。唯一允許的 ledger 是 `MissionCenter/execution-ledger.jsonl`；`tasks.md` 仍是狀態、順序、優先級、依賴與下一步的唯一真實來源。

每筆 pulse 必須只包含 `taskId`、`phase`、`outcome`、`nextAction`、`evidenceRef`、`budgetRemaining` 與 `causalParent`（另有產生的 `pulseId`），且 `taskId` 必須先存在於 canonical `tasks.md`。系統會拒絕 prompt、reasoning、完整 command、secret、token、password、credential 等欄位或疑似秘密內容；單筆最多 4 KiB，ledger 最多 256 KiB。`causalParent` 必須指向同一 ledger 中既有的 pulse，重送相同 `pulseId` 與內容是 idempotent，內容不同則拒絕。

換班只讀這個已知 ledger，取指定 task 的最新 pulse 與 bounded causal chain，並重新從 `tasks.md` 確認最新 task 存在。handoff 明示 `lifecycleSource: tasks.md`，攜帶 bounded `canonicalTask`（`ID`、`Title`、`Priority`、`Status`、`Depends on`、`Next action`、`Verification`）；pulse 的 `nextAction` 只會以 `executionNextAction`／`nextActionSource: execution-pulse` 表示，絕不覆蓋 canonical `Next action`。ledger 遺失時安全省略；格式損壞、超限或最新 task 已不存在時 fail closed，不掃描其他目錄，也不把 handoff 升格成 lifecycle truth。

```bash
python skills/mission-center/scripts/mission_maintenance.py . pulse \
  --task-id MC-047 --phase implement --outcome "pulse A complete" \
  --next-action "run focused tests" --evidence-ref tests/test_mission_maintenance.py \
  --budget-remaining 1200
python skills/mission-center/scripts/mission_maintenance.py . handoff --task-id MC-047
python skills/mission-center/scripts/mission_maintenance.py . resume --json
```

Resume 的所有 `content`（含 handoff）共用 16 KiB UTF-8 fuse；超限時保留 `[TRUNCATED]` 與 `readNext`，不得繞過 fuse 重新掃讀全部 ledger 或 canonical records。
