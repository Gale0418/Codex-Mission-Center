<!-- Generated materialized view. Do not edit directly; rebuild from canonical MissionCenter files. -->
<!-- mission-center-derived schema=1.0 fingerprint-format=sha256-v2-lf source-fingerprint=39089e03c82f8c8ee5a05e46e4f1af1acea160f194f8dd5f176037974e190e4d -->
# 當前工作集

- 唯一真實來源: `tasks.md`
- 可執行項目數: 1

| ID | 標題 | 優先級 | 狀態 | 下一步 | 依賴 | 驗證方式 | 阻塞原因 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MC-067 | Rust Sync Derived Views and Maintainability Probe | P1 | Review | 讓 Rust sync 原子刷新 brief／working-set／focus，並驗證重複邏輯、自然模組邊界與低 context 維護性 | MC-066 | Rust 1.98 fmt／clippy／workspace tests、Python differential、真實 sync→status→resume→Doctor 與多平台 stable gate |  |
