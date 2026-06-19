# CodeRabbit 最終審查閘門實作計畫

> **給代理工作者：** 必須使用 `superpowers:executing-plans` 逐項執行本計畫。所有步驟使用 checkbox 追蹤；本任務採 inline execution，不使用子 Agent。

**目標：** 在 Mission Center 加入省額度、需同意、風險式觸發的 CodeRabbit 最終獨立審查閘門。

**架構：** `SKILL.md` 只保留觸發時機與路由，詳細規則放在新的 `references/coderabbit-review-gate.md`。既有契約測試鎖定最後登場、範圍排除、外傳同意、一次完整審查加一次聚焦複查、finding 驗證與額度失敗誠實揭露；不新增執行依賴或自動寫 cache 的程式。

**技術棧：** Markdown Skill、Python `unittest` 契約測試、CodeRabbit CLI agent mode、既有 Python 本機發行器、Codex Plugin Creator。

---

## 檔案邊界

- 修改 `skills/mission-center/SKILL.md`：只新增最終審查步驟與 reference 路由。
- 建立 `skills/mission-center/references/coderabbit-review-gate.md`：承擔完整風險、同意、範圍、額度與 failure policy。
- 修改 `tests/test_skill_contract.py`：驗證核心 Skill 與 runbook 契約。
- 不修改 CodeRabbit CLI、不新增依賴、不直接操作 Codex plugin cache。

### Task 1：以失敗測試鎖定 CodeRabbit 最終閘門

**檔案：**
- 修改：`tests/test_skill_contract.py`
- 測試：`tests/test_skill_contract.py`

- [ ] **Step 1：新增會失敗的契約測試**

在 `SkillContractTests` 新增：

```python
def test_coderabbit_gate_is_final_risk_based_and_quota_aware(self):
    skill = SKILL_PATH.read_text(encoding="utf-8")
    gate_path = SKILL_ROOT / "references" / "coderabbit-review-gate.md"
    self.assertIn("references/coderabbit-review-gate.md", skill)
    self.assertTrue(gate_path.is_file())

    gate = gate_path.read_text(encoding="utf-8")
    normalized = gate.casefold()
    for phrase in (
        "after implementation and local verification",
        "explicit consent",
        "risk-based",
        "--dir",
        "--base-commit",
        "-t uncommitted",
        "binary",
        "generated",
        "one full scoped review",
        "one focused re-review",
        "regression test",
        "rate limit",
        "do not claim coderabbit passed",
        "codex-managed plugin cache",
        "completed",
        "skipped",
        "unavailable",
    ):
        self.assertIn(phrase, normalized)
```

- [ ] **Step 2：執行測試並確認 RED**

執行：

```powershell
python -m unittest tests.test_skill_contract.SkillContractTests.test_coderabbit_gate_is_final_risk_based_and_quota_aware -v
```

預期：FAIL，因 `references/coderabbit-review-gate.md` 尚不存在，且 `SKILL.md` 尚未路由至它。

### Task 2：建立省額度的最終審查 runbook

**檔案：**
- 建立：`skills/mission-center/references/coderabbit-review-gate.md`
- 修改：`skills/mission-center/SKILL.md`
- 測試：`tests/test_skill_contract.py`

- [ ] **Step 1：建立詳細 runbook**

建立 `coderabbit-review-gate.md`，內容必須明確包含：

```markdown
# CodeRabbit Final Review Gate

Run this optional risk-based gate only after implementation and local verification.

## Trigger

Run when the user requests it or the change is large or high risk: cross-module behavior, security or privacy boundaries, release and publishing logic, migration, destructive operations, or broad user-facing workflows. Otherwise record `skipped (reason)`.

## Consent And Scope

Confirm explicit consent before uploading the relevant code. Reuse consent already given for the same task. Inspect the diff and use supported scope controls such as `--dir`, `--base-commit`, or `-t uncommitted`. Exclude secrets, binary assets, generated files, caches, lockfiles, vendored code, unrelated files, and large documents that do not need semantic review.

Never invent unsupported flags. Never let CodeRabbit write Codex-managed plugin cache.

## Budget

Use at most one full scoped review and one focused re-review of the fix diff.

## Findings

Treat every issue as external advice. Verify it against current code and architecture. Reject incorrect, duplicate, unsafe, or out-of-scope advice with a technical reason. Add a failing regression test before fixing a valid behavior issue, then make the smallest safe change and rerun local verification.

## Failure

Do not claim CodeRabbit passed after auth failure, timeout, service failure, or rate limit. Record `completed`, `skipped (reason)`, or `unavailable (exact error)`. Ordinary CodeRabbit unavailability does not erase successful local verification. If independent review is explicitly required for security-critical, destructive, or release-blocking work, ask whether to wait, connect an organization, or proceed without that evidence.
```

- [ ] **Step 2：在核心 Skill 新增最後階段路由**

在 `Sync the HUD` 後新增：

```markdown
### 9. Optional Final CodeRabbit Review

After implementation and local verification, use [coderabbit-review-gate.md](references/coderabbit-review-gate.md) when the user requests independent review or the change is large or high risk. CodeRabbit is advisory: obtain upload consent, scope out irrelevant large files, verify every issue, and never report a failed or rate-limited review as passed.
```

並在 `References` 加入：

```markdown
- [coderabbit-review-gate.md](references/coderabbit-review-gate.md): risk-based final independent review.
```

- [ ] **Step 3：執行契約測試並確認 GREEN**

執行：

```powershell
python -m unittest tests.test_skill_contract.SkillContractTests.test_coderabbit_gate_is_final_risk_based_and_quota_aware -v
```

預期：PASS。

- [ ] **Step 4：執行完整測試與 Skill 驗證**

執行：

```powershell
wsl -d Ubuntu -- bash -lc 'cd /mnt/d/MyGame/Codex-Mission-Center && python3 -m unittest discover -s tests -p "test_*.py" -v'
python "C:\Users\USER\.codex\skills\.system\skill-creator\scripts\quick_validate.py" "D:\MyGame\Codex-Mission-Center\skills\mission-center"
git diff --check
```

預期：全部測試 PASS、`Skill is valid!`、`git diff --check` 無輸出。

### Task 3：執行一次聚焦 CodeRabbit 複查並提交

**檔案：**
- 審查：`skills/mission-center/SKILL.md`
- 審查：`skills/mission-center/references/coderabbit-review-gate.md`
- 審查：`tests/test_skill_contract.py`

- [ ] **Step 1：先確認 diff 沒有大檔或無關檔案**

執行：

```powershell
git status --short
git diff --numstat
```

預期：只有上述三個小型文字檔。

- [ ] **Step 2：嘗試一次聚焦 CodeRabbit review**

執行：

```powershell
wsl -d Ubuntu -- bash -lc 'cd /mnt/d/MyGame/Codex-Mission-Center && BASE_COMMIT=$(git rev-parse HEAD) && /root/.local/bin/coderabbit review --agent --base-commit "$BASE_COMMIT" --dir skills/mission-center'
```

預期：若完成，逐項驗證 issues；若遇到 rate limit 或服務錯誤，記錄完整錯誤且不重跑、不宣稱通過。本次為低風險 Skill 文件變更，完整本地驗證仍可作為提交依據。

- [ ] **Step 3：提交 Skill 變更**

```powershell
git add skills/mission-center/SKILL.md skills/mission-center/references/coderabbit-review-gate.md tests/test_skill_contract.py
git commit -m "feat: add risk-gated CodeRabbit closeout review"
```

### Task 4：同步四份 Skill、刷新 cache 並推送 GitHub

**檔案：**
- 發行來源：`skills/mission-center/`
- 個人 Skill：`C:\Users\USER\.codex\skills\mission-center`
- Marketplace plugin：`C:\Users\USER\.codex\local-marketplaces\mission-center\plugins\mission-center`
- Codex cache：依 cachebuster 版本動態決定

- [ ] **Step 1：從 repo 單向發行個人 Skill 與 marketplace plugin**

```powershell
python scripts/publish_local.py `
  --repo "D:\MyGame\Codex-Mission-Center" `
  --personal-skill "C:\Users\USER\.codex\skills\mission-center" `
  --marketplace-plugin "C:\Users\USER\.codex\local-marketplaces\mission-center\plugins\mission-center" `
  --write
```

預期：`[personal] no changes` 與 `[marketplace] no changes`，表示替換後立即驗證一致。

- [ ] **Step 2：用官方流程更新 cachebuster 並重裝**

```powershell
python "C:\Users\USER\.codex\skills\.system\plugin-creator\scripts\update_plugin_cachebuster.py" "C:\Users\USER\.codex\local-marketplaces\mission-center\plugins\mission-center"
& "C:\Users\USER\AppData\Local\OpenAI\Codex\bin\5d35d2790d1d3d7b\codex.exe" plugin add "mission-center@mission-center-local"
```

預期：CLI 顯示新的 installed plugin root。

- [ ] **Step 3：逐檔驗證四份 Skill**

```powershell
$manifest = Get-Content "C:\Users\USER\.codex\local-marketplaces\mission-center\plugins\mission-center\.codex-plugin\plugin.json" -Raw | ConvertFrom-Json
$cacheSkill = "C:\Users\USER\.codex\plugins\cache\mission-center-local\mission-center\$($manifest.version)\skills\mission-center"
python scripts/publish_local.py `
  --repo "D:\MyGame\Codex-Mission-Center" `
  --personal-skill "C:\Users\USER\.codex\skills\mission-center" `
  --marketplace-plugin "C:\Users\USER\.codex\local-marketplaces\mission-center\plugins\mission-center" `
  --cache-skill $cacheSkill `
  --verify
```

預期：personal、marketplace、cache 均為 `no changes`。

- [ ] **Step 4：確認乾淨後推送 main**

```powershell
git status --short
git push origin main
```

預期：status 無輸出，push 為 fast-forward；若遠端先進，先 fetch 與一般 merge，禁止 force-push。
