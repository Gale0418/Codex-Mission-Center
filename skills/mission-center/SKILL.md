---
name: mission-center
description: Use when a user needs to clarify a vague or high-impact goal, research options, publish an approved local MissionCenter workspace, or resume its work.
---

# Mission Center｜意圖／風險路由

Mission Center 僅處理目前 repo 的 `./MissionCenter/`；不掃描、註冊、監控或合併其他 repo。所有生成內容依使用者語言；使用繁中時一律 zh-TW。`tasks.md` 是任務順序與生命週期的唯一真實來源。

## 先判斷意圖

- **恢復**：先執行 `python skills/mission-center/scripts/mission_maintenance.py . resume --json`，優先只使用 bounded `packet.content`；其中 `workingSet`、`activeCriticalLessons`、`snapshot` 分別是 `working-set.md`、`critical-lessons.md` Active Lessons 與有效 active `snapshot.md` 的 bounded 內容。若 `fallbackReason` 為 `derived view stale`，先執行 `mission_maintenance.py . sync`，再重新取得 Resume packet；其他情況僅依 `packet.readNext` 或 `fallbackReason` 追加讀取指定檔案，不得自行掃描整個 `MissionCenter/`。任何狀態、順序、優先級、依賴或下一步變更前仍須讀 `tasks.md`；詳見 [記憶維護](references/memory-maintenance.md)。
- **目標未清**：依 [訪談](references/intake-protocol.md) 重述理解、指出最大缺口並提出**至多一個**阻塞問題；安全可逆假設可繼續。未達完整性前不建立工作區或任務。
- **規劃／發布**：依 [任務工作區](references/task-workspace.md)、[Linear 規劃](references/linear-parity.md) 與 [執行閘門](references/execution-gates.md)，先提出選項、取捨與建議；使用者核准完整 Epic 地圖與首個可驗證里程碑的草案前，不得寫入 `tasks.md`。
- **執行／變更**：維持最小可驗證切片、如實記錄阻塞與決策；依 [任務種子](references/task-seeding.md)、[規格化](references/normalization-rules.md) 與 [活動紀錄](references/activity-log-format.md) 更新事實。

## 依風險加深，而非硬塞流程

先查本地證據；新依賴、高成本架構、現行規範或相容性風險才依 [研究](references/research-protocol.md) 做 Prior Art／主要來源／授權與 Clean-room 判斷，確定性本地修改可記為略過研究。

開放式產品、體驗或架構發想才用 [創意智囊](references/intake-council.md)。有實質影響的決策依 [動態專家智囊](references/dynamic-expert-council.md) 按複雜度選擇 skip／lite／full；真實子代理、Shadow 試驗與額外預算均需使用者明確核准，詳見 [協作](references/agent-orchestration.md)。可量測指標、硬限制、預算與停止規則齊備時，才依 [最佳化](references/optimization-protocol.md)、[最佳化路由](references/optimization-routing.md) 與必要的 [實驗設計](references/experiment-design.md) 實驗；否則做決策或研究，不偽造數值最佳解。

## 任務與 Runtime 分離

HUD 的一位 helper 對應一項 task，來源永遠是 `tasks.md`；依 [視覺 HUD](references/visual-hub.md) 同步。Runtime 是可選遙測，依 [Runtime 協定](references/runtime-agent-protocol.md) 顯示於獨立 Live Agents 面板，絕不改任務狀態、排序或唯一真實來源。

## 驗證、Done 與收尾

每項有意義的任務須有低成本、可重複的驗證；依 [煙霧測試模式](references/smoke-test-patterns.md) 與 [目錄](references/smoke-test-catalog.md) 記錄指令/動作、預期、觀察、結果、日期與 task ID。無通過證據不得 Done。收尾前依 [快照格式](references/snapshot-format.md) 產生可重啟 checkpoint，依 [收尾格式](references/closeout-format.md) 保存結果與未完成工作，並遵守 [專案生命週期](references/project-lifecycle.md)。

實作後且本地驗證最新時，僅在高風險、大變更或使用者要求時走 [CodeRabbit 閘門](references/coderabbit-review-gate.md)；需要時再依 [完成對抗評論](references/completion-critic-council.md) 執行受預算限制的評論。發現須查證，修正後重跑受影響驗證；不可把不可用的外部審查說成通過。

## 維護者 Hook

此 source checkout 的 **Maintainer-only** pre-commit 是 check-only：可安裝於維護 repo 檢查契約，但 `git commit` 不執行 sync 或 normalize，也不是 target workspace 的一般命令。若任務資料有變更，可提示維護者在提交前手動執行需要的 sync／normalize；不得背景監控。

## 參考路由

- [活動格式](references/activity-log-format.md)｜[協作](references/agent-orchestration.md)｜[收尾](references/closeout-format.md)｜[CodeRabbit](references/coderabbit-review-gate.md)
- [Execution Pulse／Handoff](references/execution-pulse-handoff.md)
- [Steelman Evolution](references/steelman-evolution.md)
- [Research Portfolio／Saturation](references/research-portfolio.md)
- [Shift-Loss Eval／Self-Metrics](references/shift-loss-eval.md)
- [完成評論](references/completion-critic-council.md)｜[動態專家](references/dynamic-expert-council.md)｜[執行閘門](references/execution-gates.md)｜[實驗設計](references/experiment-design.md)
- [創意智囊](references/intake-council.md)｜[訪談](references/intake-protocol.md)｜[Linear 規劃](references/linear-parity.md)｜[記憶維護](references/memory-maintenance.md)
- [規格化](references/normalization-rules.md)｜[最佳化](references/optimization-protocol.md)｜[最佳化路由](references/optimization-routing.md)｜[平台支援](references/platform-support.md)
- [專案生命週期](references/project-lifecycle.md)｜[研究](references/research-protocol.md)｜[Runtime 協定](references/runtime-agent-protocol.md)｜[煙霧測試目錄](references/smoke-test-catalog.md)
- [煙霧測試模式](references/smoke-test-patterns.md)｜[快照格式](references/snapshot-format.md)｜[任務種子](references/task-seeding.md)｜[任務工作區](references/task-workspace.md)｜[視覺 HUD](references/visual-hub.md)
