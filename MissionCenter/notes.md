# 筆記

## 研究紀錄

| 搜尋前構想 | 參考來源 | 採納內容 | 授權狀態 |
| --- | --- | --- | --- |
| 重新實作全部腳本 | 本 repo 現有 scripts/tests | 保留既有 bootstrap、normalize、sync、visual_state、publish 核心 | 專案內部 |
| doctor 複製 sync 輸出 | 本 repo workspace contract | 共用進度計算與 HUD 驗證，doctor 保持唯讀 | 專案內部 |
| 匯入完整多角色 Prompt 庫 | https://github.com/msitarzewski/agency-agents | Learn／Adapt：只採角色契約、專家路由、handoff 與 evidence gate；不複製人格全文、不新增角色庫依賴 | MIT；本次無實質內容複製，未觸發 attribution 變更 |
| 讓專家會議只靠職稱與演戲製造專業感 | https://github.com/msitarzewski/agency-agents/blob/main/engineering/engineering-multi-agent-systems-architect.md | Adapt：每個動態視角定義輸入、單一責任、非目標、產物、成功條件與低信心行為；主持人輸出含異議與未知項的 handoff | MIT；僅採契約模式，未複製角色 Prompt |
| 自訂不穩定 Runtime 協定 | https://developers.openai.com/codex/app-server | Adapt：以官方 JSON-RPC、initialize、thread、turn、item、approval、collabToolCall、error、token usage 為 adapter 邊界 | 官方文件；WebSocket 為可選實驗性 transport |
| 將所有問題套用田口法 | https://www.itl.nist.gov/div898/handbook/pri/section3/pri332.htm | Learn：先判斷可量測性與實驗設計；高噪聲才選 robust DOE／Taguchi，無重複 metric 回 research spike | 美國政府公開技術文件；僅採方法概念 |
| 每次恢復都重讀整座 MissionCenter | https://developers.openai.com/codex/skills | Learn：用 progressive disclosure 先載入聚焦的短上下文，需要時再讀 canonical files | OpenAI 官方文件；僅採方法概念 |
| 把每天事件與長期記憶混在一起 | https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/memory-context-and-rag-optimization.html | Learn：短期與長期記憶分層、設定 context budget 並依相關性取回 | AWS 官方文件；僅採方法概念 |
| 讓短摘要成為第二份手寫真實來源 | https://learn.microsoft.com/en-us/azure/architecture/patterns/materialized-view | Adapt：衍生視圖可丟棄、可重建、帶 freshness 檢查且禁止直接維護 | Microsoft 官方文件；僅採架構模式 |

## Evolution 邊界

- `tasks.md` 仍是唯一 Task lifecycle／ordering 真實來源。
- Runtime 僅保存 coarse telemetry，不保存 prompt、reasoning、完整命令、tool arguments 或秘密。
- 核心離線、單一 repo、stdlib-only；WebSocket transport 才使用可選依賴。
- Shadow 結果最多進入 `Review`，不得自動升級或改 Task 狀態。
