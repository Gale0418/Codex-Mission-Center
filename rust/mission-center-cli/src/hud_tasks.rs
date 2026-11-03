use mission_center_core::{Task, TaskStatus, sha256_digest};
use mission_center_runtime::{HudServer, MAX_FIELD_BYTES, MAX_LIST_ITEMS};
use mission_center_workspace::MissionWorkspace;
use serde_json::{Value, json};
use std::{
    collections::HashSet,
    path::PathBuf,
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

const HUD_TITLE_MAX_BYTES: usize = 256;
const HUD_TASK_MAX_BYTES: usize = 400;
const HUD_TRUNCATION_MARKER: &str = "…";

fn clip_utf8(value: &str, max_bytes: usize) -> String {
    if value.len() <= max_bytes {
        return value.to_owned();
    }
    let marker_bytes = HUD_TRUNCATION_MARKER.len();
    debug_assert!(max_bytes > marker_bytes);
    let mut end = max_bytes.saturating_sub(marker_bytes);
    while end > 0 && !value.is_char_boundary(end) {
        end -= 1;
    }
    let mut clipped = value[..end].to_owned();
    clipped.push_str(HUD_TRUNCATION_MARKER);
    clipped
}

fn task_id_is_publishable(task: &Task) -> bool {
    task.id.len() <= MAX_FIELD_BYTES
}

fn now_millis() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

fn snapshot(tasks: &[Task], source: &str) -> Value {
    let done = tasks
        .iter()
        .filter(|task| task.status == TaskStatus::Done)
        .count();
    let parents: HashSet<&str> = tasks.iter().map(|task| task.parent.as_str()).collect();
    let leaves: Vec<_> = tasks
        .iter()
        .filter(|task| !parents.contains(task.id.as_str()))
        .collect();
    let leaf_done = leaves
        .iter()
        .filter(|task| task.status == TaskStatus::Done)
        .count();
    let mut selected: HashSet<&str> = tasks
        .iter()
        .filter(|task| task.status != TaskStatus::Done)
        .take(10)
        .map(|task| task.id.as_str())
        .collect();
    selected.extend(
        tasks
            .iter()
            .rev()
            .filter(|task| task.status == TaskStatus::Done)
            .take(5)
            .map(|task| task.id.as_str()),
    );
    let omitted_long_id = tasks
        .iter()
        .filter(|task| selected.contains(task.id.as_str()))
        .filter(|task| !task_id_is_publishable(task))
        .count();
    let helpers: Vec<_> = tasks
        .iter()
        .filter(|task| selected.contains(task.id.as_str()) && task_id_is_publishable(task))
        .map(|task| {
            let status = task.status.as_str();
            let zone = if matches!(task.status, TaskStatus::Backlog | TaskStatus::Ready) {
                "Intake"
            } else {
                status
            };
            let title = clip_utf8(&task.title, HUD_TITLE_MAX_BYTES);
            let task_label = clip_utf8(&format!("{} {}", task.id, title), HUD_TASK_MAX_BYTES);
            let mut dependencies = Vec::new();
            let mut omitted_dependencies = 0usize;
            for dependency in &task.dependencies {
                if dependencies.len() >= MAX_LIST_ITEMS || dependency.len() > MAX_FIELD_BYTES {
                    omitted_dependencies += 1;
                } else {
                    dependencies.push(dependency.clone());
                }
            }
            json!({"id":task.id,"name":title,"task":task_label,
            "status":status,"zone":zone,"active":task.status != TaskStatus::Done,
            "dependencies":dependencies,
            "dependencyCounts":{"visible":dependencies.len(),"total":task.dependencies.len(),"omitted":omitted_dependencies}})
        })
        .collect();
    let blocked: Vec<_> = tasks
        .iter()
        .filter(|task| task.status == TaskStatus::Blocked)
        .collect();
    let status = if !blocked.is_empty() {
        "Blocked"
    } else if !tasks.is_empty() && done == tasks.len() {
        "Done"
    } else if tasks
        .iter()
        .any(|task| task.status == TaskStatus::InProgress)
    {
        "In Progress"
    } else if tasks.iter().any(|task| task.status == TaskStatus::Review) {
        "Review"
    } else {
        "Intake"
    };
    json!({
        "status":status,
        "goal":format!("任務列完成 {done}/{}（含父項）；末端任務完成 {leaf_done}/{}",tasks.len(),leaves.len()),
        "progress":if tasks.is_empty() { 0 } else { (done * 100 + tasks.len() / 2) / tasks.len() },
        "active":tasks.iter().filter(|task| task.status == TaskStatus::InProgress).take(15).map(|task| clip_utf8(&task.title, HUD_TITLE_MAX_BYTES)).collect::<Vec<_>>(),
        "blocked":blocked.iter().filter(|task| task_id_is_publishable(task)).take(15).map(|task| clip_utf8(&format!("{} {}",task.id,task.title), HUD_TASK_MAX_BYTES)).collect::<Vec<_>>(),
        "blockedCount":blocked.len(),
        "taskCounts":{"visible":helpers.len(),"total":tasks.len(),"hidden":tasks.len()-helpers.len(),"omittedLongId":omitted_long_id},
        "leafCounts":{"done":leaf_done,"total":leaves.len()},
        "agents":helpers,"freshness":"VALID","observedAtMs":now_millis(),
        "source":{"path":"MissionCenter/tasks.md","sha256":sha256_digest(source.as_bytes())}
    })
}

fn unavailable() -> Value {
    json!({"status":"Unknown","goal":"Canonical task source unavailable","progress":0,
        "active":[],"blocked":[],"agents":[],"taskCounts":{"visible":0,"total":0,"hidden":0,"omittedLongId":0},
        "freshness":"UNAVAILABLE","observedAtMs":0})
}

fn refresh(workspace: &MissionWorkspace, last_valid: &Option<Value>) -> Value {
    let regular_source =
        std::fs::symlink_metadata(workspace.tasks_path()).is_ok_and(|metadata| metadata.is_file());
    match regular_source.then(|| workspace.read_tasks()) {
        Some(Ok((source, tasks))) => snapshot(&tasks, &source),
        _ => {
            let mut state = last_valid.clone().unwrap_or_else(unavailable);
            state["freshness"] = json!(if last_valid.is_some() {
                "STALE"
            } else {
                "UNAVAILABLE"
            });
            state
        }
    }
}

pub fn start(root: PathBuf, server: HudServer) {
    let _ = server.set_task_state(&serde_json::to_vec(&unavailable()).unwrap_or_default());
    let _ = thread::Builder::new()
        .name("mission-center-task-source".to_owned())
        .spawn(move || {
            let workspace = MissionWorkspace::new(root);
            let mut last_valid: Option<Value> = None;
            while server.is_running() {
                let state = refresh(&workspace, &last_valid);
                if let Ok(bytes) = serde_json::to_vec(&state)
                    && server.set_task_state(&bytes).is_ok()
                    && state["freshness"] == "VALID"
                {
                    last_valid = Some(state);
                }
                for _ in 0..30 {
                    if !server.is_running() {
                        return;
                    }
                    thread::sleep(Duration::from_millis(500));
                }
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;
    use mission_center_core::parse_tasks;
    use mission_center_runtime::{HUD_MANAGED_ASSETS, HudLauncher, HudServerConfig};

    #[test]
    fn task_snapshot_counts_parents_separately_and_preserves_canonical_selection() {
        let source = "| ID | Title | Type | Parent | Priority | Status |\n| --- | --- | --- | --- | --- | --- |\n| E1 | Parent | Epic | | P0 | In Progress |\n| T1 | Finished | Task | E1 | P0 | Done |\n| T2 | Review | Task | E1 | P1 | Review |\n";
        let tasks = parse_tasks(source).unwrap();
        let state = snapshot(&tasks, source);
        assert_eq!(state["taskCounts"]["total"], 3);
        assert_eq!(state["leafCounts"], json!({"done":1,"total":2}));
        assert_eq!(state["progress"], 33);
        assert_eq!(state["agents"][0]["id"], "E1");
        assert_eq!(state["source"]["sha256"], sha256_digest(source.as_bytes()));
    }

    #[test]
    fn task_snapshot_has_no_placeholder_for_an_empty_canonical_table() {
        let state = snapshot(&[], "");
        assert_eq!(state["agents"], json!([]));
        assert_eq!(state["taskCounts"]["total"], 0);
        assert_eq!(unavailable()["freshness"], "UNAVAILABLE");
    }

    #[test]
    fn hud_projection_is_bounded_and_set_task_state_preserves_canonical_source() {
        let ascii_title = "A".repeat(600);
        let cjk_title = "界".repeat(200);
        let long_id = "I".repeat(MAX_FIELD_BYTES + 1);
        let collision_id = format!("prefix-{}", "x".repeat(MAX_FIELD_BYTES - "prefix-".len()));
        let collision_dependency = format!("{collision_id}y");
        let mut dependencies = (0..64)
            .map(|index| format!("dependency-{index}"))
            .collect::<Vec<_>>();
        dependencies.push("界".repeat(200));
        dependencies.push(collision_dependency);
        dependencies.push("dependency-overflow".to_owned());
        let canonical = format!(
            "| ID | Title | Status | Dependencies |\n| --- | --- | --- | --- |\n| ASCII | {ascii_title} | In Progress | {} |\n| {collision_id} | {cjk_title} | Blocked | |\n| {long_id} | Long ID | In Progress | |\n",
            dependencies.join(", ")
        );
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "mission-center-hud-bounds-{}-{}",
            std::process::id(),
            now_millis()
        ));
        std::fs::create_dir_all(root.join("MissionCenter")).unwrap();
        std::fs::create_dir_all(root.join("output/mission-center-assets")).unwrap();
        for asset in HUD_MANAGED_ASSETS {
            std::fs::write(root.join("output/mission-center-assets").join(asset), asset).unwrap();
        }
        let tasks_path = root.join("MissionCenter/tasks.md");
        std::fs::write(&tasks_path, &canonical).unwrap();
        let canonical_before = std::fs::read(&tasks_path).unwrap();

        let workspace = MissionWorkspace::new(&root);
        let state = refresh(&workspace, &None);
        assert_eq!(state["freshness"], "VALID");
        assert_eq!(state["taskCounts"]["omittedLongId"], 1);
        assert_eq!(state["taskCounts"]["visible"], 2);
        assert_eq!(state["taskCounts"]["hidden"], 1);
        assert!(
            state["agents"]
                .as_array()
                .unwrap()
                .iter()
                .all(|agent| agent["id"] != long_id)
        );

        let ascii_agent = &state["agents"][0];
        assert!(ascii_agent["name"].as_str().unwrap().ends_with('…'));
        assert!(ascii_agent["task"].as_str().unwrap().ends_with('…'));
        assert!(ascii_agent["name"].as_str().unwrap().len() <= HUD_TITLE_MAX_BYTES);
        assert!(ascii_agent["task"].as_str().unwrap().len() <= HUD_TASK_MAX_BYTES);
        let dependencies = ascii_agent["dependencies"].as_array().unwrap();
        assert_eq!(dependencies.len(), MAX_LIST_ITEMS);
        assert!(
            dependencies
                .iter()
                .all(|dependency| dependency.as_str().unwrap().len() <= MAX_FIELD_BYTES)
        );
        assert_eq!(
            ascii_agent["dependencyCounts"],
            json!({"visible":64,"total":67,"omitted":3})
        );
        assert!(
            !dependencies
                .iter()
                .any(|dependency| dependency == &collision_id)
        );
        assert!(state["active"][0].as_str().unwrap().ends_with('…'));
        assert!(state["blocked"][0].as_str().unwrap().ends_with('…'));
        assert_eq!(state["blockedCount"], 1);

        let launcher = HudLauncher::new();
        let assets = crate::frozen_hud_assets(&crate::unavailable_runtime_state()).unwrap();
        let server = launcher
            .launch(
                HudServerConfig::new(&root).with_frozen_assets(assets),
                false,
            )
            .unwrap()
            .server;
        server
            .set_task_state(&serde_json::to_vec(&state).unwrap())
            .unwrap();
        launcher.shutdown_all().unwrap();

        assert_eq!(std::fs::read(&tasks_path).unwrap(), canonical_before);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn task_source_refresh_reads_edits_and_keeps_last_valid_on_invalid_source() {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "mission-center-task-refresh-{}-{}",
            std::process::id(),
            now_millis()
        ));
        std::fs::create_dir_all(root.join("MissionCenter")).unwrap();
        let path = root.join("MissionCenter/tasks.md");
        let source =
            "| ID | Title | Status |\n| --- | --- | --- |\n| T1 | Actual task | Review |\n";
        std::fs::write(&path, source).unwrap();
        let workspace = MissionWorkspace::new(&root);
        let first = refresh(&workspace, &None);
        assert_eq!(first["agents"][0]["status"], "Review");
        std::fs::write(&path, source.replace("Review", "Done")).unwrap();
        let second = refresh(&workspace, &Some(first));
        assert_eq!(second["agents"][0]["status"], "Done");
        assert_eq!(second["progress"], 100);
        std::fs::write(&path, "not a canonical table").unwrap();
        let stale = refresh(&workspace, &Some(second.clone()));
        assert_eq!(stale["freshness"], "STALE");
        assert_eq!(stale["agents"], second["agents"]);
        assert_eq!(stale["source"], second["source"]);
        assert_eq!(refresh(&workspace, &None)["freshness"], "UNAVAILABLE");
        assert_eq!(
            std::fs::read_to_string(&path).unwrap(),
            "not a canonical table"
        );
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn task_source_rejects_a_non_regular_file_without_opening_it() {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "mission-center-task-nonregular-{}-{}",
            std::process::id(),
            now_millis()
        ));
        std::fs::create_dir_all(root.join("MissionCenter/tasks.md")).unwrap();
        assert_eq!(
            refresh(&MissionWorkspace::new(&root), &None)["freshness"],
            "UNAVAILABLE"
        );
        std::fs::remove_dir_all(root).unwrap();
    }
}
