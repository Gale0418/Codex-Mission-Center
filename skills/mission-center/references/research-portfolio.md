# Research Portfolio／Saturation Gate

Research Portfolio 是 bounded、deterministic 的 advisory artifact，不會上網、執行研究、修改 `tasks.md`、smoke evidence 或 memory，也不會自動採用任何 hypothesis。

每個 portfolio 綁定 canonical `tasks.md` 的 `taskId`，並至少各列一筆三類 hypothesis：`exploit`、`adjacent_explore`、`moonshot`。預設 `60/30/10` 只是 `initial_hypothesis_allocation`，配置總和必須是 100，絕不代表最佳解。每個 hypothesis 都要記錄問題、機制、證據引用、最小辨識測試、預期觀察、否證條件、依賴、風險、token/tool/time budget（可明確為零）、成功／失敗後續、重新驗證條件與狀態。依賴與風險可以是空 list；空 `currentEvidenceRefs` 只允許 `unverified` 或 `research_needed`。

Pre-research 階段 `sourceLedger` 可以是空 list；此時所有 hypothesis 必須使用空 evidence refs 且維持 `unverified`／`research_needed`。sourceType 只有 `local`、`repo`、`workspace`、`fixture` 會被視為 local；`github`、`docs`、`api` 或其他未列出的類型一律視為 external，必須標記 `untrusted_external_evidence`。

Source ledger 必須保留 locator、sourceType、provenance、trustStatus、licenseStatus、retrievedAt、status。外部內容一律標記 `untrusted_external_evidence`，不可以直接 promotion；portfolio 預設 `advisory_only`。

Saturation 只能依顯式本地 signal 路由：

- 少於兩項 signal：`continue`
- 至少兩項 signal：`broaden_search`
- hard constraint failure 或 budget exhausted：`stop`（或由人工選 `human_decision`）

```bash
python skills/mission-center/scripts/research_portfolio.py validate portfolio.json --workspace .
python skills/mission-center/scripts/research_portfolio.py saturate signals.json
```
