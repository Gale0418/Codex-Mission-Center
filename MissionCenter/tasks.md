# 任務

| ID | 標題 | 類型 | 父層 | 優先級 | 狀態 | 負責人 | 依賴 | 下一步 | 驗證方式 | 估時 | 標籤 | 備註 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MC-001 | 統一 workspace layout 文件與 bootstrap 產物 | Task |  | P1 | Done | Codex |  | 已完成 | bootstrap exact-layout tests | 2 | plan, verification |  |
| MC-002 | 補 bootstrap / normalize / sync 測試 | Task |  | P1 | Done | Codex | MC-001 | 已完成 | unittest focused modules | 3 | verification |  |
| MC-003 | 補 visual_state 測試 | Task |  | P1 | Done | Codex | MC-002 | 已完成 | unittest visual-state module | 2 | verification |  |
| MC-004 | 補 publish_local dry-run / verify 測試 | Task |  | P1 | Done | Codex | MC-002 | 已完成 | unittest publish module | 2 | verification | 既有覆蓋已符合需求 |
| MC-005 | 補單 workspace doctor script | Task |  | P1 | Done | Codex | MC-001 | 已完成 | doctor returns zero | 3 | execution, verification |  |
| MC-006 | 補 GitHub Actions CI | Task |  | P2 | Done | Codex | MC-002, MC-005 | 已完成 | release metadata tests | 1 | execution | branch protection 另設 |
| MC-007 | 補 release checklist | Task |  | P2 | Done | Codex | MC-006 | 已完成 | release metadata tests | 1 | closeout |  |
| MC-008 | 補 demo workspace fixture | Task |  | P1 | Done | Codex | MC-005 | 已完成 | doctor returns zero | 2 | verification |  |
