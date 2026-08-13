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
| 2026-08-13 | MC-038 | Working Set、跨日 freshness 與 bounded Resume | 執行 maintenance/status/resume 行為測試與實際 CLI | 最多 6 項；跨日 stale；封包不超過 16 KiB | 相關回歸通過；實測 5,050 bytes、fresh、未截斷 | 通過 | automated |
| 2026-08-13 | MC-039 | Critical Lessons schema、6 KiB 與 incident confinement | 執行 lesson/doctor/traversal 回歸 | 缺證據、越界 pointer 與超限皆 fail closed | 回歸通過；`../README.md` 被拒絕 | 通過 | automated |
| 2026-08-13 | MC-040 | Snapshot Resume 與跨 invocation Retry Gate | 執行 execution continuity 回歸 | active checkpoint 可恢復；重複 signature 進 diagnosis；新假設＋證據才解鎖 | 10 項 continuity tests 通過 | 通過 | automated |
| 2026-08-13 | MC-041 | Parser、smoke、leaf progress、freshness、hook 與 force | 執行完整 unittest／pytest 與 Doctor | 共用 parser；無假 smoke；Epic 不重算；hook 不改 tracked files | unittest 201、pytest 201＋70 subtests、Doctor OK | 通過 | automated |
| 2026-08-13 | MC-042 | 薄路由、繁中、Plugin/Skill validation 與 benchmark | quick_validate、validate_plugin、byte benchmark | SKILL <= 6144 bytes；驗證通過；不捏造節省率 | SKILL 5,372 bytes；兩項驗證通過；candidate 比舊熱區多 993 bytes | 通過 | release |
| 2026-08-13 | MC-043 | 外部審查、本機發布與 GitHub 交付 | CodeRabbit 三輪、完整 unittest、Doctor、Skill/Plugin validation、publish verify 與 git push | 可重現 findings 修復；最終 Rabbit 0 findings；來源副本一致；遠端 main 可用 | Rabbit 初審 10 findings 全修；delta 1 Minor 補實跑測試；最終 0 findings；209 tests、Doctor、Skill/Plugin validation OK | 通過 | release |
| 2026-08-13 | MC-037 | v0.3 整體收斂 | 完整 unittest、pytest、Doctor、Skill/Plugin validation 與交付證據 | 所有子任務有 evidence；無未處置 Critical/High | 201 tests、70 subtests、Doctor/validators OK；兩位 critic 的 3 個 High 已修 | 通過 | release |
| 2026-08-09 | MC-017 | Memory release gate | 完整 unittest、doctor、暫存 publish dry-run→write→verify | 全部通過且不修改實際安裝副本 | 112 tests OK；doctor OK；publish verify OK | 通過 | release |
| 2026-08-09 | MC-018 | CodeRabbit 審查與問題修正 | 先掃 68 個文字變更，再聚焦 10 個 scripts；逐項重現後補 regression tests | 不掃大型二進位；真問題才修；核心契約與跨平台行為不退化 | 2 次 review；128 tests OK；doctor、compileall、diff check OK | 通過 | release |
| 2026-08-09 | MC-019 | 依複雜度啟動的動態專家會議與 Council 分工 | 執行 skill contract、完整 unittest、skill validator、doctor、compileall、diff check 與暫存 publish verify | deterministic 工作 skip；Lite／Full 契約、腦洞席、最新來源、Jina、handoff 與額度 gate 均受測 | 129 tests OK；skill valid；doctor、compileall、diff check、publish verify OK | 通過 | release |
| 2026-08-09 | MC-020 | 個人 Skill、local marketplace 與 Codex plugin cache 發布 | dry-run 後執行正式 write／register，再以 publish verify、cache diff 與 plugin validator 檢查 | 三個已安裝副本與 repo canonical Skill 一致；plugin 可重新註冊 | personal／marketplace／cache no changes；plugin validation passed；版本 0.2.0+codex.e853fb1e3add497faf9d62b7b92c22aa | 通過 | release |
| 2026-08-09 | MC-021 | 跨平台 derived view、最佳化 manifest、Runtime 事件與注意力穩定化 | 完整 unittest、doctor、publish dry-run／verify 與 CodeRabbit 聚焦審查 | 跨平台 fixture 有回歸保護；無效 runtime payload 保留 last-valid；兩項 Rabbit issues 修正；本機 gate 通過 | 140 tests OK（Rabbit regression 後最終重跑）；doctor OK；CodeRabbit 2 issues 已修正；publish dry-run OK | 通過 | release |
| 2026-08-09 | MC-022 | 代表性 Prior Art 深篩與採納判斷 | research contract tests＋notes evidence | 搜廣篩深、3–7 為彈性指引、含維護與退出風險 | skill contract tests 通過；6 類代表來源記錄 Adopt／Adapt／Learn／Reject | 通過 | research |
| 2026-08-09 | MC-023 | 目前 Codex thread lifecycle 與 transport 契約 | runtime tests＋本機 schema/stdio probe | 官方 status tagged object、未知事件 fail closed、明確 endpoint | thread/started、status/changed、thread/closed 與 initialize/list probe 驗證 | 通過 | integration |
| 2026-08-09 | MC-024 | 低噪音 HUD 與 Runtime/Task 分層 | HUD tests＋Chrome 視覺驗收 | drawer 預設收合、Task/Agent entity 分離、無 console error | Chrome 驗證膠囊、拓樸、圖片與 zero console error | 通過 | visual |
| 2026-08-09 | MC-025 | 收斂 release gate | 完整 unittest、doctor、CodeRabbit、publish verify | 全部 release gate 通過 | 兩輪 CodeRabbit 共 9 issues 均驗證修正；三方 publish verify 無 drift | 通過 | release |
| 2026-08-09 | MC-026 | Representative GitHub Screening 契約 | test_skill_contract | 不湊 quota、不以 stars 當品質、結論可追溯 | 契約測試通過 | 通過 | automated |
| 2026-08-09 | MC-027 | Codex lifecycle mapping 與 malformed frame | test_runtime_protocol | current notifications 正確；malformed/unknown ignored | runtime regression tests 通過 | 通過 | automated |
| 2026-08-09 | MC-028 | stdio abstraction、清理與封裝限制 | unit tests＋本機 app-server probe | 不經 shell；partial failure cleanup；WindowsApps fail actionable | raw app-server initialize/list 成功；adapter 回歸與封裝限制測試通過 | 通過 | integration |
| 2026-08-09 | MC-029 | Attention capsule、drawer 與父子拓樸 | HUD tests＋Chrome click smoke | 五種 attention；Generation 0/1 可見；無橫向溢出 | 4 Agent fixture 顯示 2 generations、2 attention，drawer 345/345 px | 通過 | visual |
| 2026-08-09 | MC-030 | activityKind、last-valid、adaptive polling 與位置穩定 | runtime/HUD tests＋CodeRabbit regression | 不解析敏感文字；隱藏降頻；同 zone 不亂跳 | Object.hasOwn fallback、position cache、30 秒 hidden polling 受測 | 通過 | performance |
| 2026-08-09 | MC-031 | 文件、完整驗證與本機 Plugin 發布 | full unittest、doctor、compileall、diff check、publish verify | 全綠且 personal／marketplace／cache 一致 | 155 tests OK；plugin `0.2.0+codex.8f4f2583757549d594eb7d33b39f12bc` verify 無 drift | 通過 | release |
| 2026-08-10 | MC-033 | Completion Critic Council 全流程契約 | 完整 unittest、三席 critic＋獨立 arbiter、CodeRabbit 三輪限額審查 | 動態選角、真實唯讀子代理、兩波上限、finding disposition 與假 Full pass 防護成立 | 165 tests OK；初審與唯一 delta 完成；最終 CodeRabbit 0 issues | 通過 | release |
| 2026-08-10 | MC-034 | 遊戲、文章、對話、UI、CLI/API 動態成果路由 | test_skill_contract 與 critic delta review | 依 artifact／journey／audience／risk 選角，混合成果拆 lane | Skill contract tests 與三席獨立 critic evidence 通過 | 通過 | automated |
| 2026-08-10 | MC-035 | Critic 預算、snapshot、coverage、風險與 lifecycle validator | test_critic_contract、compileall、doctor | 未授權、假席次、Critical waiver、unknown required lane、缺 game journey 皆 fail closed | 7 validator tests 通過；Task/Runtime/smoke evidence 邊界保留 | 通過 | automated |
| 2026-08-10 | MC-036 | 完整驗證、CodeRabbit 與本機發布 | full unittest、doctor、CodeRabbit、publish write/register/verify | 全部 release gate 通過且本機三方副本一致 | 165 tests OK；2 invalid Minor；4 valid Major 已修；最終 0 issues；plugin `0.2.0+codex.f87f7ed4885d4ad89347817f89aa38b8` 三方 verify 無 drift | 通過 | release |
