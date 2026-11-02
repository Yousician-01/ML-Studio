use super::*;

#[test]
fn command_surface_and_flags() {
    for command in ["install", "start", "abort", "status", "doctor"] {
        assert!(Cli::try_parse_from(["mls", command]).is_ok());
    }
    assert!(Cli::try_parse_from(["mls", "logs", "--follow", "--component", "backend"]).is_ok());
    assert!(Cli::try_parse_from(["mls", "logs", "--component", "shell"]).is_err());
    assert!(Cli::try_parse_from(["mls", "terminal"]).is_err());
}

#[test]
fn paths_and_version_boundaries() {
    assert!(config::version_supported(
        "Python 3.12.0",
        "Python",
        &[3, 12, 0]
    ));
    assert!(!config::version_supported(
        "Python 3.11.9",
        "Python",
        &[3, 12, 0]
    ));
    assert!(config::version_supported("v22.13.0", "v", &[22, 13, 0]));
    assert!(!config::version_supported("v22.12.0", "v", &[22, 13, 0]));
    let root = std::env::temp_dir().join(format!("mls spaces \u{00e9} {}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(root.join("backend/alembic")).unwrap();
    std::fs::create_dir_all(root.join("frontend/src")).unwrap();
    std::fs::create_dir_all(root.join("cli")).unwrap();
    std::fs::write(root.join("cli/bridge.py"), "").unwrap();
    std::fs::write(root.join("cli/node-signals.cjs"), "").unwrap();
    std::fs::write(root.join("backend/pyproject.toml"), "").unwrap();
    std::fs::write(root.join("frontend/package-lock.json"), "").unwrap();
    assert!(config::validate_repo(&root).is_ok());
    assert!(config::venv_python(&root).starts_with(&root));
    std::fs::remove_dir_all(root).unwrap();
}

#[test]
fn install_inputs_ignore_generated_output_but_detect_source_changes() {
    let root = std::env::temp_dir().join(format!("mls-inputs-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(root.join("frontend/.next")).unwrap();
    std::fs::write(root.join("frontend/package.json"), "original").unwrap();
    let first = install::input_hash(&root, "frontend").unwrap();
    std::fs::write(root.join("frontend/.next/cache"), "generated").unwrap();
    assert_eq!(first, install::input_hash(&root, "frontend").unwrap());
    std::fs::write(root.join("frontend/.next/BUILD_ID"), "owned-build").unwrap();
    assert!(install::build_matches(&root, "owned-build"));
    assert!(!install::build_matches(&root, "external-build"));
    assert!(!install::build_matches(&root, ""));
    std::fs::write(root.join("frontend/package.json"), "changed").unwrap();
    assert_ne!(first, install::input_hash(&root, "frontend").unwrap());
    std::fs::remove_dir_all(root).unwrap();
}

#[test]
fn stale_pid_identity_never_counts_as_owned() {
    let identity = process::Identity::current().unwrap();
    assert!(identity.alive());
    let mut reused = identity.clone();
    reused.started += 1;
    assert!(!reused.alive());
    let mut other_exe = identity;
    other_exe.exe = PathBuf::from("unrelated executable");
    assert!(!other_exe.alive());
}

#[test]
fn dropping_partial_startup_stops_owned_child() {
    let mut command = test_child();
    let child = process::Managed::spawn(&mut command).unwrap();
    let identity = child.identity.clone();
    assert!(identity.alive());
    drop(child);
    assert!(!identity.alive());
}

#[test]
fn explicit_shutdown_is_bounded_and_reaped() {
    let mut command = test_child();
    let mut child = process::Managed::spawn(&mut command).unwrap();
    let identity = child.identity.clone();
    child.stop();
    assert!(!identity.alive());
    child.stop(); // repeated cleanup is safe
    #[cfg(windows)]
    let mut fast = {
        let mut command = std::process::Command::new("cmd.exe");
        command.args(["/d", "/c", "exit", "0"]);
        command
    };
    #[cfg(unix)]
    let mut fast = std::process::Command::new("true");
    let output = process::output(&mut fast, std::time::Duration::from_secs(5)).unwrap();
    assert!(output.status.success());
    assert!(output.stdout.is_empty());
}

fn test_child() -> std::process::Command {
    #[cfg(windows)]
    let mut command = {
        let mut c = std::process::Command::new("C:\\Windows\\System32\\ping.exe");
        c.args(["-n", "60", "127.0.0.1"]);
        c
    };
    #[cfg(unix)]
    let mut command = {
        let mut c = std::process::Command::new("sleep");
        c.arg("60");
        c
    };
    command
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    command
}
