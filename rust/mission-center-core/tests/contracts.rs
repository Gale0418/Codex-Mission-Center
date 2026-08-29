use mission_center_core::{TaskStatus, parse_tasks_markdown, sha256_digest};

#[test]
fn markdown_contract_handles_crlf_unicode_and_unknown_escape() {
    let source = "# 任務\r\n\r\n| ID | Title | Status | Notes |\r\n| --- | --- | --- | --- |\r\n| MC-1 | 你好 \\| 世界 | ready | keep \\x |";
    let tasks = parse_tasks_markdown(source).expect("valid table");
    assert_eq!(tasks[0].status, TaskStatus::Ready);
    assert_eq!(tasks[0].title, "你好 | 世界");
    assert_eq!(tasks[0].notes, "keep \\x");
}

#[test]
fn malformed_trailing_escape_is_rejected() {
    let source = "| ID | Title | Status |\n| --- | --- | --- |\n| MC-1 | broken | Done \\\\";
    assert!(parse_tasks_markdown(source).is_err());
}

#[test]
fn sha256_is_stable_for_empty_input() {
    assert_eq!(
        sha256_digest(b""),
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    );
}

#[test]
fn lifecycle_aliases_are_not_accepted_as_canonical_statuses() {
    for alias in [
        "todo",
        "planned",
        "doing",
        "in-progress",
        "in_progress",
        "verification",
        "completed",
    ] {
        assert!(
            TaskStatus::parse(alias).is_err(),
            "alias unexpectedly accepted: {alias}"
        );
    }
}
