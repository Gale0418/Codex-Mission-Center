# External-operation result reconciliation

Mission Center 不宣稱外部副作用 exactly-once。`external-operation prepare` 先建立與 canonical task、scope digest、provider receipt digest 綁定的 `pending` record；完成或中斷後再用相同 operation ID 執行 `reconcile`。

狀態機：`pending → confirmed|failed|unknown`；`unknown` 只有在提供目前存在且 digest 相符的新 evidence 後才能轉 `confirmed|failed`；`confirmed` 與 `failed` terminal。同 ID／同 payload 是 replay，同 ID／不同 payload 是 conflict。模糊中斷一律 `unknown`，不得自動重送 provider operation。

記錄位於 `MissionCenter/.mission-center/external-operations/`，採 bounded strict JSON、hashed filename、writer lock、operation history、原子寫入與 canonical task read guard。`get`／`list` 是唯讀；所有路徑、digest、secret 與 symlink/reparse 檢查皆 fail closed。
