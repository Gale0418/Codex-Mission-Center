# 重要護欄

自動化不得新增、升格或停用護欄；變更必須經人工明確核准。

| ID | 嚴重度 | 適用情境 | 曾踩過的坑 | 必須遵守 | 驗證方式 | 來源 | 最後確認 | 狀態 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GR-001 | Critical | 任何 Task 狀態同步 | Runtime Agent 完成被誤當成 Task Done | `tasks.md` 永遠是唯一 lifecycle 與 ordering 真實來源 | runtime agent-finished/task-state test | ADR-005 | 2026-08-09 | Active |
| GR-002 | High | 重建 project summary | sync 曾重複堆疊活動欄位並覆蓋自訂內容 | 保留自訂欄位、區段與既有活動；新活動寫入 daily log | workspace sync regression tests | MC-002 | 2026-08-09 | Active |
| GR-003 | High | 發布 Skill 與 plugin | personal skill 與 marketplace plugin 目標容易混用 | 使用不同目標根目錄並執行 dry-run、write、verify | publish disposable verify | MC-012 | 2026-08-09 | Active |
| GR-004 | High | 啟用 Live Runtime | optional 依賴缺失可能破壞核心離線流程 | WebSocket 僅為 optional；缺少時退回靜態 HUD | runtime optional dependency tests | MC-010 | 2026-08-09 | Active |
| GR-005 | Critical | 整理 MissionCenter 記憶 | 直接編輯短摘要會製造第二個真實來源 | `brief.md` 與 `focus.md` 只能重建；canonical evidence 不得自動刪除 | doctor memory tests | MC-013, MC-017 | 2026-08-09 | Active |
| GR-006 | High | 從失敗提取護欄 | 自動升格錯誤推論會永久污染後續任務 | 自動化只可提出候選；Active 或 Superseded 必須人工核准 | guardrail validation and human review | MC-016 | 2026-08-09 | Active |
| GR-007 | High | 使用 CodeRabbit 審查 | 一小時內重複送審或一次餵太多檔案會浪費有限額度 | 每小時最多 3 次、每次最多 150 檔；先排除大型生成物與肯定無關檔案，意見須驗證後才修改 | `.coderabbit.yaml`、review receipt 與本機 regression tests | 使用者明確指示 | 2026-08-09 | Active |
