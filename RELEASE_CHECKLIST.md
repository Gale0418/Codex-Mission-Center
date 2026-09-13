# Release Checklist

- [x] All unit tests pass.
- [x] Bootstrap demo succeeds in English and Traditional Chinese.
- [x] Single-workspace doctor succeeds.
- [x] Publish dry-run succeeds without writing targets.
- [x] Publish verify reports no drift after publishing.
- [x] `README.md`, `README.zh-TW.md`, `SKILL.md`, and references describe the same workspace contract.
- [x] The release adds no global monitoring, repository scanner, registry, or background service.
- [x] The release does not merge tasks across repositories.
- [x] `MissionCenter/tasks.md` remains the only task lifecycle source for its repository.
- [x] `cargo fmt --check`, Clippy `-D warnings`, and workspace tests pass with Rust 1.98.1 using `--locked --offline` where supported.
- [x] All four release artifacts match their SHA-256 manifests and the stable `0.5.2` plugin/release contracts.
- [x] The frozen package contains no Python runtime, fallback, compatibility scripts, or preview metadata.
- [x] Rust native registration, install, publish, reconcile, and receipt-bound rollback pass in an isolated directory.
- [x] `docs/SBOM.spdx.json`, `NOTICE.md`, vendored license files, release notes, and rollback guidance are present.
- [x] Historical replay preserves unavailable manual evidence as bounded `unknown`; it never promotes unknown to pass.
