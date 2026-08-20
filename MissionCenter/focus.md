<!-- Generated materialized view. Do not edit directly; rebuild from canonical MissionCenter files. -->
<!-- Deprecated compatibility view: focus.md is generated from tasks.md only and must never be edited or treated as a second lifecycle source. -->
<!-- mission-center-derived schema=1.0 fingerprint-format=sha256-v2-lf source-fingerprint=563e6ab756050da765c74a29571deca6873e37539f06b02c08790ce005976d4d -->
# P0 焦點

- 唯一真實來源: `tasks.md`
- 未完成 P0: 2

| ID | 標題 | 狀態 | 下一步 | 依賴 | 驗證方式 |
| --- | --- | --- | --- | --- | --- |
| MC-046 | OWO+ v0.4 Causal Continuity and Evolution Loop | In Progress | 執行 MC-051 完整驗證、審查與發布閘門 | MC-045 | 端到端換班 smoke、Shift-Loss eval、full regression、Doctor、publish verify |
| MC-051 | OWO+ v0.4 Review, Compatibility and Release | Review | 等待 CodeRabbit 上傳同意與 critic_full 總額／席次／工具／時限預算核准 | MC-048, MC-049, MC-050 | full unittest、Doctor、CodeRabbit／Critic gate、publish verify |
