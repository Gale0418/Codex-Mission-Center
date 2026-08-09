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
| 2026-08-09 | MC-009 | Adaptive Optimization 路由、budget、hard constraint、Pareto 與五項 fixtures | 執行完整 unittest discovery | 無 metric 回 research_spike；Shadow 不自動採用；所有測試通過 | 101 tests OK | 通過 | automated |
| 2026-08-09 | MC-010 | Runtime event、approval、subagent、亂序、stale、reconnect、隱私與 optional fallback | 執行 test_runtime_protocol、compileall 與 `python -S ... connect` | reducer 正確；Task 不變；缺依賴時安全提示 | runtime tests、compileall、fallback OK | 通過 | automated |
| 2026-08-09 | MC-011 | Mission Island、Live Agents、Pixel Mission Map 與無 Runtime 降級 | loopback 啟動 `mission_runtime.py serve` 並 HTTP GET | HTTP 200，頁面含 Live Agents／Pixel Mission Map，靜態 HUD 可用 | HTTP HUD fallback smoke: OK | 通過 | automated |
| 2026-08-09 | MC-012 | 完整 release gate | unittest、doctor、獨立暫存目錄 publish dry-run→write→verify、git diff --check | 全部通過且不修改實際安裝副本 | 101 tests OK；doctor OK；publish verify OK；diff check OK | 通過 | release |
| 2026-08-09 | MC-013 | 每日低噪音維護與同日去重 | 執行 `test_mission_maintenance` daily/idempotence tests | 同日合併、跨日分段、重複訊息不重寫 | 測試通過；第二次 sync changed 為空 | 通過 | automated |
| 2026-08-09 | MC-014 | 未完成 P0 衍生視圖 | 執行雙語 P0、Done removal、doctor mismatch tests | 只列未完成 P0，Task 完成後消失 | 英文與繁中 fixtures 均通過 | 通過 | automated |
| 2026-08-09 | MC-015 | compact brief freshness 與 context budget | 比較 canonical resume set 與 `brief.md + focus.md` bytes | 衍生視圖可驗 stale，且一般讀取集明顯縮小 | 11,552 bytes 降至 2,655 bytes，約減少 77% | 通過 | automated |
| 2026-08-09 | MC-016 | 人工護欄 schema 與升格邊界 | 執行 invalid ID、severity、date、status 與 doctor tests | 非法值 fail closed；Candidate 不可冒充 Active | 測試通過；6 個人工核准 Active 護欄 | 通過 | automated |
| 2026-08-09 | MC-017 | Memory release gate | 完整 unittest、doctor、暫存 publish dry-run→write→verify | 全部通過且不修改實際安裝副本 | 112 tests OK；doctor OK；publish verify OK | 通過 | release |
| 2026-08-09 | MC-018 | CodeRabbit 審查與問題修正 | 先掃 68 個文字變更，再聚焦 10 個 scripts；逐項重現後補 regression tests | 不掃大型二進位；真問題才修；核心契約與跨平台行為不退化 | 2 次 review；128 tests OK；doctor、compileall、diff check OK | 通過 | release |
| 2026-08-09 | MC-019 | 依複雜度啟動的動態專家會議與 Council 分工 | 執行 skill contract、完整 unittest、skill validator、doctor、compileall、diff check 與暫存 publish verify | deterministic 工作 skip；Lite／Full 契約、腦洞席、最新來源、Jina、handoff 與額度 gate 均受測 | 129 tests OK；skill valid；doctor、compileall、diff check、publish verify OK | 通過 | release |
| 2026-08-09 | MC-020 | 個人 Skill、local marketplace 與 Codex plugin cache 發布 | dry-run 後執行正式 write／register，再以 publish verify、cache diff 與 plugin validator 檢查 | 三個已安裝副本與 repo canonical Skill 一致；plugin 可重新註冊 | personal／marketplace／cache no changes；plugin validation passed；版本 0.2.0+codex.e853fb1e3add497faf9d62b7b92c22aa | 通過 | release |
