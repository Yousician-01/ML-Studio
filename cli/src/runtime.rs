use crate::{
    STOP,
    config::{self, Context},
    install, logs,
    process::{Identity, Managed},
};
use anyhow::{Context as _, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use std::{
    fs,
    io::{Read, Write},
    net::{SocketAddr, TcpListener, TcpStream},
    process::{Command, Stdio},
    sync::atomic::Ordering,
    thread,
    time::{Duration, Instant},
};

#[derive(Serialize, Deserialize)]
pub struct Session {
    pub nonce: String,
    pub supervisor: Identity,
    pub backend: Option<Identity>,
    pub frontend: Option<Identity>,
    pub phase: String,
    pub api_prefix: String,
    pub started_at: u64,
}

pub fn ports_free() -> Result<()> {
    // Keep both probes open until checked; startup still handles a later bind race.
    let _backend = TcpListener::bind(("127.0.0.1", 8000)).context(
        "Port 8000 is occupied. Stop the conflicting server; mls never kills unrelated processes",
    )?;
    let _frontend = TcpListener::bind(("127.0.0.1", 3000)).context(
        "Port 3000 is occupied. Stop the conflicting server; mls never kills unrelated processes",
    )?;
    Ok(())
}

pub fn healthy(port: u16, path: &str, backend: bool) -> bool {
    (|| -> Result<bool> {
        ensure!(
            path.starts_with('/') && !path.contains(['\r', '\n']),
            "Invalid health path"
        );
        let address = SocketAddr::from(([127, 0, 0, 1], port));
        let mut socket = TcpStream::connect_timeout(&address, Duration::from_secs(1))?;
        socket.set_read_timeout(Some(Duration::from_secs(2)))?;
        socket.set_write_timeout(Some(Duration::from_secs(2)))?;
        write!(
            socket,
            "GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
        )?;
        let mut bytes = Vec::new();
        socket.take(65536).read_to_end(&mut bytes)?;
        let response = String::from_utf8_lossy(&bytes);
        let okay = response.starts_with("HTTP/1.1 200 ") || response.starts_with("HTTP/1.0 200 ");
        if !backend {
            return Ok(okay);
        }
        let body = response
            .split_once("\r\n\r\n")
            .map(|(_, body)| body)
            .unwrap_or("");
        let value: serde_json::Value = serde_json::from_str(body)?;
        Ok(okay
            && value["status"] == "ok"
            && value["service"] == "ml-studio-api"
            && value["database"] == "ready")
    })()
    .unwrap_or(false)
}

fn read_session(context: &Context) -> Result<Session> {
    config::read_json(&context.state.join("session.json"))
}

pub fn has_live_supervisor(context: &Context) -> bool {
    read_session(context).is_ok_and(|session| session.supervisor.alive())
}

pub fn refuse_live_session(context: &Context) -> Result<()> {
    if context.state.join("session.json").exists() {
        let session = read_session(context).context(
            "Unreadable session record. Inspect it before proceeding; no PID will be killed",
        )?;
        ensure!(
            !session.supervisor.alive(),
            "A supervisor is active. Use mls abort before installing/starting"
        );
        ensure!(
            !session.backend.is_some_and(|i| i.alive())
                && !session.frontend.is_some_and(|i| i.alive()),
            "Stale supervisor has a verifiably live component. Preserve session evidence and stop the original session explicitly; no PID-file killing is performed"
        );
    }
    Ok(())
}

fn abort_requested(context: &Context, nonce: &str) -> bool {
    config::read_json::<String>(&context.state.join("abort.json"))
        .is_ok_and(|request| request == nonce)
}

pub fn start(context: &Context) -> Result<()> {
    context.prepare_state()?;
    let _lease = config::lock(&context.state.join("operation.lock"))?;
    refuse_live_session(context)?;
    println!("Checking installed application and database...");
    let installed = install::verify(context)?;
    let _workspace = config::lock(&installed.settings.home.join(".mls-runtime.lock"))?;
    ports_free()?;
    let mut session = Session {
        nonce: uuid::Uuid::new_v4().to_string(),
        supervisor: Identity::current()?,
        backend: None,
        frontend: None,
        phase: "Starting".into(),
        api_prefix: installed.settings.api_prefix.clone(),
        started_at: config::now(),
    };
    config::write_json(&context.state.join("session.json"), &session)?;
    let mut components: Vec<Managed> = Vec::new();
    let mut drains = Vec::new();
    let result = (|| -> Result<()> {
        for component in [logs::Component::Backend, logs::Component::Frontend] {
            ensure!(
                !STOP.load(Ordering::SeqCst) && !abort_requested(context, &session.nonce),
                "Startup cancelled"
            );
            let name = component.name();
            println!("Starting {name}...");
            let mut command = match component {
                logs::Component::Backend => {
                    let mut command = Command::new(&installed.python);
                    command.current_dir(context.repo.join("backend")).args([
                        "-B",
                        "-X",
                        "utf8",
                        "-m",
                        "uvicorn",
                        "mlstudio.main:create_app",
                        "--factory",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8000",
                        "--timeout-graceful-shutdown",
                        "12",
                    ]);
                    context.environment(&mut command);
                    command
                }
                logs::Component::Frontend => {
                    let mut command = Command::new(&installed.node);
                    #[cfg(windows)]
                    command.args(["--require", "../cli/node-signals.cjs"]);
                    command
                        .current_dir(context.repo.join("frontend"))
                        // Fixed relative argv avoids Node's Windows verbatim-path
                        // limitation; explicit cwd handles spaces and Unicode.
                        .arg("node_modules/next/dist/bin/next")
                        .args(["start", "--hostname", "127.0.0.1", "--port", "3000"])
                        .env("NODE_ENV", "production")
                        .env("NEXT_TELEMETRY_DISABLED", "1");
                    command
                }
            };
            command.stdout(Stdio::piped()).stderr(Stdio::piped());
            let mut child = Managed::spawn(&mut command)
                .with_context(|| format!("Cannot start {name}; use mls logs --component {name}"))?;
            let writer = logs::Writer::open(&context.state.join("logs"), name)?;
            drains.push(logs::drain(
                child.child.stdout.take().context("Missing stdout")?,
                writer.clone(),
                name,
                "stdout",
            ));
            drains.push(logs::drain(
                child.child.stderr.take().context("Missing stderr")?,
                writer,
                name,
                "stderr",
            ));
            match component {
                logs::Component::Backend => session.backend = Some(child.identity.clone()),
                logs::Component::Frontend => session.frontend = Some(child.identity.clone()),
            }
            components.push(child);
            config::write_json(&context.state.join("session.json"), &session)?;
            // A clean Windows install exhausted the earlier 90-second budget
            // before application startup. Allow a bounded first-start margin
            // for the ML stack rather than requiring a warmed environment.
            let deadline = Instant::now() + Duration::from_secs(180);
            loop {
                for (index, child) in components.iter_mut().enumerate() {
                    if let Some(status) = child.poll()? {
                        bail!(
                            "{} PID {} exited ({status}); partial startup is being stopped",
                            if index == 0 { "Backend" } else { "Frontend" },
                            child.identity.pid
                        );
                    }
                }
                ensure!(
                    !STOP.load(Ordering::SeqCst) && !abort_requested(context, &session.nonce),
                    "Startup cancelled"
                );
                let ready = match component {
                    logs::Component::Backend => {
                        healthy(8000, &format!("{}/health", session.api_prefix), true)
                    }
                    logs::Component::Frontend => healthy(3000, "/", false),
                };
                if ready {
                    // Next changes argv via process.title on Unix. Refresh through
                    // the owned child after readiness; supervisor stays strict.
                    let child = components.last_mut().context("Missing owned component")?;
                    ensure!(child.poll()?.is_none(), "{name} exited during readiness");
                    child.identity = Identity::capture(child.child.id())?;
                    match component {
                        logs::Component::Backend => session.backend = Some(child.identity.clone()),
                        logs::Component::Frontend => {
                            session.frontend = Some(child.identity.clone())
                        }
                    }
                    config::write_json(&context.state.join("session.json"), &session)?;
                    println!("{name} ready");
                    break;
                }
                ensure!(
                    Instant::now() < deadline,
                    "{name} readiness timed out after 180 seconds. Use mls logs --component {name}"
                );
                thread::sleep(Duration::from_millis(250));
            }
        }
        session.phase = "Running".into();
        config::write_json(&context.state.join("session.json"), &session)?;
        println!(
            "\nML Studio is available at http://127.0.0.1:3000\nWorkspace: {}\nPress Ctrl+C to stop both servers (or mls abort from another terminal).",
            installed.settings.home.display()
        );
        loop {
            if STOP.load(Ordering::SeqCst) || abort_requested(context, &session.nonce) {
                break;
            }
            for (index, child) in components.iter_mut().enumerate() {
                if let Some(status) = child.poll()? {
                    bail!(
                        "{} PID {} exited ({status}); stopping the other server",
                        if index == 0 { "Backend" } else { "Frontend" },
                        child.identity.pid
                    );
                }
            }
            thread::sleep(Duration::from_millis(250));
        }
        Ok(())
    })();
    println!("Stopping owned ML Studio servers...");
    while let Some(mut child) = components.pop() {
        child.stop();
    }
    let deadline = Instant::now() + Duration::from_secs(2);
    for drain in drains {
        while !drain.is_finished() && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(20));
        }
        if drain.is_finished() {
            let _ = drain.join();
        }
    }
    if read_session(context).is_ok_and(|record| record.nonce == session.nonce) {
        fs::remove_file(context.state.join("session.json"))?;
    }
    if abort_requested(context, &session.nonce) {
        let _ = fs::remove_file(context.state.join("abort.json"));
    }
    println!("Stopped. Logs and all application data retained.");
    if result.is_err() {
        eprintln!("Recent server output (also available with mls logs):");
        let _ = logs::show(context, false, None);
    }
    result
}

pub fn abort(context: &Context) -> Result<()> {
    if !context.state.join("session.json").exists() {
        println!("No active session.");
        return Ok(());
    }
    let session = read_session(context)?;
    if !session.supervisor.alive() {
        refuse_live_session(context)?;
        println!("Stale session; no verified live components. No processes were signalled.");
        return Ok(());
    }
    config::write_json(&context.state.join("abort.json"), &session.nonce)?;
    let deadline = Instant::now() + Duration::from_secs(40);
    while Instant::now() < deadline {
        if !context.state.join("session.json").exists() {
            println!("ML Studio stopped. Data and logs retained.");
            return Ok(());
        }
        ensure!(
            read_session(context).is_ok_and(|s| s.nonce == session.nonce),
            "Session changed during abort; no other session was touched"
        );
        thread::sleep(Duration::from_millis(200));
    }
    bail!(
        "Supervisor did not acknowledge shutdown in 40 seconds. Preserve logs and inspect the original terminal; no unverified PID was killed"
    )
}

pub fn status(context: &Context) -> Result<()> {
    println!(
        "Installation: {}\nCheckout: {}",
        if context.installed().is_ok() {
            "installed"
        } else {
            "not installed/incomplete"
        },
        context.repo.display()
    );
    if let Ok(installation) = context.installed() {
        println!(
            "Workspace: {}\nDatabase: {}",
            installation.settings.home.display(),
            installation.settings.database.display()
        );
    }
    if !context.state.join("session.json").exists() {
        println!("Session: inactive");
        return Ok(());
    }
    let session = read_session(context)?;
    let owner = session.supervisor.alive();
    let backend = session.backend.as_ref().is_some_and(Identity::alive);
    let frontend = session.frontend.as_ref().is_some_and(Identity::alive);
    let backend_health = backend && healthy(8000, &format!("{}/health", session.api_prefix), true);
    let frontend_health = frontend && healthy(3000, "/", false);
    let state = if !owner {
        "stale session"
    } else if session.phase == "Starting" {
        "starting"
    } else if backend && frontend && backend_health && frontend_health {
        "running"
    } else {
        "degraded"
    };
    println!(
        "Session: {state}\nBackend: owned_alive={backend}, healthy={backend_health}\nFrontend: owned_alive={frontend}, healthy={frontend_health}"
    );
    if owner && frontend && frontend_health {
        println!("Application URL: http://127.0.0.1:3000");
    }
    Ok(())
}
