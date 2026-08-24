# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

主要使用者是在單一 repository 內操作 Codex Mission Center 的個人開發者或專案操作者。他們需要迅速看出目前最需要介入的事項，並追蹤任務、代理與驗證證據。

## Product Purpose

Codex Mission Center 是離線、per-project、檔案核心的任務作業系統，將模糊目標收斂成可驗證、可交接、可恢復的本地任務工作區。HUD 是這套工作區的唯讀戰情表面；成功代表操作者能依序掌握異常與待處理事項、任務進度、Agent 狀態與證據追溯，而不必猜測資料新鮮度。

## Positioning

產品以 repository 中可檢查、可版本化的 MissionCenter 文件與 `tasks.md` 作為生命週期真相；可選的 loopback runtime 只顯示明確連接 endpoint 的遙測。它不是全域 Codex Desktop 監控器，也不建立第二套任務狀態來源。

## Operating Context

核心流程為 Intake、任務拆分、執行或阻塞、Review、Done，以及 handoff 或 resume。HUD 讀取可重建的 `visual-state.json`，並可選讀取 `mission-center-runtime/runtime-state.json`。Task 與 Runtime 是彼此獨立的資訊層。

## Capabilities and Constraints

- `MissionCenter/tasks.md` 是 canonical lifecycle truth；HUD 不可回寫它。
- Task 狀態映射為 Intake、In Progress、Blocked、Review、Done；最多顯示 15 個 task helpers。
- Task 載入失敗時保留最後有效快照並如實標示 stale；從未成功載入時顯示 unavailable fallback。
- Runtime drawer 預設收合，只顯示 allowlist attention：approval、question、blocked、error、verification。
- Runtime 最多顯示 15 個 agents，超量時揭露 visible、total、hidden；未知、idle、stale、disconnected 不得暗示為完成。
- Runtime 是可選、唯讀、endpoint-only 的遙測；不得保存或展示 prompt、reasoning、完整 command、tool arguments、環境變數、token 或 secrets。
- HUD 必須保留 Close、Escape、焦點恢復、reduced-motion 與 truthful stale/unavailable 行為。
- 直接以 `file://` 開啟可能因 fetch/CORS 無法取得狀態；正式檢查使用 loopback HTTP server。

## Brand Commitments

保留 Codex Mission Center 名稱、親切但不誇大的作戰指揮語彙，以及 repository 內既有任務／helper／mission map 概念。角色 sprite 是裝飾性視覺語彙，不是官方 Codex 人物或品牌資產。

本次 HUD 的使用者指定視覺承諾是「如頂尖消費電子團隊打造的宇宙戰艦艦橋」：整體需呈現精密、克制、連續且具空間感的軟硬體整合；避免直接複製 Apple 商標、產品畫面或受保護 trade dress，也避免廉價霓虹科幻駕駛艙。

## Evidence on Hand

- 產品與決策紀錄：`README.zh-TW.md`、`MissionCenter/project.md`、`MissionCenter/decisions.md`。
- HUD 契約：`skills/mission-center/references/visual-hub.md`。
- 資料與協定：`skills/mission-center/scripts/visual_state.py`、`skills/mission-center/schemas/runtime-state.schema.json`。
- 驗證：`tests/test_visual_state.py`、`tests/test_hud_assets.py`、`tests/test_sync_mission_center.py`、`tests/test_runtime_protocol.py`。
- Checked-in output 與 runtime replay 可能是舊快照，不能用來宣稱現在的即時狀態、模型、token、效能或 uptime。

## Product Principles

1. Attention first：第一眼先回答哪裡需要人介入。
2. Truth before theatre：寧可顯示 unavailable 或 stale，也不製造即時感。
3. Task truth stays singular：Runtime 只補充上下文，不改寫任務生命週期。
4. Progressive disclosure：總覽保持可掃描，細節在明確操作後展開。
5. Evidence remains traceable：狀態與宣稱應可回溯至本地文件、schema、測試或 smoke evidence。

## Accessibility & Inclusion

互動控制支援鍵盤、Escape 關閉與焦點恢復；動態狀態使用適當的 live region；尊重 `prefers-reduced-motion`；不得僅靠顏色表達狀態。完整繁中介面與 task helper 鍵盤逐項探索仍是本次重建應處理的缺口。
