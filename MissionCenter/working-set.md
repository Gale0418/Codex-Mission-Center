<!-- Generated materialized view. Do not edit directly; rebuild from canonical MissionCenter files. -->
<!-- mission-center-derived schema=1.0 fingerprint-format=sha256-v2-lf source-fingerprint=150a0c10fafc164c45ad4b5f1ad7cb2d6479dc0a43a97317b131aac9edd2e71c -->
# 當前工作集

- 唯一真實來源: `tasks.md`
- 可執行項目數: 1

| ID | 標題 | 優先級 | 狀態 | 下一步 | 依賴 | 驗證方式 | 阻塞原因 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MC-071 | CodeRabbit Review、Main 發布與分支收斂 | P0 | Review | 驗證 CodeRabbit issues、重跑 release gates、提交推送 main 並清理等價或已合併遠端分支 | MC-070 | CodeRabbit 初審＋至多一次聚焦複審、完整本機門檻、GitHub main/branches 驗證、本機 Plugin smoke |  |
