# Mission Center Skill 統合設計

## 目標

將 Mission Center 的 repo、個人 Skill、Marketplace 安裝來源與 plugin cache 統一為同一套可靠工作流程。

使用者啟用 Mission Center Skill 後，系統必須能：

1. 先理解並研究目標、限制、風險與完成條件。
2. 將目標拆成可執行、可驗證且有依賴關係的任務。
3. 將任務依序發布到 `MissionCenter/tasks.md`，並同步專案摘要、進度與 HUD 狀態。
4. 讓 HUD 以「一個小人代表一個任務」呈現 `tasks.md` 的生命週期。

## 成功條件

- Repo 是唯一可編輯真源，其餘三個位置均由發布流程產生。
- 四份 `SKILL.md` 的 SHA-256 完全相同。
- Skill 不再依 active agent、Owner、程序數或平行工作數量決定 HUD 小人數量。
- 任務研究、拆解、發布、同步及驗證流程有明確輸入、輸出與失敗行為。
- `tasks.md`、`project.md`、`progress.md`、`smoke-tests.md` 與 HUD 不會各自維護互相衝突的狀態。
- Skill 與 plugin 驗證、內容一致性檢查及任務生命週期 fixture 測試全部通過。

## 非目標

- 不實作 Codex 與 Antigravity 或其他 AI 程式的跨程序橋接。
- 不重設 HUD 視覺風格或進行無關的前端重構。
- 不修改無關 License、歷史文件或使用者尚未提交的變更。
- 不直接把 plugin cache 當成作者來源或長期手動維護目標。

## 單一真源與發布架構

唯一真源：

```text
D:\MyGame\Codex-Mission-Center\skills\mission-center
```

衍生位置：

```text
C:\Users\USER\.codex\skills\mission-center
C:\Users\USER\.codex\local-marketplaces\mission-center\plugins\mission-center\skills\mission-center
C:\Users\USER\.codex\plugins\cache\mission-center-local\mission-center\<version>\skills\mission-center
```

發布方向固定為：

```text
repo 真源
  -> 個人 Skill 相容鏡像
  -> Marketplace plugin 來源
  -> cachebuster 與插件重裝
  -> plugin cache
```

禁止從任一衍生位置反向覆寫 repo。個人 Skill 保留相容性，但不得成為另一套規格來源。Plugin cache 必須透過正式更新流程刷新，不直接手改。

## Skill 工作流程

### 1. 讀取現況

- 若工作區已有 `MissionCenter/`，先讀取 `project.md`、`progress.md`、`tasks.md`、`decisions.md` 與 `smoke-tests.md`。
- 若尚未建立，先完成需求 intake，不得用模糊描述直接生成大量任務。
- 研究本機檔案、既有文件與 Git 歷史；只有在資訊具時效性、需要來源或本機資料不足時才使用網路研究。

### 2. 研究與定義任務

- 明確記錄目標、成功條件、限制、非目標、優先級、第一個里程碑、主要風險與驗證策略。
- 外部研究結果應摘要到 `notes.md` 或 `decisions.md`，保留可追溯來源，不把搜尋結果直接當作未驗證事實。
- 任務必須是可交付的切片；過大或高風險工作先拆成父子任務。

### 3. 發布任務

- `tasks.md` 是任務順序與生命週期的唯一真源。
- 每個任務至少包含穩定 ID、短標題、類型、父項、優先級、狀態、依賴、下一步與驗證方式。
- 新任務按使用者與依賴順序插入，不得以 active agent 或 Owner 排序。
- 發布後同步 `project.md` 與 `progress.md`；若任務影響 HUD，立即重建視覺狀態。
- 任務未有可重複驗證紀錄前不得標為 `Done`。

### 4. 失敗處理

- 缺少關鍵需求時停在 intake，提出一個最能降低不確定性的問題。
- `tasks.md` 格式錯誤時回報可定位的錯誤，不虛構任務或預設小人。
- 同步衍生檔失敗時保留 repo 真源，停止發布並列出失敗位置。
- 不得為了讓 HUD 看起來有內容而生成假任務或主程式佔位角色。

## HUD 生命週期

每一列有效任務對應一個小人，名稱使用任務短標題，順序跟隨 `tasks.md`。

| `tasks.md` 狀態 | HUD 區域 |
|---|---|
| `Backlog`、`Ready` | `Intake` |
| `In Progress` | `In Progress` |
| `Blocked` | `Blocked` |
| `Review` | `Review` |
| `Done` | 休息區 |

顯示規則：

- 主工作區顯示前 10 個未完成任務。
- `Done` 不占前 10 名額。
- 總小人超過 15 時，先淘汰最舊的 `Done`。
- `Blocked` 僅代表真正受阻；smoke test 是完成門檻，不另造衝突狀態。
- HUD 小人數量不得從 active agents、Owner 或程序數推導。

## Skill 文件結構

- `SKILL.md`：保留觸發條件、核心流程、生命週期與必要守則。
- `references/`：保存 HUD、intake、task workspace、驗證與發布細節。
- `scripts/`：保存需要確定性與可重複執行的 bootstrap、seed、sync、validate 與 publish 工具。
- `assets/`：只放實際發布所需的 HUD 資產。

避免在 `SKILL.md` 重複整段範例實作；詳細 schema 與腳本行為放到 reference 或可測試腳本，降低載入成本。

## 更新與防漂移

- 擴充既有 Windows／Unix 安裝工具，從 repo 真源發布完整 Skill 套件。
- 發布前檢查 repo 工作樹，保留目前未提交的 `sync_mission_center.py` 變更。
- Marketplace 來源更新後使用 cachebuster／重新安裝流程刷新 plugin cache。
- 排除 `.git`、`__pycache__`、`*.pyc` 與暫存檔。
- 提供唯讀 dry-run，先列出新增、修改、刪除與雜湊差異。
- 正式發布後再次計算四份 `SKILL.md` 雜湊；不一致視為失敗。

## 驗證策略

### 靜態驗證

- 驗證 `SKILL.md` YAML frontmatter、名稱與 description。
- 驗證 plugin manifest 與 Marketplace metadata。
- 搜尋並拒絕舊的 active-agent roster 規則。
- 檢查 `SKILL.md` 不含互相矛盾的生命週期敘述。

### 行為 fixture

- 空任務表：HUD 為空狀態，不生成預設小人。
- 混合狀態：每個任務恰好一個小人並進入正確區域。
- 重複 Owner：仍依任務數建立小人。
- 超過 10 個未完成任務：只顯示前 10 個。
- 具有 `Done`：不占未完成額度，超過總上限時淘汰最舊完成項。
- 缺少欄位或格式錯誤：回報明確錯誤且不覆寫既有視覺狀態。

### 發布驗證

- 四份 `SKILL.md` SHA-256 相同。
- repo、個人 Skill 與 Marketplace 的必要檔案清單一致。
- plugin cache 的必要檔案內容與發布來源一致，允許 Codex 自身生成的安裝 metadata。
- Python 腳本編譯與相關測試通過。
- Git diff 僅包含本次 Skill 統合、發布與測試內容。

## 風險控制

- Repo 目前落後 `origin/main` 三個提交，且已有使用者未提交修改；實作不得使用 destructive reset、checkout 或粗暴覆蓋。
- GitHub 版的 active-agent 與 SmokeTest 偽狀態不可直接當成最終規格。
- Cache 版雖具有正確的 task-driven 原則，仍含預設小人與部分語意矛盾，必須依本設計修正後才能成為真源內容。
- 發布流程若不能可靠刷新 cache，應停止並保留已驗證的 repo 與 Marketplace，不宣稱四份已同步。
