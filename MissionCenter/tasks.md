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
| MC-022 | Prior Art Deep Screening | Epic |  | P1 | Done | Codex | MC-021 | 已完成 | research contract、notes evidence、skill tests | 3 | research, convergence | 搜廣、篩深；不為湊數加入弱候選 |
| MC-023 | Runtime Correctness and Transport | Epic |  | P1 | Done | Codex | MC-022 | 已完成 | runtime protocol tests、local app-server smoke | 5 | runtime, correctness | 僅監看明確連接的 endpoint |
| MC-024 | HUD Attention UX | Epic |  | P1 | Done | Codex | MC-023 | 已完成 | HUD contract tests、Chrome visual smoke | 4 | hud, attention, ux | Task 與 Runtime Agent 永久分層 |
| MC-025 | Convergence Verification and Release | Epic |  | P1 | Done | Codex | MC-022, MC-023, MC-024 | 已完成 | unittest、doctor、publish verify、git push | 3 | verification, release | release gate 與本機發布證據完成；Git push 由最終提交收尾 |
| MC-026 | 強化 representative research contract | Task | MC-022 | P0 | Done | Codex | MC-021 | 已完成 | test_skill_contract | 2 | research, p0 | 數量為指引，不是硬湊 quota |
| MC-027 | 修正 Codex thread lifecycle mapping | Task | MC-023 | P0 | Done | Codex | MC-026 | 已完成 | test_runtime_protocol | 2 | runtime, schema, p0 | malformed / unknown fail closed |
| MC-028 | 加入最小 stdio transport abstraction | Task | MC-023 | P0 | Done | Codex | MC-027 | 已完成 | unit tests、local initialize smoke | 3 | runtime, transport, p0 | 不經 shell；WindowsApps 封裝限制明確 fail closed |
| MC-029 | 建立 attention capsule 與 Live Agents drawer | Task | MC-024 | P0 | Done | Codex | MC-027 | 已完成 | HUD tests、Chrome smoke | 2 | hud, ux, p0 | 只提升五種 attention；加入父子世代拓樸 |
| MC-030 | 實作受限 activity mapping 與 adaptive polling | Task | MC-024 | P1 | Done | Codex | MC-027, MC-029 | 已完成 | HUD/runtime tests | 2 | hud, privacy, performance | 不解析 prompt/command/tool args；zone 不變時保留位置 |
| MC-031 | 完成文件、全量驗證與發布證據 | Task | MC-025 | P0 | Done | Codex | MC-026, MC-028, MC-029, MC-030 | 已完成 | full unittest、doctor、publish verify | 3 | docs, release, p0 | CodeRabbit 兩輪、三方本機發布 verify 完成 |
| MC-032 | Optional Persistent Project Map | Experiment |  | P1 | Ready | Codex | MC-026 | 設計 html/json/lock、元件證據與 stale 契約 | 跨語言 spike、fingerprint tests、人工 review | 5 | codemap, experiment, visualization | 與 RuntimeState 分離；不得偽造 caller、依賴或 test evidence |
| MC-033 | Completion Adversarial Critic Council | Epic |  | P0 | Done | Codex | MC-031 | 已完成 | skill contract、完整 unittest、獨立 review | 4 | critic, council, verification | 真實子代理唯讀；不建立第二套 lifecycle |
| MC-034 | 定義成果路由與龜毛評審契約 | Task | MC-033 | P0 | Done | Codex | MC-031 | 已完成 | reference 與 skill contract tests | 2 | critic, routing, p0 | 初審＋最多一次 delta 複審 |
| MC-035 | 鎖定證據、預算與 Task 邊界 | Task | MC-033 | P0 | Done | Codex | MC-034 | 已完成 | orchestration / execution gate tests | 2 | evidence, budget, p0 | 評語不得冒充 smoke-test evidence |
| MC-036 | 驗證、兔子審查與本機發布 | Task | MC-033 | P0 | Done | Codex | MC-034, MC-035 | 已完成 | unittest、doctor、CodeRabbit、publish verify | 2 | review, release, p0 | 最終 0 issues；本機 plugin `0.2.0+codex.f87f7ed4885d4ad89347817f89aa38b8` |
