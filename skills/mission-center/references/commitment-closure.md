# Canonical commitment closure

`mission-center commitments --root .` 只讀 `tasks.md` 與 current evidence envelopes。每個非空 `Verification` cell 是一個 opaque requirement；不得用關鍵字把自由文字猜分成新的承諾，也不得建立 `commitments.json` 等第二 truth store。

衍生狀態只有：current pass 為 `satisfied`、current fail 為 `failed`、無 current evidence 為 `missing`、scope／artifact 已改為 `stale`、malformed／duplicate／ambiguous 為 `unknown`。輸出保留原 Verification 與 next distinguishing verification，但不修改 task status、Next action、Pulse 或 Completion Passport。
