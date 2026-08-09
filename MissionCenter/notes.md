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
| 把 Agent 活動全部攤在主畫面 | https://github.com/vibeislandapp/vibe-island、https://github.com/erha19/ping-island | Adapt：採 attention-first 與漸進揭露；以安靜膠囊取代常駐大面板 | Vibe Island 為 community-only；Ping Island 為 Apache-2.0；本次未複製程式碼或圖像 |
| 直接搬入完整像素辦公室 | https://github.com/pixel-agents-hq/pixel-agents | Learn：採 provider boundary、受限活動分類與 Task/Agent 分層；拒絕重型 Node/React/Canvas 依賴 | MIT；僅採架構概念，未複製實質內容 |
| 保存完整 Agent 軌跡方便回放 | https://github.com/camtrik/agent-trail | Reject：其完整 prompt/tool/reasoning 儲存方向不符合 MissionCenter 的最小遙測與隱私契約 | 僅比較設計方向；未採用 |
| 擴張成多 Agent 控制平面 | https://github.com/lanchuske/lanchu | Learn：共享狀態與 handoff 值得參考，但完整控制平面超出單 repo、零 daemon 邊界 | MIT；僅採 Learn，不導入依賴 |
| 猜測 Codex Desktop 私有事件 | 本機 `codex app-server generate-json-schema` 與 stdio initialize probe | Adopt：以目前 schema 的 `thread/started`、`thread/status/changed`、`thread/closed` 和 status tagged object 為契約；舊通知不再臆測 | 本機官方 CLI 0.147.0-alpha.6.5；升級後需重新驗證 |
| 將 Code Map 與 Agent HUD 當成同一種畫面 | https://x.com/so_ainsight/status/2084869512684519763 | Learn／Adapt：另設可重建的 html/json/lock Project Map，最多約 20 個主元件與 3–5 條關鍵流程，並以 fingerprint 標 stale | 公開貼文設計概念；尚未實作跨語言分析，不複製圖像 |
| 讓每個子 Agent 直接競爭寫同一份 state.json | https://x.com/kotetsu_0321/status/2082383124462469353 | Adapt：採父子世代拓樸與狀態表情，但由集中 reducer 原子寫入；不採自報進度、完整任務、token 或事件實況 | 公開貼文設計概念；以既有 privacy contract 收斂 |
| 用 one-shot Prompt 在完成後無限召喚分身互相批評 | https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents | Adapt：組合不同 grader 職能、保留多輪互動與證據；加入固定快照、能力宣告、預算與停止條件 | 官方工程文章；僅採 eval 方法概念 |
| 多個 AI 評審一致就視為品質保證 | https://openai.com/index/gdpval/ | Learn：自動 grader 不能取代真正專家；採 rubric、盲評式獨立初稿與人工風險接受 | OpenAI 官方研究說明；僅採評估方法 |
| 只靠平均分判斷長流程互動品質 | https://deepmind.google/blog/evaluating-multimodal-interactive-agents/ | Adapt：以時間延伸的情境、可觀察 continuation 與人工標註概念建立 journey coverage；不把主觀感受偽裝成總分 | Google DeepMind 官方研究；僅採方法概念 |

## Evolution 邊界

- `tasks.md` 仍是唯一 Task lifecycle／ordering 真實來源。
- Runtime 僅保存 coarse telemetry，不保存 prompt、reasoning、完整命令、tool arguments 或秘密。
- 核心離線、單一 repo、stdlib-only；WebSocket transport 才使用可選依賴。
- Shadow 結果最多進入 `Review`，不得自動升級或改 Task 狀態。
