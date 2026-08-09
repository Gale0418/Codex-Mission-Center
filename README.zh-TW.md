# Codex Mission Center 任務中心套件

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![Codex Integration](https://img.shields.io/badge/Codex-Plugin%20%2B%20Skill-brightgreen.svg)]()

**Codex Mission Center** 是一套完全離線、以檔案為核心的 Codex 外掛套件與 Skill。它受 Linear 式專案追蹤與 Superpowers 執行紀律啟發，能將模糊的目標逐步收斂並轉化為本地化的任務工作區 (`MissionCenter/`)。

Mission Center 僅服務目前這一個專案。它只建立或讀取目前 repo 的 `./MissionCenter/`，不掃描其他倉庫、不合併跨專案任務，也不提供全局監控。

![skills/mission-center/assets/visual-hub/readme-hero.png](skills/mission-center/assets/visual-hub/readme-hero.png)

---

## 💡 核心功能

- **單一聚焦訪談 (North Star Intake)**：每輪僅提出一個針對性問題，直到目標、邊界與第一里程碑完全清晰。
- **跨領域創意智囊團 (Cross-Domain Council)**：在面對開放式發想或架構設計時，引導跨領域類比與創新解法。
- **先前技術先行檢查 (Prior Art Gate)**：在動手實作前，先搜尋既有方案與開源授權，避免重複造輪子。
- **滾動式任務劃分 (Linear-style Parity)**：以 `Project -> Cycle -> Epic -> Task -> Subtask` 劃分完整目標，僅精細拆解第一里程碑。
- **純檔案工作區與多語系支援**：於專案根目錄建立 `MissionCenter/`（包含 `project.md`、`progress.md`、`tasks.md`、`decisions.md` 等），並完全支援繁體中文 (zh-TW) 輸出。
- **離線動態視覺 HUD (Visual Summary)**：提供網頁視覺化面板 (`output/mission-center-assets/visual-summary.html`)，以小人動態看板反應任務進度與狀態。
- **自適應最佳化 Gate**：依可量測性、參數型態、噪聲、風險與預算，自動選擇決策分析、DOE、Taguchi、Bayesian Optimization、TPE、Pareto 或梯度法；證據不足時回到研究，不假裝有數值最佳解。
- **動態專家會議 Gate**：依決策複雜度選擇跳過、精簡會議或完整會議；只在真正需要時搜尋最新資料與召集多角度觀點，避免讓例行工作變成額度焚化爐。
- **有預算上限的 Shadow 實驗**：只產出人工審查建議，不會自動採用候選方案。
- **可選 Live Agent HUD**：透過本機 companion 顯示已連接 Codex app-server endpoint 的 Agent；與 Task 小人完全分層，Runtime 永遠不修改 Task 狀態。
- **低額度熱區記憶**：以零模型呼叫的每日紀錄、人工護欄與可重建的 `brief.md`／`focus.md`，避免每次都重讀整座任務中心。

---

## 🏗️ 專案與工作區目錄結構

```text
Codex-Mission-Center/
├── .codex-plugin/           # Codex 外掛定義檔
├── SKILL.md                 # 核心技能規範
├── README.md                # 英文說明文件
├── README.zh-TW.md          # 繁體中文說明文件
├── assets/                  # 視覺 HUD 基礎圖資
├── docs/                    # 設計規範與導向文件
├── scripts/                 # 自動化腳本 (bootstrap, sync, normalize, install)
├── skills/
│   └── mission-center/       # 外掛封裝 Skill 檔
│       ├── SKILL.md
│       ├── agents/
│       ├── references/
│       ├── scripts/
│       └── assets/
└── tests/                   # 自動化測試套件
```

執行後建立的本地工作區結構：

```text
MissionCenter/
├── brief.md                 # 可重建的短摘要熱區
├── focus.md                 # 僅列未完成 P0 的可重建視圖
├── guardrails.md            # 人工核准的重要踩坑護欄
├── daily-log.md             # 一天一區塊的日誌
├── project.md               # 專案 North Star 目標與範圍
├── progress.md              # 階段進度條與里程碑
├── tasks.md                 # 核心任務清單 (唯一狀態來源)
├── decisions.md             # 架構決策紀錄 (ADR)
├── smoke-tests.md           # 煙霧測試與驗證清單
├── notes.md                 # 研究筆記與討論紀錄
├── snapshot.md              # 可恢復的工作快照
├── closeout.md              # 週期收尾與回顧
└── visual-hub.md            # 本專案 HUD 入口
```

---

## 🚀 快速開始與安裝

### 選項 1：PowerShell 一鍵安裝 (Windows / macOS / Linux)

```powershell
pwsh -ExecutionPolicy Bypass -File ./scripts/install.ps1
```

### 選項 2：Python 跨平台安裝

```bash
python3 scripts/install.py
```

### 呼叫方式

在 Codex 中直接輸入：

```text
使用 $mission-center 規劃這個專案目標，先進行訪談，然後建立 MissionCenter 工作區。
```

最短的單專案流程：

```bash
python skills/mission-center/scripts/bootstrap_mission_center.py . --language zh-TW
python skills/mission-center/scripts/sync_mission_center.py .
python skills/mission-center/scripts/doctor_mission_center.py .
```

恢復任務時先檢查短摘要，或用純規則記一筆今日事件：

```bash
python skills/mission-center/scripts/mission_maintenance.py . status
python skills/mission-center/scripts/mission_maintenance.py . daily --message "完成 parser 驗證"
python skills/mission-center/scripts/mission_maintenance.py . sync
```

`tasks.md` 仍是唯一 Task lifecycle 真實來源；`brief.md` 與 `focus.md` 只是有內容指紋的可重建快取。`guardrails.md` 的新增、升格、停用一律需要人工明確核准。

最佳化與 Runtime CLI：

```bash
python skills/mission-center/scripts/mission_optimizer.py profile --input project-profile.json
python skills/mission-center/scripts/mission_optimizer.py route --profile project-profile.json
python skills/mission-center/scripts/mission_optimizer.py shadow --manifest experiment.json --observations observations.json --workspace .
python skills/mission-center/scripts/mission_runtime.py --workspace . replay events.jsonl
python skills/mission-center/scripts/mission_runtime.py --workspace . connect --stdio
python skills/mission-center/scripts/mission_runtime.py --workspace . serve --port 8765
```

核心功能仍是零必要第三方依賴；stdio 可直接啟動目前 Codex app-server，只有連接 WebSocket live runtime 時才需執行 `python -m pip install -r requirements-runtime.txt`。HUD 平時只顯示安靜的注意力膠囊，展開後才看 Live Agents；缺少 Runtime 或可選依賴時會自動退回原本的靜態 Task 畫面。所有 Live 監看都只涵蓋明確連接的 endpoint，不宣稱全域監控 Codex Desktop。

Windows 的 Microsoft Store／WindowsApps 封裝版 Codex 可能拒絕被 Python 直接建立子程序；此時請用 `--codex-executable` 指向獨立 CLI。Mission Center 不會偷偷退回 shell wrapper。

被動的 Runtime 監看只整理本機事件與 JSON，**不會呼叫模型，也不會額外消耗模型額度**。已連接 Agent 本身執行任務時仍依原本方式計費；只有明確啟用 LLM 分類或 Agent 驅動的實驗 trial 才消耗模型 token，且必須受 manifest 預算限制。

---

## 🧪 執行自動化測試

要驗證任務種子生成、狀態規格化與 HUD 同步邏輯：

### PowerShell Pester 測試

```powershell
pwsh -Command "Invoke-Pester -Path ./tests"
```

### Python unittest 測試套件

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 📄 授權條款

本專案採用 [MIT License](LICENSE) 條款開源發布。
