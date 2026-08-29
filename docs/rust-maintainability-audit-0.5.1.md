# Rust 0.5.1 maintainability audit

Date: 2026-08-29

這份稽核只描述可重複觀察，不以語言偏好或虛構 benchmark 宣稱優劣。

## Observed facts

| Crate entrypoint | Lines | `clone()` calls | `serde_json::Value` references | Functions |
|---|---:|---:|---:|---:|
| `mission-center-workspace/src/lib.rs` | 5,005 | 42 | 18 | 156 |
| `mission-center-cli/src/main.rs` | 4,362 | 17 | 80 | 114 |
| `mission-center-publish/src/lib.rs` | 3,520 | 13 | 35 | 139 |
| `mission-center-policy/src/lib.rs` | 3,487 | 11 | 149 | 66 |
| `mission-center-runtime/src/lib.rs` | 2,988 | 35 | 42 | 126 |
| `mission-center-core/src/lib.rs` | 610 | 1 | 4 | 24 |

- Task Markdown parsing、`TaskStatus` 與 task digest 已集中在 `core`；這是 lifecycle
  domain 的唯一修改入口。
- Runtime 已重用 core privacy scanner；policy 仍有較寬的 policy-content scanner，兩者
  名稱相同但語意不同，容易造成維護者誤判。
- CLI、runtime 與 publish 各自實作 strict duplicate-key JSON visitor；其輸入上限與
  error mapping 不同，目前不能直接刪成同一份，但共同 visitor 機制可抽到 core。
- `serde_json::Value` 主要集中在 CLI envelope 與 policy schema boundary；domain task
  model 已 typed。policy 內部仍有 stringly-typed status/classification 欄位。
- `clone()` 次數不是目前主要風險；多數位於 receipt、bounded reducer 或輸出 ownership
  邊界。沒有 profile 證據前不以次數本身做效能結論。
- Publish 的 formal-runtime scanner 先以 PE／ELF／Mach-O header 區分原生 binary 與
  script；只有非原生 binary 內容才進入 script policy 或 Python invocation parser。
  Regression fixtures 刻意在合法 PE bytes 內放入 Python vocabulary，並在 Mach-O bytes
  內放入 `#!`／`cargo` vocabulary，避免 binary 被 lossy-text 誤判。
- Formal script policy 以能力邊界拒絕下載、編譯、套件管理與動態 command wrapper，
  不維護一份會和 selector 漂移的「所有允許 shell commands」巨大白名單；正式 POSIX
  與 PowerShell selector bytes 直接進入同一組 regression fixture。

## Natural module boundaries

下一個 minor release 應依行為邊界漸進拆分，每次只移動一個已有測試的區域：

1. `workspace`: `pulse_handoff`, `claims`, `snapshot`, `project_map`, `transactions`。
2. `policy`: `research`, `optimization`, `steelman`, `critic`, `shift_loss`, `compatibility`。
3. `publish`: `frozen_package`, `platform`, `native_transaction`, `registration`。
4. `cli`: `envelope`, `args`, `hook_hud`, `native_commands`；`main.rs` 只留 dispatch。
5. `runtime`: `protocol`, `privacy`, `reducer`, `transport`, `hud_lifecycle`。

不在 0.5.1 stable 前進行純搬檔重構：它會大幅增加 diff、破壞 blame 與跨平台 release
風險，卻不改變已驗證行為。

## Agent maintenance probe

Probe：新增或修改 task status alias。

- 唯一 production 修改點：`mission-center-core/src/lib.rs` 的 `TaskStatus::parse`。
- 直接 unit contract：`mission-center-core/tests/contracts.rs`。
- 跨介面保護：workspace 與 CLI differential tests。

結論：核心 lifecycle 小功能具備低 context 的唯一入口；HUD、publish transaction 或
policy schema 小功能仍需先依上方自然邊界定位，這是 0.5.2 的主要維護性工作。

第二個 release-path probe：GitHub 產出的 macOS binary 被 formal-runtime scanner 誤判。

- 由 CLI 穩定 `python_runtime` error code 追到唯一 production policy：
  `mission-center-publish/src/lib.rs::scan_frozen_python`。
- 根因不是 Python，而是原生 Mach-O 已辨識成功後，另一個 `has_shebang` 分支仍把 binary
  送進 shell validator；修正後 native binary 在單一 gate 排除所有文字掃描。
- 同一份 GitHub frozen package 在修正前可重現 fail、修正後通過，並新增上述 Mach-O
  regression fixture。

這個 probe 顯示 production 修改點仍可在 bounded context 內定位，但也暴露
`PythonRuntime` 同時承載 Python dependency 與 prohibited shell capability；0.5.2 應將
後者改成獨立 typed error code，避免穩定 envelope 隱藏真正 domain failure。

第三個 cross-platform probe：相同 revision 在 Windows CI 偶發 `WSAECONNRESET`。

- GitHub job log 將 failure 定位到 `hud_lifecycle` 的單一 HTTP request helper，production
  response boundary 則唯一落在 `mission-center-runtime::serve_hud_http_once`。
- Server 改為 `write_all` 後 `flush` 並明確關閉 write half，避免 Windows 把立即 drop
  socket 呈現為 reset；回歸測試每輪連續讀取 16 個完整 response。
- 本機固定 Rust 1.98.0 將該測試重複 10 輪（160 responses）後全數通過，再交回三平台
  CI 驗證；不以單次 rerun 掩蓋 flaky transport boundary。
