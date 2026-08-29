# Completion Passport（Rust bounded contract）

`output/mission-center-passports/<taskId>.json` 是 Review→Done 的驗證附件，不是 lifecycle source；`MissionCenter/tasks.md` 仍是唯一狀態真相。

Passport schema 1.0 必須包含 `taskId`、排除 `Status` 欄位計算的 `taskDigest`、`status: current`、`verification.result: pass`、至少一個安全相對 `evidenceRefs`，以及 finding 陣列。Critical 只能 `fixed` 或 `rejected-with-counterevidence`；High deferred 與所有 accepted 必須有完整 `humanAcceptance`。

Rust transition 在任何 receipt 或檔案寫入前 bounded-read 並嚴格驗證 Passport；缺檔、未知欄位、敏感內容、unsafe locator、digest 不一致都 fail-closed。Done→In Progress 若存在 current Passport，會以 atomic write 將其標成 `superseded`；legacy workspace 缺 Passport 由 Doctor 回報 unknown/warning。
