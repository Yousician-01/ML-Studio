# Installation

Audience: users installing the local beta from a source checkout. For hot-reload development, use [Development](development.md). The [CLI reference](cli.md) owns storage and supervision details.

## Distribution and prerequisites

Use a trusted checkout of `release/v0.4.0-beta.1` while the release is prepared. No published binary/package is assumed. Do not install an unrelated package named `mls` from a package registry.

| Requirement | Declared minimum | Validation reference |
| --- | --- | --- |
| Python, with pip and venv | 3.12 | Windows Python 3.14.2 |
| Node.js, with npm | 22.13.0 | Windows Node 24.13.0, npm 11.6.2 |
| Rust/Cargo for source bootstrap | Rust 1.89 (crate MSRV) | CI pins Rust 1.99.1; use it for matching builds |
| Git | Available on PATH | Required for checkout/contribution |

Manifest minima do not establish testing on every version. Dependencies must also have compatible wheels. See [current validation evidence](development/beta-release-readiness.md). CLI targets are Windows x64, Linux GNU x64, macOS Apple Silicon and Intel. Other architectures/distributions are not acceptance-certified. Four-platform CI exists; confirm its results before promising cross-platform support.

Python and Node are prerequisites, not downloaded or embedded by Rust. Prefer official Node layouts including npm; alternative runtime-manager layouts may not be detected. Use [Python downloads](https://www.python.org/downloads/), [Node downloads](https://nodejs.org/en/download), [Git](https://git-scm.com/downloads), and [rustup](https://rustup.rs/).

## Windows PowerShell

Install the prerequisites and open a new terminal. Rust's MSVC toolchain needs C++ build tools and the Windows SDK described in the [official Windows instructions](https://rust-lang.github.io/rustup/installation/windows-msvc.html).

```powershell
python --version
node --version
npm.cmd --version
cargo --version
git clone --branch release/v0.4.0-beta.1 https://github.com/Yousician-01/ML-Studio.git
Set-Location ML-Studio
.\scripts\bootstrap-cli.ps1 -FromSource
```

The default installed executable is `%LOCALAPPDATA%\ML Studio CLI\tools\bin\mls.exe`. Bootstrap prints its exact path and does not change PATH. Use that path directly (PowerShell requires `&` before a quoted executable path), or add the directory for this terminal:

```powershell
$env:Path = "$env:LOCALAPPDATA\ML Studio CLI\tools\bin;$env:Path"
mls --version
mls install
mls doctor
mls start
```

For persistent discovery, add that **directory** to your user's Path through Windows Environment Variables, then open a new terminal. Do not replace the existing Path. If script execution is blocked, inspect the checkout and follow your organization's policy; do not disable execution policy globally. After reviewing the script, a process-only invocation can use:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap-cli.ps1 -FromSource
```

## macOS: Apple Silicon and Intel

Use native Python, Node and Rust matching the machine architecture. With an existing trusted Homebrew installation:

```sh
brew install git python@3.14 node@24
export PATH="$(brew --prefix python@3.14)/libexec/bin:$(brew --prefix node@24)/bin:$PATH"
# Persist these runtime paths in your actual shell profile if needed.
python3 --version
node --version
npm --version
```

See the [Python formula](https://formulae.brew.sh/formula/python@3.14) and [Node formula](https://formulae.brew.sh/formula/node@24). Install Rust using official rustup instructions; native compilation also needs Apple's command-line developer tools (`xcode-select --install` if absent).

```sh
git clone --branch release/v0.4.0-beta.1 https://github.com/Yousician-01/ML-Studio.git
cd ML-Studio
sh scripts/bootstrap-cli.sh --source
export PATH="$HOME/.local/bin:$PATH"
mls --version
mls --python "$(command -v python3)" install
mls doctor
mls start
```

Bootstrap selects arm64 or x86_64 from the host. Runtime acceptance on each architecture is separate; these commands have not been run on macOS during this local release pass.

## Linux: GNU x64

The automated target is GitHub's Ubuntu runner, not every Linux distribution. Install Git, Python >=3.12 including pip/venv, Node >=22.13 with npm, and Rust/Cargo through trusted distribution or official instructions. Source builds need a C compiler/linker and libc development headers (for example Debian/Ubuntu's `build-essential`). Python builds may need more headers if wheels are unavailable. Distribution defaults may be too old: verify versions instead of assuming `apt install` chooses compatible runtimes. musl/Alpine and non-x64 Linux are not claimed supported here.

```sh
python3 --version
node --version
npm --version
cargo --version
git clone --branch release/v0.4.0-beta.1 https://github.com/Yousician-01/ML-Studio.git
cd ML-Studio
sh scripts/bootstrap-cli.sh --source
export PATH="$HOME/.local/bin:$PATH"
mls --version
mls --python "$(command -v python3)" install
mls doctor
mls start
```

For persistent PATH on macOS/Linux, place `export PATH="$HOME/.local/bin:$PATH"` once in the startup file your shell actually reads: commonly `~/.zshrc` for interactive zsh or `~/.bashrc` for interactive Bash (login shells may use a profile). Open a new shell. Other shells need their own syntax. Alternatively invoke `"$HOME/.local/bin/mls"` directly. Bootstrap does not edit profiles.

## Daily lifecycle

| Command | Purpose |
| --- | --- |
| `mls --version` | Confirm CLI identity: 0.4.0-beta.1 |
| `mls install` | Prepare managed Python environment, npm dependencies, production build and backed-up migrations; initially and after relevant source/configuration changes |
| `mls doctor` | Read-only prerequisite/configuration/schema diagnostics; does not migrate |
| `mls start` | Run real FastAPI on 127.0.0.1:8000 and real production Next.js on 127.0.0.1:3000 in foreground |
| `mls status` | Inspect installation and verified server identity/readiness |
| `mls logs` | Show bounded recent persistent backend/frontend logs |
| `mls logs --follow --component backend` | Follow a component; stopping log following does not stop servers |
| `mls abort` | Ask the verified live supervisor to stop both owned servers |

Open http://127.0.0.1:3000 after readiness. Ctrl+C in the `start` terminal is normal shutdown. Use another terminal for status/logs/abort, inside the checkout or with `mls --repo "path/to/ML-Studio" ...`. Occupied ports fail explicitly; the CLI does not select another port or kill unrelated listeners. Missing prerequisites produce diagnostics instead of silently installing runtimes.

Source bootstrap builds only the launcher. `mls install` installs the application. `mls start` uses production servers; `npm run dev` is a separate developer workflow. Rust does not replace, merge or embed either application server.

## Workspace, upgrades and preservation

Keep the checkout: editable backend and Alembic depend on it. The CLI-managed venv is separate from `backend/.venv`. Rebuilding the frontend manually can invalidate the recorded build; rerun `mls install`.

Application data defaults to the platform's ML Studio user-data directory. CLI metadata/logs use a separate `ML Studio CLI` directory keyed by checkout. `mls --home "absolute/path" install` selects an explicit workspace; `MLS_STATE_HOME` changes CLI metadata only. See [CLI storage](cli.md) and [environment configuration](development.md).

**Before upgrades, stop every backend/worker, including manual processes.** CLI backs up an existing workspace before pending migrations to a sibling backup directory and records recovery information. It preserves `.env` and does not move/delete Projects. This is not a continuous backup service. Manual Alembic users must back up SQLite and managed files together. Head is `0009_multiclass`; downgrade across recent task/Code Mode migrations is refused, so rollback uses a consistent backup.

A real `backend/.env` (read from the backend working directory) or environment variables configure settings. Editing `.env.example` has no effect. Check **both** `MLSTUDIO_HOME` and any `MLSTUDIO_DATABASE_URL`: an explicit database URL can still point outside a newly selected home. Never use a real workspace for disposable testing.

No separate MLflow server or database service is needed. For errors, use [Troubleshooting](troubleshooting.md). For checksum-verified local candidates instead of source compilation, see [CLI bootstrap options](cli.md); do not assume Release assets have been published.
