<!-- Generated materialized view. Do not edit directly; rebuild from canonical MissionCenter files. -->
<!-- mission-center-derived schema=1.0 fingerprint-format=sha256-v2-lf source-fingerprint=57dda425c71bcfc266db17da1848e9afd7a9064de298956c7dcbc9c694ea9fad -->
# 任務簡報

- 最後整理: 2026-08-26
- 來源指紋: `57dda425c71bcfc266db17da1848e9afd7a9064de298956c7dcbc9c694ea9fad`
- 唯一真實來源: `tasks.md`
- 專案: Codex Mission Center
- 北極星: 將 Mission Center 升級為研究驅動的自適應 Project OS，並提供可選的本機 Live Agent HUD
- 週期: v0.5 Evidence and Reconciliation Hardening

## 今日摘要 · 2026-08-26
- 完成 Mission Center semantic Hook、HUD asset fingerprint／可攜側欄意圖、Windows launcher 與安裝回歸修正；HUD 預設不啟動 Chrome 或系統瀏覽器。
- 完成 MC-032 Persistent Project Map：獨立 JSON／HTML、canonical fingerprint、atomic lock、跨語言與 adversarial regression；與 RuntimeState 分離。
- 完成 MC-044 Codex CLI Plugin Compatibility Spike：官方安裝／搜尋／更新文件與 Windows／WSL 本機探測矩陣；WindowsApps binary 權限受限，離線 publisher fallback 保留。
- 完成沙盒外 371 項完整測試與 HUD 併發壓測；Project Map manifest、Doctor 與 reconcile release gate 通過。

## 重要護欄 (7)
- GR-001
- GR-002
- GR-003
- GR-004
- GR-005
- GR-006
- GR-007

## 需要時再讀
- 目前工作（0 項）→ `working-set.md`
- 修改任務生命週期／順序 → `tasks.md`
- 查閱理由／證據 → `decisions.md`、`notes.md`、`smoke-tests.md`
- 簡報／工作集過期或截斷 → 執行 `mission_maintenance.py sync` 後再讀 canonical files
