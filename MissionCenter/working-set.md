<!-- Generated materialized view. Do not edit directly; rebuild from canonical MissionCenter files. -->
<!-- mission-center-derived schema=1.0 fingerprint-format=sha256-v2-lf source-fingerprint=f77d486304ee0ef3d1facdb447e06f9d2f4ffcb2dcd8cd3e10a263d396ff3c1f -->
# 當前工作集

- 唯一真實來源: `tasks.md`
- 可執行項目數: 6

| ID | 標題 | 優先級 | 狀態 | 下一步 | 依賴 | 驗證方式 | 阻塞原因 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MC-072 | Mission Center 0.5.2 完整記憶、承諾與對帳版本 | P0 | In Progress | 完成 MC-073～MC-078，通過本機與四平台 release gate 後發布 | MC-071 | B/C/D 契約、完整 Rust/Python regression、CodeRabbit、獨立審查、四平台 frozen package |  |
| MC-073 | B：來源綁定情境召回與明確 Preflight | P0 | Review | 等待 0.5.2 四平台 release gate 完成後封存 | MC-071 | Rust 正負向、UTF-8 budget、digest、symlink/traversal、secret、deploy/migration discrimination tests |  |
| MC-074 | C：Canonical Task Commitment Closure | P0 | Review | 等待 0.5.2 四平台 release gate 完成後封存 | MC-073 | satisfied/failed/missing/stale/unknown、determinism、tasks.md byte-identical tests |  |
| MC-075 | D1：外部操作結果對帳 | P0 | Review | 等待 0.5.2 四平台 release gate 完成後封存 | MC-074 | replay/conflict、ambiguous restart、digest、task/scope binding、path/secret/size/Windows tests |  |
| MC-077 | 0.5.2 版本、文件與本機 Release Candidate | P0 | Review | 等待 GitHub frozen package 驗證後封存 | MC-073, MC-074, MC-075, MC-076 | fmt、Clippy、workspace all-target/all-feature tests、Python full suite、candidate probes |  |
| MC-078 | 嚴格審查、四平台 Frozen Package 與 Main 收斂 | P0 | In Progress | 推送凍結 candidate，完成 GitHub 四平台 gate、main 合併、branch 清理與本機安裝 | MC-077 | CodeRabbit 配額內審查、獨立 reviewer、required test、artifact/checksum/package/remote branch verification |  |
