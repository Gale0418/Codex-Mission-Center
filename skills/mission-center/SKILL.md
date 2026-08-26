---
name: mission-center
description: Use when a high-impact or multi-step goal needs clarification, research, planning, approval, or MissionCenter recovery. Skip single-step, generic plan/continue, and explanation/quotation only.
---

# Mission Center｜意圖／風險路由

Mission Center 僅處理 `./MissionCenter/`，不掃描、註冊、監控或合併其他 repo；依語言生成（繁中 zh-TW）。`tasks.md` 是任務順序與生命週期的唯一來源。

`<python>`：Unix=python3；Win=`py -3`。

## 先判斷意圖


- **恢復**：執行 `<python> skills/mission-center/scripts/mission_maintenance.py . resume --json`，只用 bounded `packet.content`；`workingSet`、`activeCriticalLessons`、`snapshot` 分別對應 `working-set.md`、`critical-lessons.md` Active Lessons、有效 active `snapshot.md`。若 `fallbackReason` 為 `derived view stale`，先執行 `<python> skills/mission-center/scripts/mission_maintenance.py . sync`，再執行 `<python> skills/mission-center/scripts/mission_maintenance.py . resume --json`；否則僅依 `packet.readNext`／`fallbackReason` 讀指定檔，不掃描 `MissionCenter/`。變更狀態、順序、優先級、依賴或下一步前須讀 `tasks.md`；詳見 [記憶維護](references/memory-maintenance.md)。
- **目標未清**：依 [訪談](references/intake-protocol.md) 重述理解、指出最大缺口並提出**至多一個**阻塞問題；可用安全可逆假設繼續。完整前不建立工作區／任務。
- **規劃／發布**：依 [任務工作區](references/task-workspace.md)、[Linear 規劃](references/linear-parity.md) 與 [執行閘門](references/execution-gates.md) 先提出選項與取捨；使用者核准完整 Epic 地圖與首個可驗證里程碑草案前，不寫入 `tasks.md`。
- **執行／變更**：維持最小可驗證切片，依 [任務種子](references/task-seeding.md)、[規格化](references/normalization-rules.md)、[活動紀錄](references/activity-log-format.md) 記錄事實。

## 依風險加深，而非硬塞流程

先查本地證據；新依賴、高成本架構、現行規範或相容性風險才依 [研究](references/research-protocol.md) 做 Prior Art／主要來源／授權／Clean-room 判斷；確定性本地修改可略過研究。

開放式產品／體驗／架構發想才用 [創意智囊](references/intake-council.md)；重大決策依 [動態專家智囊](references/dynamic-expert-council.md) 按複雜度選 skip／lite／full。真實子代理、Shadow 試驗與額外預算均須使用者明確核准（詳見 [協作](references/agent-orchestration.md)）。有指標、硬限制、預算與停止規則才做 [最佳化](references/optimization-protocol.md)／實驗；否則研究／決策，不偽造數值最佳解。

## 任務與 Runtime 分離

HUD helper 一對一 task，來源永遠是 `tasks.md`，依 [視覺 HUD](references/visual-hub.md) 同步；Runtime 僅可選遙測，依 [Runtime 協定](references/runtime-agent-protocol.md) 顯示在獨立 Live Agents 面板，不改任務狀態、排序或唯一真實來源。

開 HUD：`<python> skills/mission-center/scripts/hud_autolaunch.py show --workspace .`；預設不開瀏覽器；指紋供驗證；失敗不擋。

Project Map：`<python> skills/mission-center/scripts/project_map.py .`（與 RuntimeState 分離）

## 驗證、Done 與收尾

每項任務須有低成本可重複驗證，依 [煙霧測試模式](references/smoke-test-patterns.md) 與 [目錄](references/smoke-test-catalog.md) 記錄指令／動作、預期、觀察、結果、日期、task ID；無通過證據不得 Done。收尾依 [快照格式](references/snapshot-format.md) 產生 checkpoint、依 [收尾格式](references/closeout-format.md) 保存結果／未完成工作，並遵守 [專案生命週期](references/project-lifecycle.md)。

實作後且本地驗證最新，僅高風險、大變更或使用者要求時走 [CodeRabbit 閘門](references/coderabbit-review-gate.md)；需要時依 [完成對抗評論](references/completion-critic-council.md) 做受預算限制的評論。發現須查證，修正後重跑受影響驗證；不可把不可用外部審查說成通過。

## 維護者 Hook

source checkout 的 **Maintainer-only** pre-commit 是 check-only；可安裝於維護 repo 檢查契約，但 `git commit` 不執行 sync 或 normalize，也不是 target workspace 一般命令。任務資料變更可提示維護者提交前手動 sync／normalize；不得背景監控。

## 參考路由

- [活動格式](references/activity-log-format.md)｜[協作](references/agent-orchestration.md)｜[收尾](references/closeout-format.md)｜[CodeRabbit](references/coderabbit-review-gate.md)
- [Pulse/Handoff](references/execution-pulse-handoff.md)｜[Evidence](references/evidence-envelope.md)
- [Steelman Evolution](references/steelman-evolution.md)
- [Research Portfolio／Saturation](references/research-portfolio.md)
- [Shift-Loss Eval／Self-Metrics](references/shift-loss-eval.md)
- [完成評論](references/completion-critic-council.md)｜[動態專家](references/dynamic-expert-council.md)｜[執行閘門](references/execution-gates.md)｜[實驗設計](references/experiment-design.md)
- [創意智囊](references/intake-council.md)｜[訪談](references/intake-protocol.md)｜[Linear 規劃](references/linear-parity.md)｜[記憶維護](references/memory-maintenance.md)
- [規格化](references/normalization-rules.md)｜[最佳化](references/optimization-protocol.md)｜[最佳化路由](references/optimization-routing.md)｜[平台支援](references/platform-support.md)
- [專案生命週期](references/project-lifecycle.md)｜[研究](references/research-protocol.md)｜[Runtime 協定](references/runtime-agent-protocol.md)｜[Runtime 相容性矩陣](references/runtime-compatibility-matrix.md)｜[煙霧測試目錄](references/smoke-test-catalog.md)
- [煙霧測試模式](references/smoke-test-patterns.md)｜[快照格式](references/snapshot-format.md)｜[任務種子](references/task-seeding.md)｜[任務工作區](references/task-workspace.md)｜[視覺 HUD](references/visual-hub.md)
