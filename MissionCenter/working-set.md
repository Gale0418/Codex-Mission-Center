<!-- Generated materialized view. Do not edit directly; rebuild from canonical MissionCenter files. -->
<!-- mission-center-derived schema=1.0 fingerprint-format=sha256-v2-lf source-fingerprint=6eda1e1152692c717c576dbc3c8fb0405aa86d72fe51f0537aeaf37669e6992c -->
# 當前工作集

- 唯一真實來源: `tasks.md`
- 可執行項目數: 1

| ID | 標題 | 優先級 | 狀態 | 下一步 | 依賴 | 驗證方式 | 阻塞原因 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MC-061 | Rust-only v0.5.1 Wave 0：契約／供應鏈基線 | P0 | In Progress | 建立 Rust workspace、版本與依賴／來源鎖定清單，完成 contract／supply-chain review | MC-060 | cargo metadata --locked、lockfile／hash／policy fixture（待實跑） |  |
