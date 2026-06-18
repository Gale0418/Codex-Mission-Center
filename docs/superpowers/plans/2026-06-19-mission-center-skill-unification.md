# Mission Center Skill 統合實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 Mission Center repo 建成唯一真源，使 Skill 能完成深度 intake、創意跨域研究、Linear 式任務發布與 task-driven HUD，並以可驗證流程同步至三個本機衍生位置。

**Architecture:** Repo 中的 `skills/mission-center/` 保存唯一工作流程與 deterministic scripts；`tasks.md` 是任務與 HUD 的唯一狀態來源。Repo 根目錄的 Python 發布器只同步個人 Skill 與 Marketplace source，plugin cache 則透過官方 cachebuster／reinstall 流程刷新，禁止反向覆寫真源。

**Tech Stack:** Python 3 standard library、`unittest`、Markdown Agent Skill、PowerShell 7.4、HTML/CSS/JavaScript HUD、Codex plugin marketplace。

---

## 檔案責任圖

- `skills/mission-center/SKILL.md`：精簡觸發條件、核心工作流與必要閘門。
- `skills/mission-center/references/intake-protocol.md`：北極星 intake、完整性條件、一次一題規則。
- `skills/mission-center/references/intake-council.md`：按需啟動的創意跨域發散／收斂 Council。
- `skills/mission-center/references/research-protocol.md`：Prior Art、Jina 降級、Clean-room 與授權政策。
- `skills/mission-center/references/linear-parity.md`：Linear 任務層級、滾動式規劃與 Superpowers 對齊。
- `skills/mission-center/references/execution-gates.md`：草案核准、發布、執行、驗證與收尾閘門。
- `skills/mission-center/references/agent-orchestration.md`：觀點模擬與真正子 Agent 的邊界。
- `skills/mission-center/references/visual-hub.md`：一任務一小人與顯示上限規則。
- `skills/mission-center/scripts/visual_state.py`：純函式任務正規化、篩選與 HUD state 建構。
- `skills/mission-center/scripts/sync_mission_center.py`：讀取 workspace、更新摘要並原子寫入 HUD state。
- `skills/mission-center/scripts/bootstrap_mission_center.py`：建立語系化工作區與研究紀錄模板。
- `skills/mission-center/scripts/seed_task_tree.py`：依已核准目標建立精簡的第一個任務樹。
- `skills/mission-center/assets/visual-hub/*`：只負責呈現已產生的 task-driven state。
- `scripts/publish_local.py`：dry-run、同步、排除生成物與雜湊驗證。
- `scripts/install-*.{ps1,sh}`：薄包裝，轉呼叫 `publish_local.py`。
- `.codex-plugin/plugin.json`、`skills/mission-center/agents/openai.yaml`、`README.md`：發布 metadata 與使用說明。
- `tests/`：pure function、workspace template、Skill contract、HUD asset 與發布器測試。

## 工程護欄

- **易讀：** 每個新增檔案只有一個可用一句話說明的責任；名稱直接描述用途，不建立空殼 `src/`、`components/`、`utils/` 或 `legacy/` 分層。
- **易維護：** 優先延伸既有 scripts／references；只有 HUD pure function、research protocol 與共用發布器確實需要獨立邊界時才新增檔案。
- **易測試：** 每項行為先寫會失敗的測試、實際看見 RED，再做最小實作並實際看見 GREEN；禁止只建立 `tests/` 卻不執行。
- **最小安全變更：** 不重構無關 HUD 樣式、資產、歷史文件或工作區格式；只修正已核准的 task lifecycle、intake、研究與發布行為。
- **保留既有行為：** bootstrap 語系、既有 CLI 參數、progress 計算、smoke-test 紀錄與 local-first 工作區維持相容；只有 active-agent roster、SmokeTest 偽狀態、錯誤發布路徑與授權 metadata 依規格更正。
- **可更新／擴展／升級：** 狀態映射、欄位 alias、排除規則與發布 target 各自集中定義；不把使用者路徑或 cache version 寫死在核心函式。
- **零佔位債務：** 不新增待辦／修補佔位標記、空的相容舊版目錄、未使用 helper 或延後處理分支；無法完成的需求應停止並明確回報。
- **零新依賴：** 使用 Python standard library 與現有 PowerShell／HTML；除非測試證明標準庫不足且主人另行核准，不新增套件。
- **驗證留到最後：** 每個 commit 前跑焦點測試，發布前跑完整測試、Skill validator、plugin validator、雜湊一致性與 Git 範圍檢查。

### Task 1：用測試接住現有 HUD 同步修改

**Files:**
- Create: `tests/test_visual_state.py`
- Create: `skills/mission-center/scripts/visual_state.py`
- Modify: `skills/mission-center/scripts/sync_mission_center.py:1-235`

- [ ] **Step 1：建立 task-driven HUD 的失敗測試**

```python
# tests/test_visual_state.py
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).parents[1] / "skills" / "mission-center" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from visual_state import build_visual_state, normalize_tasks


class VisualStateTests(unittest.TestCase):
    def test_empty_tasks_create_no_placeholder_helper(self):
        state = build_visual_state([], goal="空專案", progress=0)
        self.assertEqual(state["agents"], [])

    def test_one_helper_per_task_ignores_duplicate_owner(self):
        tasks = normalize_tasks([
            {"ID": "T1", "Title": "風道研究", "Status": "In Progress", "Owner": "Codex"},
            {"ID": "T2", "Title": "聲學驗證", "Status": "Review", "Owner": "Codex"},
        ])
        state = build_visual_state(tasks, goal="吹風機", progress=50)
        self.assertEqual([agent["name"] for agent in state["agents"]], ["風道研究", "聲學驗證"])
        self.assertEqual([agent["status"] for agent in state["agents"]], ["In Progress", "Review"])

    def test_first_ten_unfinished_and_newest_done_fill_fifteen_slots(self):
        rows = [
            {"ID": f"T{i}", "Title": f"未完成 {i}", "Status": "Ready"}
            for i in range(12)
        ] + [
            {"ID": f"D{i}", "Title": f"完成 {i}", "Status": "Done"}
            for i in range(7)
        ]
        state = build_visual_state(normalize_tasks(rows), goal="大型任務", progress=20)
        self.assertEqual(len(state["agents"]), 15)
        self.assertEqual([a["id"] for a in state["agents"][:10]], [f"T{i}" for i in range(10)])
        self.assertEqual([a["id"] for a in state["agents"][10:]], [f"D{i}" for i in range(2, 7)])

    def test_traditional_chinese_headers_are_normalized(self):
        tasks = normalize_tasks([{"ID": "T1", "標題": "研究", "狀態": "Blocked", "負責人": "同一人"}])
        self.assertEqual(tasks[0]["Title"], "研究")
        self.assertEqual(tasks[0]["Status"], "Blocked")

    def test_unknown_status_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported task status"):
            normalize_tasks([{"ID": "T1", "Title": "壞資料", "Status": "SmokeTest"}])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2：執行測試並確認因 module 尚未存在而失敗**

Run: `python -m unittest tests.test_visual_state -v`

Expected: `ModuleNotFoundError: No module named 'visual_state'`。

- [ ] **Step 3：建立最小 pure-function 實作**

`visual_state.py` 使用以下完整 pure-function 實作：

```python
from __future__ import annotations

import hashlib

STATUS_TO_ZONE = {
    "backlog": "Intake",
    "ready": "Intake",
    "in progress": "In Progress",
    "blocked": "Blocked",
    "review": "Review",
    "done": "Done",
}

HEADER_ALIASES = {
    "類型": "Type",
    "父層": "Parent",
    "優先級": "Priority",
    "標題": "Title",
    "狀態": "Status",
    "負責人": "Owner",
    "依賴": "Depends on",
    "下一步": "Next action",
    "驗證方式": "Verification",
    "估時": "Estimate",
    "標籤": "Labels",
    "備註": "Comments",
}

REQUIRED_FIELDS = ("ID", "Title", "Status")


def normalize_tasks(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    for row_number, row in enumerate(rows, start=1):
        task = {
            HEADER_ALIASES.get(str(key).strip(), str(key).strip()): str(value).strip()
            for key, value in row.items()
        }
        missing = [field for field in REQUIRED_FIELDS if not task.get(field)]
        if missing:
            raise ValueError(f"Task row {row_number} is missing: {', '.join(missing)}")
        status_key = task["Status"].lower()
        if status_key not in STATUS_TO_ZONE:
            raise ValueError(f"Unsupported task status: {task['Status']}")
        tasks.append(task)
    return tasks


def select_visible_tasks(tasks: list[dict[str, str]], limit: int = 15) -> list[dict[str, str]]:
    unfinished = [task for task in tasks if task["Status"].lower() != "done"][:10]
    done = [task for task in tasks if task["Status"].lower() == "done"]
    done_slots = max(0, limit - len(unfinished))
    visible_done = done[-done_slots:] if done_slots else []
    return unfinished + visible_done


def _stable_avatar(task_id: str) -> int:
    digest = hashlib.sha256(task_id.encode("utf-8")).digest()
    return (int.from_bytes(digest[:2], "big") % 16) + 1


def _project_status(tasks: list[dict[str, str]]) -> str:
    statuses = [STATUS_TO_ZONE[task["Status"].lower()] for task in tasks]
    if not statuses:
        return "Intake"
    if all(status == "Done" for status in statuses):
        return "Done"
    for candidate in ("Blocked", "In Progress", "Review", "Intake"):
        if candidate in statuses:
            return candidate
    return "Intake"


def build_visual_state(
    tasks: list[dict[str, str]], goal: str, progress: int
) -> dict[str, object]:
    visible = select_visible_tasks(tasks)
    active = [task["Title"] for task in tasks if task["Status"].lower() != "done"][:5]
    blocked = [task["Title"] for task in tasks if task["Status"].lower() == "blocked"][:5]
    agents = []
    for task in visible:
        status = STATUS_TO_ZONE[task["Status"].lower()]
        agents.append({
            "id": task["ID"],
            "name": task["Title"],
            "task": f"{task['ID']} {task['Title']}",
            "status": status,
            "zone": status,
            "avatar": _stable_avatar(task["ID"]),
            "active": True,
        })
    return {
        "status": _project_status(tasks),
        "goal": goal,
        "progress": max(0, min(100, int(progress))),
        "active": active,
        "blocked": blocked,
        "agents": agents,
    }
```

實作規則：保留 `tasks.md` 順序、取前 10 個未完成任務、再用最新的 `Done` 補到總數 15；空表回傳空 `agents`；每個 agent 使用 task ID、短標題、mapped status、相同 zone 與穩定 avatar。

- [ ] **Step 4：將現有 `sync_mission_center.py` 接到 pure function**

刪除 Owner 去重、預設 `MissionHelper` 與 emoji log。`main()` 必須明確執行 `raw_tasks = parse_table(root / "tasks.md")` 與 `tasks = normalize_tasks(raw_tasks)`；所有驗證成功後再以暫存檔加 `Path.replace()` 原子寫入 `visual-state.json`，解析失敗不得覆寫既有 state。

- [ ] **Step 5：執行測試與語法檢查**

Run: `python -m unittest tests.test_visual_state -v`

Expected: 5 tests PASS。

Run: `python -m py_compile skills/mission-center/scripts/visual_state.py skills/mission-center/scripts/sync_mission_center.py`

Expected: exit code 0。

- [ ] **Step 6：提交 task-driven state builder**

```bash
git add tests/test_visual_state.py skills/mission-center/scripts/visual_state.py skills/mission-center/scripts/sync_mission_center.py
git commit -m "fix: derive Mission Center HUD helpers from tasks"
```

### Task 2：在乾淨工作樹合併 GitHub 遠端基線

**Files:**
- Merge: `origin/main`
- Resolve if needed: `skills/mission-center/scripts/sync_mission_center.py`
- Resolve if needed: `skills/mission-center/scripts/seed_task_tree.py`

- [ ] **Step 1：確認相關未提交修改已由 Task 1 正式收斂**

Run: `git status --short`

Expected: 沒有 `sync_mission_center.py` 未提交修改。

- [ ] **Step 2：合併遠端三個提交，不使用 reset、checkout 或 autostash**

Run: `git merge origin/main`

Expected: 合併 Apache-2.0 License 提交；若 `sync_mission_center.py` 衝突，只保留 Task 1 的 canonical statuses，不接受 `SmokeTest` 偽狀態。

- [ ] **Step 3：檢查合併結果**

Run: `git status --short`

Expected: 無未解決衝突。

Run: `python -m unittest tests.test_visual_state -v`

Expected: 5 tests PASS。

### Task 3：讓 bundled HUD 只呈現任務 state

**Files:**
- Create: `tests/test_hud_assets.py`
- Modify: `skills/mission-center/assets/visual-hub/visual-summary.html`
- Modify: `skills/mission-center/assets/visual-hub/visual-state.json`
- Modify: `skills/mission-center/assets/visual-hub/update-visual-state.ps1`
- Modify: `skills/mission-center/references/visual-hub.md`

- [ ] **Step 1：建立 HUD asset contract 測試**

```python
# tests/test_hud_assets.py
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1] / "skills" / "mission-center"


class HudAssetTests(unittest.TestCase):
    def test_html_has_no_placeholder_roster_or_smoketest_status(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertNotIn('name: "MissionHelper"', html)
        self.assertNotIn('"SmokeTest"', html)
        self.assertIn("const maxVisibleAgents = 15", html)

    def test_default_state_is_empty(self):
        state = json.loads((ROOT / "assets" / "visual-hub" / "visual-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["agents"], [])

    def test_manual_updater_delegates_to_task_sync(self):
        script = (ROOT / "assets" / "visual-hub" / "update-visual-state.ps1").read_text(encoding="utf-8")
        self.assertNotIn("[string[]]$Agents", script)
        self.assertIn("sync_mission_center.py", script)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2：執行測試並確認舊 fallback／SmokeTest／手動 roster 造成失敗**

Run: `python -m unittest tests.test_hud_assets -v`

Expected: 3 tests FAIL。

- [ ] **Step 3：修改 HUD render contract**

將 `renderAgents()` 改為接受空陣列、清空 layer 後直接返回；不建立 fallback helper。狀態集合只保留 `Intake`、`In Progress`、`Blocked`、`Review`、`Done`，上限改為 15，`Done` 小人留在休息區。

- [ ] **Step 4：修改預設 state 與 PowerShell updater**

`visual-state.json` 使用 `"agents": []`。`update-visual-state.ps1` 僅接受 `-Workspace` 與 `-SkillRoot`，驗證 `<SkillRoot>/scripts/sync_mission_center.py` 存在後呼叫 Python sync；不得接受任意 Agents roster。

- [ ] **Step 5：更新 `visual-hub.md`**

寫明一列有效任務恰好一個小人、前 10 個未完成、總數 15、`Done` 不占未完成名額、資料錯誤不生成佔位角色。

- [ ] **Step 6：驗證並提交**

Run: `python -m unittest tests.test_hud_assets tests.test_visual_state -v`

Expected: 8 tests PASS。

```bash
git add tests/test_hud_assets.py skills/mission-center/assets/visual-hub skills/mission-center/references/visual-hub.md
git commit -m "fix: render one Mission Center helper per task"
```

### Task 4：重寫 Skill 核心與研究 Council

**Files:**
- Create: `tests/test_skill_contract.py`
- Modify: `skills/mission-center/SKILL.md`
- Modify: `skills/mission-center/references/intake-protocol.md`
- Modify: `skills/mission-center/references/intake-council.md`
- Create: `skills/mission-center/references/research-protocol.md`
- Modify: `skills/mission-center/references/agent-orchestration.md`

- [ ] **Step 1：建立 Skill contract 失敗測試**

測試必須驗證：frontmatter description 以 `Use when` 開頭且只描述觸發情境；`SKILL.md` 少於 500 行；包含北極星 intake、Prior Art、任務草案核准與 task-driven HUD；不存在 `active agent count`、`one helper per active agent`；所有 `references/*.md` 連結均存在。

Run: `python -m unittest tests.test_skill_contract -v`

Expected: 舊 Skill 因 active-agent 規則與缺少 research protocol 而 FAIL。

- [ ] **Step 2：將 `SKILL.md` 收斂成核心路由**

frontmatter 使用：

```yaml
---
name: mission-center
description: Use when a user needs to clarify a vague or high-impact goal, research existing solutions, publish an approved direction as a local task workspace, or resume tracked MissionCenter work.
---
```

正文只保留：讀取既有 workspace、一次一題直到完整、按需創意 Council、Prior Art Gate、任務草案核准、Linear task model、Superpowers execution gates、task-driven HUD、同步與驗證；細節連到 references。

- [ ] **Step 3：重寫 intake 與創意 Council reference**

`intake-protocol.md` 明確列出 goal、value、success、scope、non-goals、constraints、priority、milestone、risk、dependencies、verification 的完成條件。

`intake-council.md` 明確列出觸發條件、核心機制抽取、跨域類比／反轉／組合／尺度轉換、先發散後收斂，以及每個入選點子的四項輸出：來源領域、遷移原理、組合價值、最小驗證。

- [ ] **Step 4：新增 research protocol**

內容必須包含本機優先、官方／一手來源優先、一般搜尋失敗後 Jina Reader、Jina Search 需憑證、不得繞過存取控制、`搜尋前構想｜參考來源｜採納內容｜授權狀態`、adopt/adapt/learn/build 比較、Clean-room 與 SPDX 授權閘門。

- [ ] **Step 5：修正真正子 Agent 邊界**

`agent-orchestration.md` 寫明 Council 預設是主 Agent 的觀點模擬；只有獨立工作、需要獨立驗證且使用者明確要求／核准時才派遣，完成一批後先收回並檢查 diff。

- [ ] **Step 6：驗證並提交**

Run: `python -m unittest tests.test_skill_contract -v`

Expected: PASS。

```bash
git add tests/test_skill_contract.py skills/mission-center/SKILL.md skills/mission-center/references
git commit -m "feat: add research-driven Mission Center intake"
```

### Task 5：融合 Linear、Superpowers 與滾動式任務發布

**Files:**
- Create: `tests/test_workspace_templates.py`
- Modify: `skills/mission-center/references/linear-parity.md`
- Modify: `skills/mission-center/references/execution-gates.md`
- Modify: `skills/mission-center/references/task-workspace.md`
- Modify: `skills/mission-center/scripts/bootstrap_mission_center.py`
- Modify: `skills/mission-center/scripts/seed_task_tree.py`

- [ ] **Step 1：建立 workspace template 測試**

測試在 temporary directories 分別執行 `bootstrap_mission_center.main()` 與 `seed_task_tree.main()`，驗證英文／繁中 `notes.md` 均含四欄研究表；`visual-hub.md` 含 one task／一個任務而非 active helper；`tasks.md` 只有 canonical statuses，沒有 `SmokeTest` 欄或狀態；第一個 Epic 後只詳細展開第一個 milestone。

Run: `python -m unittest tests.test_workspace_templates -v`

Expected: 舊模板因缺少研究表、active helper 文案與過度 seed 而 FAIL。

- [ ] **Step 2：更新 Linear 與 execution references**

`linear-parity.md` 固定 `Project -> Cycle -> Epic -> Task -> Subtask`，完整 Epic map＋第一里程碑詳細拆分＋遠期 Backlog；`execution-gates.md` 固定 `Brainstorm -> Spec -> Plan -> TDD -> Verify -> Closeout`，未獲任務草案核准不得寫 `tasks.md`。

- [ ] **Step 3：更新 bootstrap templates**

英文與繁中 `notes.md` 都加入精簡研究表；`visual-hub.md` 改成 task lifecycle 文案。保持現有檔案不加 `--force` 時不覆寫。

- [ ] **Step 4：縮減 seed tree**

建立一個 goal Epic、一個 Ready 的研究／範圍 Task、一個 Backlog 的第一里程碑 Task、一個 Backlog 的驗證／收尾 Task；保留依賴、下一步與 Verification，不加入 `SmokeTest`／`Review` YES/NO 欄。

- [ ] **Step 5：驗證並提交**

Run: `python -m unittest tests.test_workspace_templates tests.test_visual_state -v`

Expected: 全部 PASS。

```bash
git add tests/test_workspace_templates.py skills/mission-center/references skills/mission-center/scripts/bootstrap_mission_center.py skills/mission-center/scripts/seed_task_tree.py
git commit -m "feat: publish rolling Linear-style task plans"
```

### Task 6：建立可 dry-run 的本機發布器

**Files:**
- Create: `tests/test_publish_local.py`
- Create: `scripts/publish_local.py`

- [ ] **Step 1：建立發布器失敗測試**

測試必須涵蓋：dry-run 不寫檔；實際同步後 personal Skill 與 Marketplace skill 的 file map／SHA-256 等於真源；排除 `.git`、`__pycache__`、`*.pyc`；拒絕不是 `skills/mission-center` 或 `plugins/mission-center` 結尾的危險 target；`--verify` 發現漂移時回傳非零。

Run: `python -m unittest tests.test_publish_local -v`

Expected: 因 `scripts.publish_local` 尚未存在而 FAIL。

- [ ] **Step 2：實作發布器固定 CLI**

```text
python scripts/publish_local.py \
  --repo <repo-root> \
  --personal-skill <target-skill> \
  --marketplace-plugin <target-plugin> \
  [--cache-skill <installed-cache-skill>] \
  (--dry-run | --write | --verify)
```

使用 `Path.resolve()` 驗證 target 尾端、以 SHA-256 file map 比較、以 sibling staging directory 寫入、切換失敗時保留舊 target；Marketplace 同步 `.codex-plugin`、`assets`、`skills`、`scripts`、README、LICENSE、NOTICE，個人位置只同步 `skills/mission-center`。不得修改 marketplace.json、config.toml 或 plugin cache。

- [ ] **Step 3：執行測試與 help 檢查**

Run: `python -m unittest tests.test_publish_local -v`

Expected: PASS。

Run: `python scripts/publish_local.py --help`

Expected: 顯示 `--dry-run`、`--write`、`--verify` 與三種 target 參數。

- [ ] **Step 4：提交發布器**

```bash
git add tests/test_publish_local.py scripts/publish_local.py
git commit -m "feat: add deterministic local Skill publisher"
```

### Task 7：修正 metadata、安裝 wrappers 與文件

**Files:**
- Modify: `.codex-plugin/plugin.json`
- Modify: `skills/mission-center/agents/openai.yaml`
- Modify: `README.md`
- Modify: `scripts/install-windows.ps1`
- Modify: `scripts/install-plugin-windows.ps1`
- Modify: `scripts/install-unix.sh`
- Modify: `scripts/install-plugin-unix.sh`
- Modify: `tests/test_skill_contract.py`

- [ ] **Step 1：擴充 contract 測試**

驗證 manifest license 為 `Apache-2.0`、repository／homepage 沒有尾端連字號、README 不宣稱 GPL、`openai.yaml` prompt 包含 clarify／research／approved task publish、四個 wrapper 均呼叫 `publish_local.py` 而不自行刪除 target 或手寫 marketplace.json。

Run: `python -m unittest tests.test_skill_contract -v`

Expected: metadata 與舊 wrappers 造成 FAIL。

- [ ] **Step 2：修正 metadata 與 README**

manifest 與 README 對齊遠端 Apache-2.0；更新 description、longDescription、defaultPrompt 與 README 功能摘要，明確寫出 research-driven intake、Prior Art、approved task publish 與 one-task-one-helper。

- [ ] **Step 3：讓 wrappers 只委派發布器**

Windows wrappers 以 PowerShell 7 相容語法呼叫 `python scripts/publish_local.py`；Unix wrappers 以 `python3` 呼叫相同 CLI。預設 personal target 為 `$CODEX_HOME/skills/mission-center`，Marketplace target 為已設定的 `~/.codex/local-marketplaces/mission-center/plugins/mission-center`，並保留參數覆寫能力。

- [ ] **Step 4：執行完整 repo 驗證**

Run: `python -m unittest discover -s tests -v`

Expected: 全部 PASS。

Run: `python C:\Users\USER\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/mission-center`

Expected: `Skill is valid!` 或等價成功訊息。

Run: `python C:\Users\USER\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py .`

Expected: plugin validation PASS。

- [ ] **Step 5：提交 metadata 與 wrappers**

```bash
git add .codex-plugin/plugin.json README.md scripts skills/mission-center/agents/openai.yaml tests/test_skill_contract.py
git commit -m "chore: align Mission Center plugin publishing metadata"
```

### Task 8：發布、刷新 cache 並證明四份一致

**Files:**
- External write: `C:\Users\USER\.codex\skills\mission-center`
- External write: `C:\Users\USER\.codex\local-marketplaces\mission-center\plugins\mission-center`
- External write by Codex installer: `C:\Users\USER\.codex\plugins\cache\mission-center-local\mission-center\<cachebuster>`

- [ ] **Step 1：在外部寫入前執行 dry-run**

```powershell
python scripts/publish_local.py --repo . `
  --personal-skill "$HOME\.codex\skills\mission-center" `
  --marketplace-plugin "$HOME\.codex\local-marketplaces\mission-center\plugins\mission-center" `
  --dry-run
```

Expected: 只列出新增／修改／刪除，不寫入；清單不含 `.git`、`__pycache__`、`*.pyc`。

- [ ] **Step 2：取得使用者核准後發布兩個可控衍生位置**

將相同命令的 `--dry-run` 改成 `--write`。

Expected: personal Skill 與 Marketplace source 更新成功，repo 保持唯一真源。

- [ ] **Step 3：使用官方 cachebuster helper 更新 Marketplace plugin manifest**

```powershell
python C:\Users\USER\.codex\skills\.system\plugin-creator\scripts\update_plugin_cachebuster.py `
  "$HOME\.codex\local-marketplaces\mission-center\plugins\mission-center"
```

Expected: version 為 `0.1.0+codex.local-<UTC timestamp>`，不堆疊舊 suffix。

- [ ] **Step 4：從已設定的 `mission-center-local` Marketplace 重裝**

```powershell
& $env:CODEX_CLI_PATH plugin add mission-center@mission-center-local
```

Expected: plugin install/reinstall 成功；若 `$env:CODEX_CLI_PATH` 不存在，從 Codex app config 的 `CODEX_CLI_PATH` 取實際 CLI 路徑，不使用被 WindowsApps 阻擋的 alias。

- [ ] **Step 5：找出最新 cache 並驗證四份**

```powershell
$cacheSkill = Get-ChildItem "$HOME\.codex\plugins\cache\mission-center-local\mission-center" -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 |
  ForEach-Object { Join-Path $_.FullName "skills\mission-center" }

python scripts/publish_local.py --repo . `
  --personal-skill "$HOME\.codex\skills\mission-center" `
  --marketplace-plugin "$HOME\.codex\local-marketplaces\mission-center\plugins\mission-center" `
  --cache-skill $cacheSkill `
  --verify
```

Expected: 四份 `SKILL.md` SHA-256 相同，三個 Skill folder 的必要 file map 相同，exit code 0。

- [ ] **Step 6：最終回歸與 Git 範圍檢查**

Run: `python -m unittest discover -s tests -v`

Expected: 全部 PASS。

Run: `git status --short`

Expected: repo 無未提交實作變更。

Run: `git log --oneline --decorate -8`

Expected: 可看到 task-driven HUD、research intake、rolling tasks、publisher 與 metadata 的獨立 commits。

- [ ] **Step 7：記錄新執行緒驗證邊界**

重新安裝後目前執行緒仍可能保留舊 Skill metadata；請使用新執行緒明確呼叫 Mission Center，驗證它會先一次問一題、按需啟動創意 Council、研究 Prior Art、提出任務草案，且未核准前不寫 `tasks.md`。
