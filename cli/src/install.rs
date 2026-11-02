use crate::{
    STOP,
    config::{self, Context, Installation},
    process::Managed,
    runtime,
};
use anyhow::{Context as _, Result, ensure};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::Read,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::Ordering,
    thread,
    time::{Duration, Instant},
};
use walkdir::WalkDir;

pub fn build_matches(repo: &Path, expected: &str) -> bool {
    !expected.is_empty()
        && fs::read_to_string(repo.join("frontend/.next/BUILD_ID")).is_ok_and(|id| id == expected)
}

pub fn input_hash(root: &Path, component: &str) -> Result<String> {
    let base = root.join(component);
    let mut paths = Vec::new();
    for entry in WalkDir::new(&base)
        .follow_links(false)
        .into_iter()
        .filter_entry(|e| {
            let name = e.file_name().to_string_lossy();
            !matches!(
                name.as_ref(),
                "node_modules"
                    | ".next"
                    | ".venv"
                    | "venv"
                    | "__pycache__"
                    | ".pytest_cache"
                    | ".ruff_cache"
                    | "dist"
                    | "monaco"
            ) && !name.ends_with(".egg-info")
        })
    {
        let entry = entry?;
        let name = entry.file_name().to_string_lossy();
        if entry.file_type().is_file()
            && !matches!(name.as_ref(), "next-env.d.ts" | "tsconfig.tsbuildinfo")
            && !name.ends_with(".pyc")
            && !name.ends_with(".db")
            && !name.ends_with(".log")
        {
            paths.push(entry.into_path());
        }
    }
    paths.sort();
    let mut hash = Sha256::new();
    for path in paths {
        let relative = path.strip_prefix(root)?.to_string_lossy();
        hash.update(relative.as_bytes());
        hash.update([0]);
        let mut file = fs::File::open(&path)?;
        let mut bytes = [0; 65536];
        loop {
            let count = file.read(&mut bytes)?;
            if count == 0 {
                break;
            }
            hash.update(&bytes[..count]);
        }
        hash.update([0]);
    }
    Ok(format!("{:x}", hash.finalize()))
}

pub fn executable(value: &Path) -> Result<PathBuf> {
    if value.is_absolute() || value.components().count() > 1 {
        let absolute = config::absolute(value)?;
        ensure!(
            absolute.is_file(),
            "Executable not found: {}",
            absolute.display()
        );
        return Ok(absolute);
    }
    for directory in std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default()) {
        let path = directory.join(value);
        if path.is_file() {
            return Ok(path);
        }
        #[cfg(windows)]
        {
            let path = path.with_extension("exe");
            if path.is_file() {
                return Ok(path);
            }
        }
    }
    anyhow::bail!(
        "{} not found on PATH. Install Python >=3.12 and Node >=22.13 with npm, or pass --python/--node",
        value.display()
    )
}

pub fn runtimes(context: &Context) -> Result<(PathBuf, PathBuf, PathBuf)> {
    let python = executable(
        context
            .config
            .python
            .as_deref()
            .unwrap_or(Path::new(if cfg!(windows) { "python" } else { "python3" })),
    )?;
    let node = executable(context.config.node.as_deref().unwrap_or(Path::new("node")))?;
    println!(
        "Python: {}",
        config::checked_version(&python, "Python", &[3, 12, 0])?
    );
    println!(
        "Node: {}",
        config::checked_version(&node, "v", &[22, 13, 0])?
    );
    let output = Command::new(&node)
        .args(["-p", "process.execPath"])
        .output()?;
    ensure!(output.status.success(), "Cannot resolve Node runtime");
    let node = PathBuf::from(String::from_utf8(output.stdout)?.trim());
    let parent = node.parent().context("Node executable has no parent")?;
    let npm = [parent.join("node_modules/npm/bin/npm-cli.js"), parent.join("../lib/node_modules/npm/bin/npm-cli.js"), parent.join("../share/nodejs/npm/bin/npm-cli.js"), PathBuf::from("/usr/share/nodejs/npm/bin/npm-cli.js")]
        .into_iter().find(|p| p.is_file()).context("npm-cli.js not found alongside Node. Install the official Node distribution including npm; shell wrappers are intentionally not used")?;
    let output = Command::new(&node).arg(&npm).arg("--version").output()?;
    ensure!(output.status.success(), "npm is not usable");
    println!("npm: {}", String::from_utf8_lossy(&output.stdout).trim());
    Ok((python, node, npm))
}

fn step(command: &mut Command, name: &str) -> Result<()> {
    println!("\n{name}...");
    let mut process = Managed::spawn(command)?;
    let deadline = Instant::now() + Duration::from_secs(30 * 60);
    loop {
        if let Some(status) = process.poll()? {
            ensure!(
                status.success(),
                "{name} failed ({status}); installation is not marked ready"
            );
            return Ok(());
        }
        ensure!(!STOP.load(Ordering::SeqCst), "Installation interrupted");
        ensure!(
            Instant::now() < deadline,
            "{name} exceeded 30-minute timeout"
        );
        thread::sleep(Duration::from_millis(200));
    }
}

pub fn run(context: &Context) -> Result<()> {
    context.prepare_state()?;
    let _lease = config::lock(&context.state.join("operation.lock"))?;
    runtime::refuse_live_session(context)?;
    runtime::ports_free()?;
    let (python, node, npm) = runtimes(context)?;
    let old = context.installed().ok();
    if !context.python().is_file() {
        ensure!(
            !context.state.join("venv").exists(),
            "Incomplete managed venv. Preserve it for diagnosis; do not overwrite it. Move it aside explicitly before reinstalling"
        );
        step(
            Command::new(&python)
                .arg("-m")
                .arg("venv")
                .arg(context.state.join("venv")),
            "Creating isolated backend environment",
        )?;
    }
    config::checked_version(&context.python(), "Python", &[3, 12, 0])?;
    let backend_hash = input_hash(&context.repo, "backend")?;
    let frontend_hash = input_hash(&context.repo, "frontend")?;
    if old
        .as_ref()
        .is_none_or(|i| i.backend_hash != backend_hash || i.python != context.python())
    {
        let mut command = Command::new(context.python());
        command
            .current_dir(context.repo.join("backend"))
            .args(["-m", "pip", "install", "-e", "."]);
        step(&mut command, "Installing backend from pyproject.toml")?;
    } else {
        println!("Backend inputs unchanged; reusing environment.");
    }
    step(
        Command::new(context.python()).args(["-m", "pip", "check"]),
        "Checking backend dependency consistency",
    )?;
    let settings = context.settings()?;
    fs::create_dir_all(&settings.home)?;
    let _workspace = config::lock(&settings.home.join(".mls-runtime.lock"))?;
    // Do not leave an old success marker if a new build/migration fails halfway.
    if context.state.join("installation.json").exists() {
        fs::remove_file(context.state.join("installation.json"))?;
    }
    let url = format!("http://127.0.0.1:8000{}", settings.api_prefix);
    let unchanged = old.as_ref().is_some_and(|i| {
        i.frontend_hash == frontend_hash
            && i.node == node
            && i.settings.api_prefix == settings.api_prefix
            && build_matches(&context.repo, &i.build_id)
    }) && context.repo.join("frontend/.next/BUILD_ID").is_file()
        && context
            .repo
            .join("frontend/node_modules/next/dist/bin/next")
            .is_file()
        && context
            .repo
            .join("frontend/public/monaco/assets/editor.worker.js")
            .is_file();
    if !unchanged {
        let dependencies_unchanged = old
            .as_ref()
            .is_some_and(|i| i.frontend_hash == frontend_hash && i.node == node)
            && context
                .repo
                .join("frontend/node_modules/next/dist/bin/next")
                .is_file();
        for (args, label) in [
            (&["ci", "--include=dev"][..], "Installing frontend lockfile"),
            (
                &["run", "build"][..],
                "Building production Next.js frontend",
            ),
        ] {
            if args[0] == "ci" && dependencies_unchanged {
                continue;
            }
            let mut command = Command::new(&node);
            command
                .arg(&npm)
                .args(args)
                .current_dir(context.repo.join("frontend"))
                .env("NODE_ENV", "production")
                .env("NEXT_PUBLIC_API_BASE_URL", &url)
                .env("NEXT_TELEMETRY_DISABLED", "1");
            step(&mut command, label)?;
        }
    } else {
        println!("Frontend inputs unchanged; reusing production build.");
    }
    println!(
        "\nWorkspace: {}\nDatabase: {}",
        settings.home.display(),
        settings.database.display()
    );
    println!(
        "Applying real Alembic migrations (whole-workspace backup before pending upgrades)..."
    );
    let output = context.bridge_output("migrate")?;
    ensure!(
        output.status.success(),
        "Migration/backup failed; installation is not ready. Existing data was not reset. Stop all non-CLI writers and check permissions/configuration/revision compatibility. {}",
        String::from_utf8_lossy(&output.stderr).trim()
    );
    let result: serde_json::Value = serde_json::from_slice(&output.stdout)?;
    if let Some(path) = result["backup"].as_str() {
        println!("Pre-upgrade backup: {path}");
    }
    let installation = Installation {
        cli_version: env!("CARGO_PKG_VERSION").into(),
        repo: context.repo.clone(),
        python: context.python(),
        node,
        build_id: fs::read_to_string(context.repo.join("frontend/.next/BUILD_ID"))?,
        backend_hash: input_hash(&context.repo, "backend")?,
        frontend_hash: input_hash(&context.repo, "frontend")?,
        settings,
        installed_at: config::now(),
    };
    ensure!(
        context.repo.join("frontend/.next/BUILD_ID").is_file(),
        "Production BUILD_ID missing"
    );
    config::write_json(&context.state.join("config.json"), &context.config)?;
    config::write_json(&context.state.join("installation.json"), &installation)?;
    config::write_json(&context.base.join("checkout.json"), &context.repo)?;
    println!("\nInstallation completed. Code Mode opt-in is unchanged.\nNext: mls start");
    Ok(())
}

pub fn verify(context: &Context) -> Result<Installation> {
    let installed = context.installed()?;
    ensure!(
        build_matches(&context.repo, &installed.build_id),
        "Production build was replaced outside mls; run mls install to rebuild with the recorded API configuration"
    );
    ensure!(
        installed.python.is_file() && installed.node.is_file(),
        "Installed runtime missing; run mls install"
    );
    ensure!(
        context.repo.join("frontend/.next/BUILD_ID").is_file()
            && context
                .repo
                .join("frontend/public/monaco/assets/editor.worker.js")
                .is_file(),
        "Production build/editor assets missing; run mls install"
    );
    ensure!(
        installed.backend_hash == input_hash(&context.repo, "backend")?
            && installed.frontend_hash == input_hash(&context.repo, "frontend")?,
        "Checkout changed since installation; run mls install"
    );
    let settings = context.settings()?;
    ensure!(
        settings.home == installed.settings.home
            && settings.database == installed.settings.database
            && settings.api_prefix == installed.settings.api_prefix,
        "Effective workspace/database/API changed. Refusing a silent workspace switch. Review configuration and run mls install explicitly"
    );
    let output = context.bridge_output("doctor")?;
    ensure!(
        output.status.success()
            && serde_json::from_slice::<serde_json::Value>(&output.stdout)?["ready"] == true,
        "Database is not ready; run mls doctor then mls install"
    );
    Ok(installed)
}

pub fn doctor(context: &Context) -> Result<()> {
    println!(
        "ML Studio Doctor (read-only)\nPlatform: {} {}\nCheckout: {}\nCLI state: {}",
        std::env::consts::OS,
        std::env::consts::ARCH,
        context.repo.display(),
        context.state.display()
    );
    let mut failures = false;
    if let Err(error) = runtimes(context) {
        println!("Prerequisites: {error:#}");
        failures = true;
    }
    if context.python().is_file() {
        match context.settings() {
            Ok(settings) => {
                println!(
                    "Workspace: {}\nDatabase: {}\nCode execution opt-in: {} (not sandboxed)",
                    settings.home.display(),
                    settings.database.display(),
                    settings.code_execution_enabled
                );
                if !settings.home.is_dir() {
                    println!("Workspace directory missing; run mls install");
                    failures = true;
                }
                let output = context.bridge_output("doctor")?;
                if output.status.success() {
                    let value: serde_json::Value = serde_json::from_slice(&output.stdout)?;
                    println!(
                        "Database revisions: current={} required={}",
                        value["current"], value["required"]
                    );
                    if value["ready"] != true {
                        failures = true;
                    }
                } else {
                    println!("Database inaccessible or configuration invalid");
                    failures = true;
                }
            }
            Err(error) => {
                println!("Settings: {error:#}");
                failures = true;
            }
        }
    } else {
        println!("Backend venv missing; run mls install");
        failures = true;
    }
    match verify(context) {
        Ok(_) => println!("Installation inputs/build/schema: ready"),
        Err(error) => {
            println!("Installation: {error:#}");
            failures = true;
        }
    }
    runtime::status(context)?;
    if !runtime::has_live_supervisor(context) {
        if let Err(error) = runtime::ports_free() {
            println!("Ports: {error:#}");
            failures = true;
        } else {
            println!("Ports 3000/8000: available");
        }
    }
    ensure!(
        !failures,
        "Doctor found issues; follow the messages above. No changes made."
    );
    Ok(())
}
