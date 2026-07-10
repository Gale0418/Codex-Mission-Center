# 冒煙測試

| 日期 | 對應任務 ID | 測試內容 | 測試方式 | 預期結果 | 實際結果 | 通過 / 失敗 | 類型 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-07-10 | MC-001 | canonical layout 與 bootstrap 一致 | 執行 test_bootstrap_mission_center | 兩語系皆產出 9 個檔案 | 2 tests OK | 通過 | automated |
| 2026-07-10 | MC-002 | bootstrap / normalize / sync 行為 | 執行完整 unittest discovery | 所有測試通過 | 69 tests OK | 通過 | automated |
| 2026-07-10 | MC-003 | HUD 狀態與繁中欄位 | 執行 test_visual_state | zone 與非法狀態正確 | 6 tests OK | 通過 | automated |
| 2026-07-10 | MC-004 | publisher dry-run / verify / target safety | 執行 test_publish_local | publisher 契約通過 | 7 tests OK | 通過 | automated |
| 2026-07-10 | MC-005 | 單 workspace doctor | 執行 doctor_mission_center.py /tmp/mc-demo | 回傳 0 | MissionCenter doctor: OK | 通過 | automated |
| 2026-07-10 | MC-006 | CI workflow 與遠端保護規則 | 執行 test_per_project_release 並查詢 GitHub branch protection API | push、PR 指令存在，test 為 required check | strict=true、contexts=[test]、enforce_admins=true | 通過 | automated |
| 2026-07-10 | MC-007 | release checklist 邊界 | 執行 test_per_project_release | checklist 含發布與禁止功能 | 6 tests OK | 通過 | automated |
| 2026-07-10 | MC-008 | demo fixture 可供 sync 與 doctor 使用 | 執行 doctor_mission_center.py tests/fixtures/demo-workspace | 回傳 0 | MissionCenter doctor: OK | 通過 | automated |
