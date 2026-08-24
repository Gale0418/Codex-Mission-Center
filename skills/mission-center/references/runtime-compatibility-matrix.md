# Runtime 相容性矩陣

這份矩陣描述 Mission Center Runtime adapter 的保守支援邊界。它不是對 Codex app-server 全部 API 的相容性承諾；上游變更時，應先更新版本證據、fixture 與 focused tests，再調整 adapter。

| Surface | v1 policy | Mission Center 行為 | 驗證／限制 |
| --- | --- | --- | --- |
| 官方文件化的 thread／turn／item／approval notifications | capability opt-in | 只讀取已列入 allowlist 的 method 與 item type；未知或 malformed payload fail closed | 以 normalized event fixture 驗證；不解析 prompt、command 或 tool arguments |
| Stable surface capability | capability opt-in | 只有 provider 明確宣告能力時才可在未來顯示控制；目前 HUD controls 維持 read-only | 不把「文件存在」當成 provider 或版本一定支援 |
| Generated schemas | version-specific | 不直接假設跨版本欄位；只投影 RuntimeState 的固定 allowlist | 每個 app-server 版本需有獨立 fixture／matrix entry；未知欄位忽略 |
| stdio app-server transport | local read-only adapter | 使用明確 argument array、無 shell；WindowsApps 封裝版失敗時要求 standalone CLI | initialize handshake 必須成功；frame、field、agent、replay 均有硬上限 |
| WebSocket companion | **experimental；unsupported for production** | 僅允許明確指定 endpoint；plain `ws://` 僅可 loopback，不能宣稱全域監控 | optional dependency；不得把 WebSocket 可連線誤稱為 production support |
| Thread discovery／attach／resume | unsupported in v1 | 不呼叫 `thread/list`、`thread/loaded/list` 或 `thread/resume`；不掃描 Desktop threads | 未來若加入，必須先完成 permission、pagination、ownership、resume semantics 契約 |
| Runtime → MissionCenter task lifecycle | unsupported by design | Runtime 只寫 `output/mission-center-runtime/`；`MissionCenter/tasks.md` 永遠不由 Runtime 修改 | task link 必須來自明確 metadata 或明確 CLI 選擇 |

## 版本使用規則

現有 protocol reference 以 `app-server 0.147.0-alpha.6.5` 的 `ThreadStatus` 形狀作為已驗證 fixture 背景；這不是 production 相容性宣告。若上游版本、generated schema 或 notification 名稱改變，先建立新 matrix entry 與 replay fixture；在未知狀態下保留舊 state、忽略該訊息，禁止猜測 mapping。

供應鏈方面，`requirements-runtime.txt` 保留使用者安裝所需的 optional compatibility range；CI／release 則使用 `requirements-runtime.lock` 與 pip `--require-hashes` 驗證官方平台無關 wheel。CI action 以官方 v6 ref 解析出的完整 40 字元 commit SHA 固定，旁註 major tag 供升級工具辨識。維護者不得猜測或縮短 SHA。
