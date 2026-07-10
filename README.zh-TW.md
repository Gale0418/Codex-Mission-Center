# Codex Mission Center 任務中心套件

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
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
├── skills/mission-center/   # 外掛封裝 Skill 檔
└── tests/                   # 自動化測試套件
```

執行後建立的本地工作區結構：

```text
MissionCenter/
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

---

## 🧪 執行自動化測試

要驗證任務種子生成、狀態規格化與 HUD 同步邏輯：

### PowerShell Pester 測試

```powershell
pwsh -Command "Invoke-Pester -Path ./tests"
```

### Python Pytest 測試套件

```bash
pytest tests/
```

---

## 📄 授權條款

本專案採用 [MIT License](LICENSE) 條款開源發布。
