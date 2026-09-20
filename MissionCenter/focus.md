<!-- Generated materialized view. Do not edit directly; rebuild from canonical MissionCenter files. -->
<!-- Deprecated compatibility view: focus.md is generated from tasks.md only and must never be edited or treated as a second lifecycle source. -->
<!-- mission-center-derived schema=1.0 fingerprint-format=sha256-v2-lf source-fingerprint=9fe2644c1502c782c8cdb9404684c096aa8f038822a9cee9c66a88496db879db -->
# P0 焦點

- 唯一真實來源: `tasks.md`
- 未完成 P0: 1

| ID | 標題 | 狀態 | 下一步 | 依賴 | 驗證方式 |
| --- | --- | --- | --- | --- | --- |
| MC-079 | 歷史 CodeRabbit 審查、本機試運行與 Main 收斂 | In Progress | 將近十五次提交的有效程式與測試改動控制在 150 檔內送交 CodeRabbit，驗證並修正真實問題後完成本機試運行、推送 main 與遠端分支清理 | MC-078 | CodeRabbit committed review、Rust/Python gates、installed Plugin smoke、GitHub main/branch verification |
