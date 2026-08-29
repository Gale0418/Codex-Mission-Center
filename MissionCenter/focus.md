<!-- Generated materialized view. Do not edit directly; rebuild from canonical MissionCenter files. -->
<!-- Deprecated compatibility view: focus.md is generated from tasks.md only and must never be edited or treated as a second lifecycle source. -->
<!-- mission-center-derived schema=1.0 fingerprint-format=sha256-v2-lf source-fingerprint=6eda1e1152692c717c576dbc3c8fb0405aa86d72fe51f0537aeaf37669e6992c -->
# P0 焦點

- 唯一真實來源: `tasks.md`
- 未完成 P0: 4

| ID | 標題 | 狀態 | 下一步 | 依賴 | 驗證方式 |
| --- | --- | --- | --- | --- | --- |
| MC-061 | Rust-only v0.5.1 Wave 0：契約／供應鏈基線 | In Progress | 建立 Rust workspace、版本與依賴／來源鎖定清單，完成 contract／supply-chain review | MC-060 | cargo metadata --locked、lockfile／hash／policy fixture（待實跑） |
| MC-062 | Rust-only v0.5.1 Wave 1：Core 邊界與狀態契約 | Backlog | 實作 Core domain、狀態 reducer 與錯誤契約，對齊既有 lifecycle truth | MC-061 | Rust Core unit／integration tests：schema、reducer、error mapping（待實跑） |
| MC-064 | Rust-only v0.5.1 Wave 3：Policy／Guardrails／Evidence | Backlog | 實作 Policy、guardrails 與 revision-bound evidence gate，維持 fail-closed | MC-063 | Policy／evidence schema fixtures、拒絕未驗證狀態的 tests（待實跑） |
| MC-066 | Rust-only v0.5.1 Wave 5：歷史重驗／Stable 收斂 | Backlog | 執行歷史任務 evidence 重驗與 migration dry-run，完成 Stable release gate | MC-065 | 歷史重驗矩陣、完整 Rust tests、Doctor、clean-checkout 與 stable manifest verify（待實跑） |
