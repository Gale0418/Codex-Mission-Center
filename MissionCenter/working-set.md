<!-- Generated materialized view. Do not edit directly; rebuild from canonical MissionCenter files. -->
<!-- mission-center-derived schema=1.0 fingerprint-format=sha256-v2-lf source-fingerprint=563e6ab756050da765c74a29571deca6873e37539f06b02c08790ce005976d4d -->
# 當前工作集

- 唯一真實來源: `tasks.md`
- 可執行項目數: 2

| ID | 標題 | 優先級 | 狀態 | 下一步 | 依賴 | 驗證方式 | 阻塞原因 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MC-046 | OWO+ v0.4 Causal Continuity and Evolution Loop | P0 | In Progress | 執行 MC-051 完整驗證、審查與發布閘門 | MC-045 | 端到端換班 smoke、Shift-Loss eval、full regression、Doctor、publish verify |  |
| MC-051 | OWO+ v0.4 Review, Compatibility and Release | P0 | Review | 等待 CodeRabbit 上傳同意與 critic_full 總額／席次／工具／時限預算核准 | MC-048, MC-049, MC-050 | full unittest、Doctor、CodeRabbit／Critic gate、publish verify |  |

## 下一步候選

- MC-032 — Optional Persistent Project Map
- MC-044 — Codex CLI 0.147 Agent Plugin Compatibility Spike
- 以上僅為候選，開始前仍須在 `tasks.md` 升格為 Ready。
