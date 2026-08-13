# 重大教訓

> 只收錄已發生、具有再次發生價值，且解法已有證據支持的重大問題。
> 詳細事故資料位於 incidents/。
> 此文件必須保持精簡。

## 主動教訓

| ID | 適用情境 | 症狀 | 根因 | 正確處理 | 禁止重犯 | 驗證方式 | Incident | 最後確認 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CL-001 | Resume 選擇下一個工作 | 沒有 P0 時看不到 Ready 任務 | focus 僅篩選 P0 | 使用 bounded working-set 依狀態與優先級選取 | 不以空 focus 判定沒有工作 | test_resume_includes_p1_ready_when_no_p0 | INC-001 | 2026-08-13 |
| CL-002 | 跨日 Resume | 內容未變但 brief 被判 fresh | freshness 只比較內容指紋 | 分開驗 sourceFresh 與 dateFresh | 不以相同 hash 代替日期新鮮度 | test_status_is_date_stale_without_source_change | INC-002 | 2026-08-13 |
| CL-003 | 建立新任務樹 | 空白 smoke row 看似已有紀錄 | seed 寫入半空 manual row | seed 只建立表頭，Doctor 驗證證據欄位 | 不把 placeholder 當測試資料 | test_seed_creates_a_small_rolling_plan_with_canonical_statuses | INC-003 | 2026-08-13 |
| CL-004 | Git commit 前後同步 | commit 後 canonical 又被修改 | post-commit 執行 normalize／sync | 使用唯讀 check-only pre-commit | post-commit 不得改 tracked canonical files | test_existing_post_commit_is_never_changed | INC-004 | 2026-08-13 |
| CL-005 | 解析 Markdown tables | 同一列被不同工具解讀 | 多份 split-pipe parser 漂移 | 所有 consumer 共用 escaped-pipe parser | 不新增臨時 `split('\|')` parser | test_shared_parser_round_trips_escaped_pipe | INC-005 | 2026-08-13 |
| CL-006 | 長任務交接 | snapshot 與 tasks 狀態矛盾 | CLI 允許手填 canonical facts | checkpoint facts 由 tasks／git／fingerprint 導出 | note 不得覆寫 lifecycle facts | test_snapshot_is_derived_from_canonical_state | INC-006 | 2026-08-13 |
| CL-007 | Critic 未獲授權或預算 | prose 允許不派送但 validator 拒絕 | 路由與執行狀態混成單欄 | 分離 selectedRoute／executionStatus／requiredByPolicy | 不偽造 critics 或把未派送說成完成 | test_v11_state_machine_allows_honest_non_dispatch_and_requires_completed_contract | INC-007 | 2026-08-13 |

## 已解決索引

| ID | 狀態 | Resolved by | Incident |
| --- | --- | --- | --- |
