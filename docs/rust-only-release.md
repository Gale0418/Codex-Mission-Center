# Rust-only 0.5.1 stable release

Mission Center 0.5.1 的正式 Plugin front door 是四平台、SHA-256 驗證的
Rust CLI。`.codex-plugin/release.json` 是 stable release contract；
`platform-manifest.json` 必須同時列出 Windows x86_64、Linux x86_64、
macOS x86_64 與 macOS arm64，缺少任一 artifact 都 fail closed。

正式 package 不包含 Python runtime、Python scripts、dependency manifest、
自動下載、本機編譯或 fallback。保留在 source checkout 的 Python 程式只可用於
`compat/python-oracle/manifest.json` 所列 differential tests、歷史重驗與 migration
diagnostics，不是正式 Plugin 執行路徑。

## 安裝、發布與復原

安裝與發布只接受已驗證的 `frozen-package-v1`：

```text
mission-center install apply --package <package> --destination <target> --operation-id <id> --platform <platform> --version 0.5.1
mission-center publish apply --package <package> --destination <target> --operation-id <id> --platform <platform> --version 0.5.1
```

每次 mutation 都綁定 operation ID 與 receipt。相同 ID＋相同內容可安全 replay；
相同 ID＋不同內容拒絕為 conflict。結果未知時必須對帳原 operation ID：

```text
mission-center install reconcile --root <transaction-parent>
mission-center install rollback --receipt <receipt.json>
```

Marketplace registration 同樣是本機、receipt-bound transaction：

```text
mission-center install register apply --plugin-root <marketplace>/plugins/mission-center --marketplace-root <marketplace> --operation-id <id> --version 0.5.1
mission-center install register reconcile --marketplace-root <marketplace>
mission-center install register rollback --receipt <receipt.json>
```

所有路徑都離線執行，不呼叫 Codex CLI、不開瀏覽器，也不自動外送資料。

## Hook 與 HUD

POSIX Hook 呼叫 `bin/mission-center`；Windows Hook 呼叫
`bin/mission-center.ps1`。selector 先驗完整 manifest、Plugin 版本、平台、architecture、
執行權限與 checksum，再 `exec` 對應 binary。任何缺失或不一致都零寫入失敗。

`hook hud` 只啟動或重用 bounded loopback companion，不開外部瀏覽器。
它可回報 sidebar intent，但只有宿主提供 presentation receipt 時才能宣稱已呈現在側欄。

## Stable promotion gate

main 上的 `0.5.1` 會啟動完整 stable gate：歷史 MC-001～MC-060 evidence、四平台
真實 binary、checksum、frozen package、Rust verifier、native registration、install、
publish、reconcile、Python-runtime exclusion、SBOM、license notice 與 rollback contract
必須全部通過。未知歷史人工證據保留為 bounded `unknown`，不得冒充 pass。
