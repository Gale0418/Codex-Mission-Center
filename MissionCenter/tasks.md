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
| MC-009 | Adaptive Optimization | Epic |  | P1 | Done | Codex | MC-008 | 已完成 | router、schema、五項 Shadow fixture unittest | 8 | optimization, evolution | 規則＋結構化分類＋repo-local case retrieval；人工 promotion |
| MC-010 | Runtime Adapter | Epic |  | P1 | Done | Codex | MC-009 | 已完成 | runtime reducer、replay、stale/disconnect unittest | 8 | runtime, evolution | Task linking 僅允許明確 metadata 或選擇 |
| MC-011 | Mission Control HUD v2 | Epic |  | P1 | Done | Codex | MC-010 | 已完成 | HUD contract unittest＋本機 HTTP smoke | 5 | hud, evolution | Task 與 Agent 分層；控制面維持唯讀 |
| MC-012 | Verification / Release | Epic |  | P1 | Done | Codex | MC-009, MC-010, MC-011 | 已完成 | unittest、doctor、publish dry-run / verify | 5 | verification, release | Windows/Linux CI matrix |
| MC-013 | Daily Memory Maintenance | Epic |  | P0 | Done | Codex | MC-012 | 已完成 | daily grouping、dedupe、idempotence unittest | 3 | memory, compaction | 一天一區塊；無 daemon、零模型呼叫 |
| MC-014 | P0 Focus Materialized View | Task | MC-013 | P0 | Done | Codex | MC-013 | 已完成 | unfinished P0 only、Done removal、fingerprint tests | 2 | memory, priority | `tasks.md` 唯一 lifecycle truth |
| MC-015 | Compact Mission Brief | Task | MC-013 | P1 | Done | Codex | MC-013 | 已完成 | stale、byte budget、write-if-changed tests | 3 | memory, token-budget | 可刪除並重建；一般恢復讀取集縮減約 77% |
| MC-016 | Approved Guardrails | Task | MC-013 | P1 | Done | Codex | MC-013 | 已完成 | strict schema、invalid status tests | 2 | memory, safety | 禁止自動升格或停用 |
| MC-017 | Memory Routing / Verification / Release | Task | MC-013 | P0 | Done | Codex | MC-014, MC-015, MC-016 | 已完成 | resume routing、doctor、CI、docs smoke | 3 | verification, release | 最終擴充至 128 unittest；doctor 與 disposable publish verify 通過 |
| MC-018 | CodeRabbit Final Review and Hardening | Task |  | P0 | Done | Codex | MC-017 | 已完成 | scoped CodeRabbit review、regression tests、doctor、publish verify | 3 | review, security, verification | 2/3 hourly reviews used；10 first-pass issues、19 focused issues verified and resolved or merged |
| MC-019 | Dynamic Expert Council Gate | Task | MC-009 | P0 | Done | Codex | MC-018 | 已完成 | skill contract、完整 unittest、doctor、publish verify | 2 | council, optimization, token-budget | 前期 Creative Council 與中後期 Expert Council 分工；Agency Agents 契約模式採 Learn／Adapt |
| MC-020 | Local Skill and Plugin Release | Task | MC-012 | P0 | Done | Codex | MC-019 | 已完成 | personal／marketplace／cache 三方 verify＋plugin validator | 1 | release, plugin, verification | 安裝版本 `0.2.0+codex.e853fb1e3add497faf9d62b7b92c22aa` |
| MC-021 | Stabilization and Contract Fix Pass | Task | MC-012 | P0 | Done | Codex | MC-020 | 已完成 | 完整 unittest、doctor、CodeRabbit、publish verify | 3 | stabilization, runtime, optimization, verification | 修正跨平台 fingerprint、runtime 狀態、定性路由與 composite validation；CodeRabbit 2 issues 已驗證修正 |
