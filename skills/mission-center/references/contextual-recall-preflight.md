# 情境召回與 Preflight

`MissionCenter/context-manifest.json` 是可選、versioned、metadata-only 的索引。它不嵌入來源內容，只能指向 repository-relative 的 `MissionCenter/` 檔案，並以完整來源 SHA-256、精確 anchor、scope、validity 與 requiredVerification 綁定。

支援的 boundary：`resume`、`enter-review`、`before-deploy`、`before-migration`、`after-repeated-failure`。正式 Rust 指令：

```bash
mission-center context validate --root .
mission-center context recall --root . --context before-deploy --scope '{"component":"release"}'
mission-center preflight --root . --context before-deploy --scope '{"component":"release"}'
```

每個來源最多 64 KiB、manifest 最多 64 cards，公開 recall 最多 16 KiB；`resume` 的 contextCards 與原有內容共用同一個 16 KiB packet 預算。路徑 traversal、URI、Windows separator／ADS、symlink/reparse、digest mismatch、失效 anchor、invalid UTF-8、secret-like excerpt 都 fail closed。

Preflight 是唯讀判斷：有效 card 為 `covered/advisory-only`；沒有匹配 card 為 `not-covered/unknown`，不是批准；stale、incompatible、recheck-required 或 corrupt context 為 `unknown/blocked`。它不攔截任意 shell，也不修改 task、dispatch agent 或執行部署。
