# 活動紀錄

- Timestamp: 2026-08-28T22:56:54+08:00
- Change: 新增 MC-061～MC-066 的 Rust-only v0.5.1 Wave 0～5 分波任務；MC-061 設為 In Progress，其餘設為 Backlog。
- Reason: 將下一個版本拆成可依序驗證的契約／供應鏈、Core、Workspace、Policy、Runtime／Publish 與歷史重驗／Stable 切片，並維持 tasks.md 為唯一 lifecycle truth。
- Impact: 目前 next action 為「建立 Rust workspace、版本與依賴／來源鎖定清單，完成 contract／supply-chain review」；尚未新增任何完成 evidence 或 Done 狀態。

- Timestamp: 2026-08-29T07:05:00+08:00
- Change: 新增 Rust `install apply`／`install rollback` 的 verified FrozenPackage 原生交易切片；加入 temp→backup→swap、operation receipt replay、traversal、tamper rollback 與多 destination preflight 測試，並把 CI stable gate 加入 native install smoke。
- Reason: 收斂 Rust-only Wave 4 的 installer／rollback 缺口，同時維持預設 `install` 的相容 read-only 行為與 stable gate fail-closed。
- Impact: native installer slice 已可由明確 opt-in command 執行；HUD persistent lifecycle、正式 Python hook 清除、根 plugin 版本與四平台 clean-checkout 仍是 MC-061 後續阻擋項。

- Timestamp: 2026-08-29T08:35:00+08:00
- Change: 將 `mission-center install --package ...` 接到同一個 Rust native transaction path，保留裸 `install` 的 fail-closed 相容行為，並新增 CLI ABI 測試確認缺少 package 時不會落入舊 unsupported staging route。
- Reason: 讓正式 CLI 形狀與原生 installer 能力一致，同時避免沒有完整 package／destination 時產生任何寫入或假成功。
- Impact: `install apply` 與 `install --package` 共用版本／平台／checksum／transaction receipt 驗證；正式 Python installer、HUD persistent lifecycle 與 stable cutover 仍未完成。

- Timestamp: 2026-08-29T09:05:00+08:00
- Change: Rust HUD launch envelope 新增與既有 launcher 對齊的 `sidePanelIntent`、`presentation.status`、`surface` 與 deterministic `reuseKey`；CLI 測試驗證不宣稱已開啟側欄，且保留 loopback-only／no-external-browser 預設。
- Reason: 讓未來具備 sidebar capability 的宿主能以 exact URL 與 workspace／asset fingerprint 重用既有 HUD，不把瀏覽器開啟誤報成側欄呈現。
- Impact: Rust HUD contract 已具備可觀測的側欄意圖與重用訊號；宿主目前沒有公開 sidebar focus API，跨程序 persistent lifecycle 仍保持明確未支援。

- Timestamp: 2026-08-29T10:00:00+08:00
- Change: 新增 Rust `publish apply`／`publish rollback`，與 native install 共用 FrozenPackage 全平台驗證、atomic swap、receipt replay 與 tamper-safe rollback；CI stable package gate 同時執行 publish 與 install smoke。
- Reason: 補齊正式 CLI 的 publish mutation contract，避免 publish 仍依賴未驗證的舊 staging／Python 路徑。
- Impact: publish／install 都有明確 package、destination、operationId、platform、version 參數與 fail-closed 錯誤；marketplace 註冊與 Python formal wrapper 仍未切換。

- Timestamp: 2026-08-29T10:45:00+08:00
- Change: 重新計算 mc-059／mc-061 evidence scope digest，修復 publish slice 造成的 current envelope stale，並確認 supersession chain 可被 Doctor 正常解析。
- Reason: 新增 Rust publish／HUD／installer source 後，revision-bound evidence 必須跟著 canonical scope 更新，不可留下看似通過但實際過期的摘要。
- Impact: Doctor 回到 OK（僅保留既有 migration warning）；歷史證據仍維持 unknown/pass 誠實分類。

- Timestamp: 2026-08-29T11:25:00+08:00
- Change: 補上 native publish transaction integration test，確認 publish alias 可完成 verified copy、receipt commit 與 rollback，並通過 publish crate 測試與 workspace clippy。
- Reason: 避免 `publish apply` 只有 CLI 參數路由測試，確實驗證它與 install 共用 atomic transaction 行為。
- Impact: publish／install 的核心 transaction parity 有可重複證據；marketplace registration、正式 Python wrapper cutover 與 clean-checkout 四平台 gate 仍待後續。

- Timestamp: 2026-08-29T12:00:00+08:00
- Change: 更新 Rust-only preview 文件，明確列出 `install --package`／`publish apply` 及對應 rollback，並保留 marketplace registration 尚未取代的限制。
- Reason: 讓可執行 preview 介面與實際 CLI 能力一致，避免文件只描述 install 而漏掉 publish mutation。
- Impact: preview 操作契約完整揭露；stable release 仍需正式 registration、Python 路徑移除與 clean-checkout gate。

- Timestamp: 2026-08-29T13:15:00+08:00
- Change: 新增 native transaction reconcile，嚴格驗證 receipt、限制數量與 target phase，並讓 `install/publish reconcile` 只復原 crashed started transaction。
- Reason: install／publish 在程序崩潰後必須能以同一 operation receipt 對帳，避免半套 swap 被靜默忽略或不安全重送。
- Impact: native mutation 具備 bounded crash recovery 與 malformed receipt fail-closed 測試；正式 marketplace registration 與 Python wrapper cutover 仍未宣告完成。

- Timestamp: 2026-08-29T14:00:00+08:00
- Change: stable package CI gate 增加 native `install reconcile` smoke，確認 install／publish committed receipts 可被同一 Rust verifier 對帳且不觸發不安全重送。
- Reason: 將 crash-recovery 契約納入四平台 frozen-package gate，而不是只在 crate 單測驗證。
- Impact: release gate 覆蓋 verify、install、publish、reconcile 四段 native transaction；Python formal runtime 與 marketplace registration blocker 仍維持 fail-closed。

- Timestamp: 2026-08-29T14:35:00+08:00
- Change: 將 native transaction reconcile 暴露為正式 CLI 的 `reconcile --transaction-root` 變體，同時保留 workspace reconcile 的既有語意。
- Reason: 讓唯一 Rust front door 能直接處理 crash recovery，而不必假借 install／publish 子命令或改變 tasks workspace facts。
- Impact: CLI contract、文件與測試同步；兩種 reconcile 來源明確分流，避免誤把交易 receipt 當成 canonical tasks 狀態。

- Timestamp: 2026-08-29T15:10:00+08:00
- Change: transaction directory 改為只接受正式 JSON receipt 與 `.lock`；未知暫存／殘留檔案直接以 `transaction_corrupt` fail-closed。
- Reason: 避免 crash 留下的 partial receipt 被靜默略過，造成 reconcile 對不完整交易現場做錯判。
- Impact: native recovery 的輸入邊界更嚴格，新增 unexpected-artifact 零寫入測試；正式 Python cutover 仍待後續波次。

- Timestamp: 2026-08-29T16:00:00+08:00
- Change: 將非同步 HUD hook 切換為 Rust `hook hud`；以 nonce control file、16 KiB ready receipt、health probe 與六小時 TTL 管理單一 workspace companion，並保留 sidebar intent 為宿主 advisory。
- Reason: 正式 Plugin 執行路徑不再依賴 Python HUD launcher，也避免背景子程序持有 stdout 管線造成 hook 卡住或重複啟動。
- Impact: 同一 workspace 會 reuse 健康實例且不開外部瀏覽器；Codex sidebar 是否實際呈現仍須由宿主能力回報，preview/stable package 其餘 Python 與 registration blocker 仍未解除。

- Timestamp: 2026-08-29T16:25:00+08:00
- Change: 完成 Rust workspace clippy/test、Rust differential 10 tests 與 HUD/CI/release Python targeted tests；更新 MC-061 scope digest。
- Reason: 在切換正式 Hook 前確認 ABI、差異輸出與 bounded HUD lifecycle 沒有回歸。
- Impact: 本機驗證全通過；stable gate 仍會因正式 package 尚含 Python scripts、root plugin 版本與 clean-checkout assembly 未收斂而 fail-closed。

- Timestamp: 2026-08-29T16:45:00+08:00
- Change: stable-package assembler 改以 Rust formal allowlist 組包，排除 source `scripts/`、所有 Python/bytecode 與 `requirements-runtime.txt`，並在 verifier 前再次檢查 package file list。
- Reason: 讓「正式包不含 Python runtime/dependency」成為可機械驗證的 package invariant，而不是只靠文件宣稱。
- Impact: compatibility/oracle 仍留在 source checkout；Rust frozen package 邊界更明確，root plugin version 與四平台 release artifacts 仍是 stable gate 的獨立必要條件。

- Timestamp: 2026-08-29T17:10:00+08:00
- Change: 新增 Rust native marketplace registration；以獨立 registration transaction root 原子提交 `.agents/plugins/marketplace.json`，支援 operationId replay/conflict、rollback 與 crash reconcile，並接上 `install register` CLI。
- Reason: marketplace discovery 不再需要呼叫 Codex CLI 或 Python publisher，且 registration receipt 不會被一般 install transaction scanner 誤解析。
- Impact: native package registration 有 bounded receipt、路徑／digest／symlink fail-closed 驗證與三組 Rust 測試；正式 stable 仍受 root plugin version、四平台 clean-checkout gate 與其餘 Python 相容工具邊界約束。

- Timestamp: 2026-08-29T17:35:00+08:00
- Change: registration receipt 綁定 requested plugin version，並拒絕 interface/category 型別異常；新增 version-conflict regression test。
- Reason: 避免相同 operationId 在 marketplace manifest bytes 不變時錯誤 replay 到另一個 plugin version。
- Impact: registration replay/conflict 邊界與 Python marketplace manifest 欄位順序同步更嚴格；stable gate 狀態不變。

- Timestamp: 2026-08-29T18:00:00+08:00
- Change: root `.codex-plugin/plugin.json` 與雙語 README badge 對齊 `0.5.1-rust.1` preview identity。
- Reason: 修正 preview metadata 與 plugin manifest 長期停在 0.5.0 的版本漂移；stable gate 仍精確要求 0.5.1。
- Impact: preview 版本鏈一致，正式 stable 仍不會因 prerelease 版本誤通過。

- Timestamp: 2026-08-29T18:20:00+08:00
- Change: stable-package assembler 排除 preview-only `.codex-plugin/release-preview.json`，並新增 package invariant 檢查。
- Reason: 避免未來 0.5.1 stable package 同時攜帶 `installable:false` 的 preview 宣告。
- Impact: preview metadata 與 stable artifact 邊界分離；stable gate 仍需四平台實際 artifacts 與正式版本。

- Timestamp: 2026-08-29T18:35:00+08:00
- Change: preview registration 文件改用 `0.5.1-rust.1`，stable CI smoke 維持 `0.5.1`。
- Reason: registration receipt 會嚴格綁定 plugin version，文件不能讓 preview manifest 直接套用 stable version。
- Impact: preview CLI 範例可實際重播；stable 版本切換仍需正式 gate。

- Timestamp: 2026-08-29T19:00:00+08:00
- Change: stable gate 對 root plugin version mismatch 增加明確 fail-closed remediation，避免只留下無上下文的 jq failure。
- Reason: preview `0.5.1-rust.1` 與 stable `0.5.1` 是刻意不同階段，release log 必須可直接指出修復方向。
- Impact: CI blocker 診斷更清楚，沒有放寬版本檢查。

- Timestamp: 2026-08-29T15:20:03+08:00
- Change: 建立 `compat/python-oracle` 邊界 manifest，並讓 stable package invariant 明確排除 compatibility boundary。
- Reason: 保留歷史 Python oracle 的可重播路徑，同時讓正式 Rust plugin 的 runtime／hook／package 邊界可被機械稽核。
- Impact: 新增 release metadata boundary test；Python 僅可用於 differential、historical revalidation 與 migration diagnostics，stable cutover 仍維持 fail-closed。

- Timestamp: 2026-08-29T15:35:00+08:00
- Change: stable package gate 現在驗證 `compat/python-oracle/manifest.json` 的非 runtime 宣告，並在 package file invariant 排除 `compat/`。
- Reason: 將 Python oracle 邊界從文件約定提升為 release-time fail-closed policy。
- Impact: boundary manifest 缺失、型別錯誤或允許 formal runtime 時，Rust stable package 不會組裝或驗證通過。

- Timestamp: 2026-08-29T15:45:00+08:00
- Change: 新增 MC-061 Python oracle boundary evidence envelope，鎖定 CI、manifest、文件與測試 scope digest。
- Reason: 讓 boundary slice 有獨立、可重算且 bounded 的驗證定位，不與整體 stable release 證據混淆。
- Impact: evidence validator 回傳零錯誤；MC-061 仍維持 In Progress，歷史重驗與四平台 gate 未被提前宣稱完成。

- Timestamp: 2026-08-29T16:05:00+08:00
- Change: POSIX selector 依平台驗證 artifact 路徑，Windows 使用 `.exe`，Linux/macOS 維持無副檔名。
- Reason: 修正 selector 與 stable CI assembler 的四平台 manifest path 契約不一致，避免合法包被 POSIX selector 錯誤拒絕。
- Impact: selector shell／policy tests 通過；checksum、版本與完整四平台 fail-closed 驗證仍維持。

- Timestamp: 2026-08-29T16:30:00+08:00
- Change: Rust workspace／CLI 現在可對 canonical `tasks.md` 執行單一步驟 transition，具 operationId replay/conflict、原子寫入與 In Progress → Review → Done gate。
- Reason: 移除原先 transition 永久回傳 unsupported 的 walking-skeleton 缺口，讓 Rust front door 真正承接 lifecycle mutation。
- Impact: 僅改寫目標列的 Status cell，保留 CRLF／escaped Markdown；新增 workspace 與 CLI regression tests，未直接修改本 workspace 任務資料。

- Timestamp: 2026-08-29T16:45:00+08:00
- Change: 將 CLI ABI 代表性測試納入 Rust transition envelope，確認 lifecycle mutation 仍符合版本化 JSON contract。
- Reason: transition 從 unsupported walking skeleton 升級為正式 front-door operation 後，需與既有 machine envelope schema 一起驗證。
- Impact: workspace／CLI／clippy 全部通過；jsonschema 依本機環境缺少套件而保留既有 skip，未冒充通過。

- Timestamp: 2026-08-29T17:00:00+08:00
- Change: Rust-only preview 文件與 Skill 補上 native transition 用法與 Review gate 說明，避免使用者依舊的 Python／unsupported 路徑操作 lifecycle。
- Reason: 新增 transition mutation 後同步更新正式 front-door 的操作契約與安全邊界。
- Impact: 文件、CLI ABI、workspace lifecycle tests 維持一致；stable 仍需 Passport／歷史重驗與四平台 release evidence。

- Timestamp: 2026-08-29T17:20:00+08:00
- Change: Core transition graph 新增 Done → In Progress reopen 邊，並納入 Rust workspace／policy regression。
- Reason: 對齊 reopenable lifecycle 契約；後續 Passport implementation 仍需在 reopen 時標記 superseded。
- Impact: 非法跳關仍拒絕，Review gate 不變；Rust workspace 全測試與 clippy 通過，未宣稱 Passport hard gate 已完成。

- Timestamp: 2026-08-29T16:20:00+08:00
- Change: Rust transition 現已接 Completion Passport／finding gate；HUD hook 遇舊版或損壞 metadata 會視為 cache miss，重新啟動並寫入側邊欄 advisory intent；release claim commit 失敗時會還原 claim bytes。
- Reason: 封閉 Done 驗證入口、避免舊 Python HUD metadata 讓明確召喚永久失效，並保留 claim release 的安全 replay 邊界。
- Impact: Rust workspace／CLI 全 workspace test、clippy、fmt 通過；HUD 實測第一次 launched、第二次 reused 且同 URL，未開外部瀏覽器。Stable cutover 仍受四平台 artifact、歷史重驗與版本 gate 阻擋。

- Timestamp: 2026-08-29T16:35:00+08:00
- Change: Rust snapshot now sanitizes bounded retry metadata and implements diagnosis／verification_required／verification pass reset parity with the Python oracle。
- Reason: 避免 malformed JSON、未處置診斷資料或舊 attempts 被原樣帶入 canonical snapshot，並讓 retry gate 可重播且可驗證。
- Impact: snapshot differential、Rust workspace 全測試、clippy 與 fmt 通過；MC-061 仍維持 In Progress，stable cutover 未提前放行。

- Timestamp: 2026-08-29T16:50:00+08:00
- Change: 重新計算並更新 bounded historical-validation working-tree digest，使目前 512-entry manifest 與測試 oracle 一致（sha256 `3a76b6b3516a...`）。
- Reason: 文件澄清後原歷史驗證摘要已 stale；修正 digest 但保留 historical replay 的 unknown 結果，不把未知證據升格為 pass。
- Impact: release metadata／per-project release tests 36 項通過（2 skip）；四平台 clean-checkout 與歷史重播仍未宣稱完成。

- Timestamp: 2026-08-29T17:05:00+08:00
- Change: source-checkout `install*` wrappers now require explicit `MISSION_CENTER_PYTHON_COMPAT=1`; without opt-in they fail before Python discovery or writes。
- Reason: 將 Python publisher 明確隔離在 compatibility/oracle 邊界，避免正式 Rust package 產生靜默 fallback。
- Impact: Unix／PowerShell fail-closed probes、wrapper policy tests 與 release metadata tests 通過；正式安裝仍以已驗證 Rust frozen package 為唯一路徑。

- Timestamp: 2026-08-29T17:20:00+08:00
- Change: CI release checksum step now selects `sha256sum` or macOS-compatible `shasum -a 256` through one fail-closed helper。
- Reason: 四平台 runner 的雜湊工具名稱不同；避免 macOS artifact 在實際 CI 被非必要命令差異阻斷，同時維持 checksum manifest 驗證。
- Impact: CI policy tests 16 項通過，抽出的 checksum bash block 通過 `bash -n`；四平台實際 artifact 仍待 clean CI runner 產出。

- Timestamp: 2026-08-29T17:35:00+08:00
- Change: 完成 Rust workspace、differential、CI policy、selector、release metadata 與歷史 digest 的收尾驗證。
- Reason: 在 stable gate 前確認本機可重現結果，並把只有 Windows toolchain／缺少四平台 artifact 的狀態保留為 Unknown。
- Impact: Rust workspace 118 tests、Python differential/回歸與 release policy checks 通過；stable `0.5.1` 仍由 CI 四平台 artifact、clean checkout 與歷史重播 gate 阻擋。

- Timestamp: 2026-08-29T17:50:00+08:00
- Change: stable package CI 新增 clean-checkout、四 artifact exact-set 與 artifact directory allowlist gate。
- Reason: 讓實際 frozen-package 組裝只能消費乾淨 checkout 與預期的四平台輸入，避免殘留或注入檔案進入 release。
- Impact: CI policy／selector／release metadata 22 tests 通過；本機仍沒有可供組裝的四平台 release artifacts。

- Timestamp: 2026-08-29T18:00:00+08:00
- Change: historical-validation schema 強制 historical pass/fail 綁定 40 碼 git revision；stable CI 新增完整 history checkout、jq／git cat-file replay-evidence gate。
- Reason: 歷史結果不能由 smoke test 或 working-tree 日期推定；沒有可隔離 revision 就必須阻擋 stable。
- Impact: 當時 MC-001～060 尚全為 Unknown，因此 stable gate 會如實 fail-closed；未產生任何虛構歷史通過證據。

- Timestamp: 2026-08-29T18:30:00+08:00
- Change: 在 detached clean worktree `80ddbb35125d46db410d317cc65d56f5889fdf01` 重播 continuity／resume／handoff 覆蓋測試。
- Reason: 先把有唯一 revision 且驗證範圍完整的歷史任務從 Unknown 提升為可證明結果，其餘含人工或外部 gate 的任務維持 Unknown。
- Impact: 78 tests 通過；MC-053 historicalReplay 現為 pass，其餘歷史結果未被推定。隔離 worktree 已移除。

- Timestamp: 2026-08-29T19:00:00+08:00
- Change: 同一 clean revision `80ddbb35125d46db410d317cc65d56f5889fdf01` 追加 runtime、policy、research、critic、compatibility、project-map 與 evidence 測試重播。
- Reason: 擴大歷史回放覆蓋面，但只有驗證欄位與命令完全吻合、且不依賴外部服務的任務才可更新為 pass。
- Impact: 額外 125 tests 通過；因部分任務仍包含 fuzz、人工審查、外部 endpoint 或發布 gate，未擅自修改其 Unknown 分類。

- Timestamp: 2026-08-29T19:30:00+08:00
- Change: 同一 clean revision `80ddbb35125d46db410d317cc65d56f5889fdf01` 重播 bootstrap、normalize、sync、doctor、skill 與 maintenance 測試，並放寬 stable historical gate 不要求不同任務使用不同 commit。
- Reason: 規格要求每項 task 有獨立 locator，而非全域唯一 commit；同一 clean revision 可由多個獨立測試任務共同引用，避免 gate 超出契約。
- Impact: R13 99 tests 通過（1 skip）；MC-001、002、005、008、026、034、038 提升為 historical pass；其餘外部/人工/不可復原證據仍為 Unknown，stable 仍 fail-closed。

- Timestamp: 2026-08-29T20:00:00+08:00
- Change: 以 pinned Rust 1.98.0、`--release --locked --offline` 建置 Windows x86_64 native CLI，並以 release binary 執行 status smoke 與 frozen-package publish verify fixture。
- Reason: 補足本機可驗證的 native release 證據，不把單一平台產物誤宣稱為四平台 stable package。
- Impact: PE magic `4D5A`、binary SHA-256 `3f30629bb877398bec250b2e995f2106df54c30fbe2d254cd1be1152643b29ec`、status exit 0、publish verify fixture pass；Linux/macOS artifacts 仍交由 CI matrix gate。

- Timestamp: 2026-08-29T20:30:00+08:00
- Change: Rust secret scanner 對齊 Python `SECRET_PATTERN` 的 delimiter、whitespace、Bearer/JWT 長度與 token prefix 規則，新增 workspace regression test；歷史 gate 改為要求每項 task 可定位 revision，不再要求全域不同 commit。
- Reason: 修正過度拒絕與 release gate 超出規格的兩個 parity 問題，同時保留 fail-closed 安全邊界。
- Impact: Rust workspace 21 個 workspace 單元測試、全 workspace 118 tests、fmt/clippy 與 Python differential 126 tests（3 skip）皆通過；HUD hook 以 reuse 重新確認 `127.0.0.1:64206/health` 200。

- Timestamp: 2026-08-29T21:00:00+08:00
- Change: `release_claim` 對 claim restore/abort 的 secondary failure 改回報穩定 `recovery_unknown`；CLI 新增同名 error code 與測試。WriterLock 的跨程序 atomic compare-delete 仍保留為明確 P1 finding，未以假修復宣稱關閉。
- Reason: recovery 不可安全推定時必須讓呼叫端進入對帳路徑，而不是吞掉 cleanup 錯誤。
- Impact: 全 workspace 119 tests、fmt/clippy、Python differential/release/HUD 126 tests（3 skip）通過；stable gate 仍因四平台與歷史 Unknown fail-closed。

- Timestamp: 2026-08-29T21:30:00+08:00
- Change: WriterLock 釋放改為原子 rename 至唯一 recovery tombstone 後再比對 token；替換競爭時保留 tombstone、阻擋後續 writer，並補強 token-swap regression test。
- Reason: 在不引入 unsafe 或未鎖定 crate 的前提下，避免 read→remove TOCTOU 誤刪新 owner lock；不安全狀態改為可對帳、fail-closed。
- Impact: workspace lock tests 21 通過、全 workspace/clippy/format 維持通過；原先 WriterLock P1 finding 已 resolved，tombstone 需由明確 reconcile/人工處理。

- Timestamp: 2026-08-29T22:00:00+08:00
- Change: 修正 retrospective historical validation summary，使其與 60 項 task 明細一致（8 pass／52 unknown），並新增 summary-to-detail 計數不變量測試。
- Reason: 避免明細已提升為可定位歷史 Pass 時，過期 summary 仍造成錯誤 release gate 判斷；不因此改寫任何 Unknown 為 Pass。
- Impact: `tests.test_per_project_release` 與 `tests.test_ci_release_policy` 共 20 tests 通過、3 skip；四平台 artifact、外部 review 與其餘歷史 Unknown 仍保持 fail-closed。

- Timestamp: 2026-08-29T22:15:00+08:00
- Change: GitHub Actions macOS release runners 由已退役／進入淘汰期的 `macos-13`、`macos-14` 更新為原生架構配對 `macos-15-intel`、`macos-15`。
- Reason: 使用者不需持有實體 Mac；四平台實測由 GitHub-hosted runners 提供，但 runner label 必須仍受官方支援。
- Impact: release matrix policy 與 per-project release 共 20 tests 通過、3 skip；尚未推送或觸發遠端 workflow，因此真實 macOS artifacts 仍為 Unknown。
