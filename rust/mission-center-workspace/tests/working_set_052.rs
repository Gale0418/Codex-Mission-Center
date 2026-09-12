//! Candidate 0.5.2 selection regressions. Run with the pinned Rust toolchain.
//! Canonical data is borrowed; selecting context must not reorder or mutate it.
use mission_center_core::{Task, TaskStatus};
use mission_center_workspace::working_set_ids;
use std::collections::HashSet;

fn task(id: &str, status: TaskStatus, priority: &str) -> Task {
    Task {
        id: id.to_owned(),
        title: format!("Fixture {id}"),
        kind: "task".to_owned(),
        parent: String::new(),
        priority: priority.to_owned(),
        status,
        assignee: "worker".to_owned(),
        dependencies: Vec::new(),
        next_action: "Run local check".to_owned(),
        verification: "local test".to_owned(),
        estimate: "S".to_owned(),
        tags: Vec::new(),
        notes: String::new(),
    }
}

#[test]
fn six_unrelated_blockers_cannot_hide_active_work() {
    let mut tasks: Vec<Task> = (1..=6)
        .map(|index| task(&format!("MC-{index:03}"), TaskStatus::Blocked, "P1"))
        .collect();
    tasks.push(task("MC-007", TaskStatus::InProgress, "P1"));
    let before: Vec<String> = tasks.iter().map(|task| task.id.clone()).collect();
    let ids = working_set_ids(&tasks);
    assert_eq!(ids.first().map(String::as_str), Some("MC-007"));
    assert_eq!(ids.len(), 6);
    assert_eq!(
        before,
        tasks.iter().map(|task| task.id.clone()).collect::<Vec<_>>()
    );
}

#[test]
fn anchor_and_urgent_work_survive_lower_priority_blockers() {
    let mut tasks: Vec<Task> = (1..=6)
        .map(|index| task(&format!("MC-{index:03}"), TaskStatus::Blocked, "P2"))
        .collect();
    tasks.push(task("MC-007", TaskStatus::InProgress, "P1"));
    tasks.push(task("MC-008", TaskStatus::Ready, "p0"));
    let ids = working_set_ids(&tasks);
    assert_eq!(&ids[..2], &["MC-007", "MC-008"]);
    assert_eq!(ids.len(), 6);
}

#[test]
fn direct_dependencies_precede_unrelated_blockers() {
    let mut tasks: Vec<Task> = (1..=6)
        .map(|index| task(&format!("MC-{index:03}"), TaskStatus::Blocked, "P1"))
        .collect();
    let mut active = task("MC-007", TaskStatus::InProgress, "P1");
    active.dependencies = vec![" MC-006 ".to_owned()];
    tasks.push(active);
    let ids = working_set_ids(&tasks);
    assert_eq!(&ids[..2], &["MC-007", "MC-006"]);
    assert_eq!(ids.len(), 6);
}

#[test]
fn done_and_backlog_are_not_promoted_by_priority_or_dependency() {
    let mut active = task("MC-003", TaskStatus::InProgress, "P1");
    active.dependencies = vec!["MC-001".to_owned(), "MC-002".to_owned()];
    let tasks = vec![
        task("MC-001", TaskStatus::Done, "P0"),
        task("MC-002", TaskStatus::Backlog, "P0"),
        active,
    ];
    assert_eq!(working_set_ids(&tasks), vec!["MC-003"]);
}

#[test]
fn overlapping_anchor_priority_and_dependency_do_not_duplicate() {
    let mut active = task("MC-001", TaskStatus::InProgress, "P0");
    active.dependencies = vec!["MC-002".to_owned()];
    let tasks = vec![active, task("MC-002", TaskStatus::Blocked, "P0")];
    assert_eq!(working_set_ids(&tasks), vec!["MC-001", "MC-002"]);
}

#[test]
fn ready_ties_are_stable_and_empty_input_is_empty() {
    let tasks = vec![
        task("MC-003", TaskStatus::Ready, "P2"),
        task("MC-002", TaskStatus::Ready, "P1"),
        task("MC-001", TaskStatus::Ready, "P1"),
    ];
    assert_eq!(working_set_ids(&tasks), vec!["MC-001", "MC-002", "MC-003"]);
    assert!(working_set_ids(&[]).is_empty());
}

#[test]
fn large_urgent_set_stays_bounded_and_keeps_anchor() {
    let mut tasks: Vec<Task> = (1..=30)
        .map(|index| task(&format!("MC-{index:03}"), TaskStatus::Ready, "P0"))
        .collect();
    tasks.push(task("MC-031", TaskStatus::InProgress, "P1"));
    let ids = working_set_ids(&tasks);
    assert_eq!(ids.len(), 6);
    assert_eq!(ids.first().map(String::as_str), Some("MC-031"));
    assert_eq!(ids.iter().collect::<HashSet<_>>().len(), 6);
    assert_eq!(ids, working_set_ids(&tasks));
}
