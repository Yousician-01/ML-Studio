use crate::Cli;
use anyhow::{Context as _, Result, bail, ensure};
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File},
    io::Write,
    path::{Path, PathBuf},
    process::Command,
};

#[derive(Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub home: Option<PathBuf>,
    pub python: Option<PathBuf>,
    pub node: Option<PathBuf>,
}

pub struct Context {
    pub repo: PathBuf,
    pub state: PathBuf,
    pub base: PathBuf,
    pub config: Config,
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Settings {
    pub home: PathBuf,
    pub database: PathBuf,
    pub api_prefix: String,
    pub code_execution_enabled: bool,
}

#[derive(Serialize, Deserialize)]
pub struct Installation {
    pub cli_version: String,
    pub repo: PathBuf,
    pub python: PathBuf,
    pub node: PathBuf,
    pub backend_hash: String,
    pub frontend_hash: String,
    #[serde(default)]
    pub build_id: String,
    pub settings: Settings,
    pub installed_at: u64,
}

impl Context {
    pub fn discover(args: &Cli) -> Result<Self> {
        platform()?;
        let base = match std::env::var_os("MLS_STATE_HOME") {
            Some(path) => absolute(Path::new(&path))?,
            None => dirs::data_local_dir()
                .context("No user-local data directory")?
                .join("ML Studio CLI"),
        };
        let repo = if let Some(repo) = &args.repo {
            repo.canonicalize().context("Cannot resolve --repo")?
        } else {
            let cwd = std::env::current_dir()?;
            cwd.ancestors().find(|p| validate_repo(p).is_ok()).map(Path::to_path_buf)
                .or_else(|| read_json::<PathBuf>(&base.join("checkout.json")).ok())
                .context("Run inside the ML Studio checkout, or pass --repo <path>; bootstrap does not download the application")?
                .canonicalize()?
        };
        validate_repo(&repo)?;
        let key = format!("{:x}", Sha256::digest(repo.to_string_lossy().as_bytes()));
        let state = base.join(&key[..20]);
        let mut config: Config = if state.join("config.json").exists() {
            read_json(&state.join("config.json"))?
        } else {
            Config::default()
        };
        if let Some(home) = &args.home {
            config.home = Some(absolute(home)?);
        }
        if let Some(python) = &args.python {
            config.python = Some(runtime_path(python)?);
        }
        if let Some(node) = &args.node {
            config.node = Some(runtime_path(node)?);
        }
        Ok(Self {
            repo,
            state,
            base,
            config,
        })
    }

    pub fn python(&self) -> PathBuf {
        venv_python(&self.state.join("venv"))
    }

    pub fn prepare_state(&self) -> Result<()> {
        fs::create_dir_all(&self.state)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&self.state, fs::Permissions::from_mode(0o700))?;
        }
        Ok(())
    }

    pub fn bridge(&self, action: &str) -> Command {
        let mut command = Command::new(self.python());
        command
            .current_dir(self.repo.join("backend"))
            .args(["-B", "-X", "utf8"])
            .arg(self.repo.join("cli/bridge.py"))
            .arg(action);
        self.environment(&mut command);
        command
    }

    pub fn environment(&self, command: &mut Command) {
        // Other application settings retain their existing environment > .env > default precedence.
        command
            .env("MLSTUDIO_ENVIRONMENT", "production")
            .env("PYTHONUTF8", "1");
        if let Some(home) = &self.config.home {
            command.env("MLSTUDIO_HOME", home);
        }
    }

    pub fn bridge_output(&self, action: &str) -> Result<std::process::Output> {
        crate::process::output(
            &mut self.bridge(action),
            std::time::Duration::from_secs(if action == "migrate" { 1800 } else { 60 }),
        )
    }

    pub fn settings(&self) -> Result<Settings> {
        let output = self
            .bridge_output("settings")
            .context("Cannot read backend Settings; run mls install")?;
        ensure!(
            output.status.success(),
            "Backend configuration is invalid: {}. Run mls doctor (configuration values are not printed).",
            String::from_utf8_lossy(&output.stderr).trim()
        );
        serde_json::from_slice(&output.stdout).context("Invalid backend settings response")
    }

    pub fn installed(&self) -> Result<Installation> {
        let installation: Installation = read_json(&self.state.join("installation.json"))
            .context("Installation incomplete or absent. Run mls install")?;
        ensure!(
            installation.repo == self.repo,
            "Installation checkout mismatch; run mls install"
        );
        Ok(installation)
    }
}

pub fn platform() -> Result<()> {
    ensure!(
        matches!(
            (std::env::consts::OS, std::env::consts::ARCH),
            ("windows", "x86_64") | ("linux", "x86_64") | ("macos", "x86_64" | "aarch64")
        ),
        "Target is not supported; use the documented source developer setup"
    );
    Ok(())
}

pub fn validate_repo(path: &Path) -> Result<()> {
    for entry in [
        "backend/pyproject.toml",
        "backend/alembic",
        "frontend/package-lock.json",
        "frontend/src",
        "cli/bridge.py",
        "cli/node-signals.cjs",
    ] {
        ensure!(
            path.join(entry).exists(),
            "Not an ML Studio checkout: missing {entry}"
        );
    }
    Ok(())
}

pub fn venv_python(root: &Path) -> PathBuf {
    root.join(if cfg!(windows) {
        "Scripts/python.exe"
    } else {
        "bin/python"
    })
}

pub fn absolute(path: &Path) -> Result<PathBuf> {
    Ok(if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()?.join(path)
    })
}

fn runtime_path(path: &Path) -> Result<PathBuf> {
    if path.is_absolute() || path.components().count() > 1 {
        absolute(path)
    } else {
        Ok(path.to_path_buf())
    }
}

pub fn read_json<T: DeserializeOwned>(path: &Path) -> Result<T> {
    serde_json::from_slice(
        &fs::read(path).with_context(|| format!("Cannot read {}", path.display()))?,
    )
    .with_context(|| format!("Invalid JSON in {}", path.display()))
}

pub fn write_json(path: &Path, value: &impl Serialize) -> Result<()> {
    fs::create_dir_all(path.parent().context("Missing parent directory")?)?;
    // Atomic same-directory replacement prevents readers seeing a partial record.
    let temporary = path.with_extension(format!("{}.tmp", uuid::Uuid::new_v4()));
    let mut file = File::options()
        .write(true)
        .create_new(true)
        .open(&temporary)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        file.set_permissions(fs::Permissions::from_mode(0o600))?;
    }
    file.write_all(&serde_json::to_vec_pretty(value)?)?;
    file.sync_all()?;
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;
        use windows_sys::Win32::Storage::FileSystem::{
            MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MoveFileExW,
        };
        let from: Vec<u16> = temporary.as_os_str().encode_wide().chain(Some(0)).collect();
        let to: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
        // SAFETY: both pointers reference live, NUL-terminated native paths.
        ensure!(
            unsafe {
                MoveFileExW(
                    from.as_ptr(),
                    to.as_ptr(),
                    MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
                )
            } != 0,
            "Cannot atomically replace CLI state: {}",
            std::io::Error::last_os_error()
        );
    }
    #[cfg(unix)]
    fs::rename(temporary, path)?;
    Ok(())
}

pub fn now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

pub fn version_supported(value: &str, prefix: &str, minimum: &[u32; 3]) -> bool {
    let pieces: Vec<u32> = value
        .trim()
        .strip_prefix(prefix)
        .unwrap_or("")
        .trim()
        .split('.')
        .map(str::parse)
        .collect::<std::result::Result<_, _>>()
        .unwrap_or_default();
    pieces.len() == 3 && pieces.as_slice() >= minimum.as_slice()
}

pub fn checked_version(executable: &Path, prefix: &str, minimum: &[u32; 3]) -> Result<String> {
    let output = Command::new(executable).arg("--version").output()
        .with_context(|| format!("{} is unavailable. Install {prefix} {}.{}.{} or newer, or pass its executable path", executable.display(), minimum[0], minimum[1], minimum[2]))?;
    let value = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    if !output.status.success() || !version_supported(&value, prefix, minimum) {
        bail!(
            "Incompatible {}: {value}; require >= {}.{}.{}",
            executable.display(),
            minimum[0],
            minimum[1],
            minimum[2]
        );
    }
    Ok(value)
}

pub fn lock(path: &Path) -> Result<File> {
    fs::create_dir_all(path.parent().context("Missing lock parent")?)?;
    let file = File::options()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(path)?;
    file.try_lock().with_context(|| {
        format!(
            "Another install/session owns {}. Use mls status; never delete a live lock",
            path.display()
        )
    })?;
    Ok(file)
}
