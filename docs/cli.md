# ML Studio local CLI (beta)

For OS-specific setup, use [Installation](installation.md). Current local validation
and remote/platform limits are in [beta readiness](development/beta-release-readiness.md).

`mls` installs this checkout and supervises **two independent real servers**:
Python FastAPI and production Node.js Next.js. Rust does not serve the application,
replace APIs, run ML workloads, or store arbitrary Python in the visual Pipeline.
Keep the checkout: editable Python installation and Alembic need its files.

## Prerequisites and bootstrap

Install Python **>=3.12** with pip/venv and Node.js **>=22.13.0** with npm.
The locally verified versions are Python 3.14.2, Node 24.13.0 and npm 11.6.2 on
Windows x64. Runtime versions satisfying manifest ranges still need compatible
dependency wheels. Official Node distributions, including npm-cli.js beside Node
or under the standard Unix lib/share locations, are supported. Alternative runtime
manager layouts may require installing the official distribution. No Python/Node
runtime is automatically downloaded, system-wide packages installed, or PATH changed.

Prebuilt CLI release assets are **not published by this change**. The build workflow
prepares binaries/checksums; a manually dispatched run retains review candidates as
seven-day CI artifacts, not GitHub Release assets. PR runs do not upload binaries.
No workflow creates releases/tags or publishes release assets. When trusted release
assets are published, obtain the matching binary and SHA256SUMS from the same official
release; checksums detect corruption, not a compromised publisher. Local-artifact
bootstrap verifies them before copying. Do not run untrusted binaries/scripts.

Until publication, install Rust/Cargo from https://rustup.rs and build from source:

```powershell
# Windows x64, from the checkout
.\scripts\bootstrap-cli.ps1 -FromSource
# Script prints the full mls.exe path; add its bin directory to user PATH manually.
```

```sh
# macOS/Linux (implementation/build targets; not locally acceptance-verified)
sh scripts/bootstrap-cli.sh --source
# Add ~/.local/bin to PATH manually, if needed.
```

For local prebuilt candidates use `-ArtifactDirectory <directory>` (PowerShell) or
`--assets <directory>` (sh). Source bootstrap needs Cargo; artifact bootstrap does
not. For a published release, manually download its matching binary/checksum first,
then use these same local-artifact flags. There is no release downloader or remote
bootstrap mode; a source clone or a past application release is not a CLI binary.
Choose one bootstrap mode and stop an active CLI session before replacing its binary.
No script downloads binaries or modifies shell profiles. The Windows default
binary directory is `%LOCALAPPDATA%\ML Studio CLI\tools\bin`; Unix defaults to
`~/.local/bin` (`MLS_BIN_DIR` overrides the bootstrap destination).

Reproducible CLI build command: `cargo +1.99.1 build --manifest-path cli/Cargo.toml
--release --locked`. Cargo.lock pins Rust dependencies. This is not a claim of
byte-identical cross-platform application dependencies: Python uses the existing
pyproject ranges and npm uses the committed lockfile. CLI version comes from
Cargo.toml; existing Python/frontend package versions remain independent.

## Install and run

Stop **all** ML Studio backends/workers, including manually started instances,
before installation or migration. The CLI rejects occupied default ports and an
active managed session; it cannot lock out arbitrary external SQLite writers.

```text
mls install
mls start
mls status
mls logs
mls logs --follow --component backend
mls abort
mls doctor
```

Run from inside the checkout, pass `--repo <checkout>`, or use the last successfully
installed checkout recorded in CLI state. `--python <executable>` and `--node
<executable>` select prerequisites. The CLI creates a separate managed venv; it
does not replace `backend/.venv`. It uses `pip install -e .`, `pip check`, the real
`npm ci` (including editor postinstall), `npm run build`, and Alembic upgrade head.
Unchanged source hashes reuse a valid environment/build. Interrupted operations
never publish a successful installation marker. Preserve an incomplete venv and
inspect it; installation does not silently delete/replace it.
The recorded production BUILD_ID is checked as well: a manual frontend rebuild
invalidates the installation until `mls install` rebuilds with its API configuration.

Start requires matching installed source inputs, build assets and database head.
It launches the venv interpreter with `-m uvicorn mlstudio.main:create_app --factory`
and Node with the installed Next CLI `start`, without reload/dev mode/shell wrappers.
Both bind **127.0.0.1** on ports **8000/3000**. Port conflicts fail without killing
the occupant; there is no fallback port. The frontend receives the resolved API
prefix at build time through NEXT_PUBLIC_API_BASE_URL. Backend readiness uses the
existing schema-aware `/api/v1/health` (or configured prefix); frontend readiness
requires HTTP 200. The URL is printed only after both owned roots are alive/ready.
Readiness allows 180 seconds per server, including cold ML imports in a fresh
environment; install subprocesses allow 30 minutes.
Backend configuration/schema probes allow 60 seconds. Migration/backup helpers are
also owned, cancellable subprocesses with a 30-minute bound and bounded output.

## Configuration and data compatibility

Application storage **does not move**. Existing backend Settings resolves it:
Windows LocalAppData/ML Studio, macOS Application Support/ML Studio, and Linux's
platformdirs/XDG user data path, unless MLSTUDIO_HOME or backend/.env overrides it.
An explicit MLSTUDIO_DATABASE_URL remains authoritative for the SQLite file.
Datasets, Runs, drafts and MLflow retain their current workspace layout. No separate
MLflow server is started; its existing local integration initializes tracking.

CLI management records live under OS user-local data/`ML Studio CLI/<checkout-hash>`:
`config.json`, `installation.json`, `session.json`, locks, managed `venv/`, and
`logs/`. The last-checkout pointer lives in the parent directory. `MLS_STATE_HOME`
overrides **only CLI metadata/venv/logs**, useful for isolated acceptance; it never
selects the application database. Do not move a checkout without reinstalling.

Workspace precedence: explicit `--home` > saved CLI config home > process
MLSTUDIO_HOME > backend/.env > backend platform default. Python/Node executable
precedence: command argument > config > PATH. The first explicit home/runtime choices
are persisted only after successful installation. Other backend settings preserve
environment > .env > application default precedence. CLI forces production mode,
loopback server arguments, and the build-time API URL. Never store credentials in
CLI JSON. A changed effective home/database/API prefix blocks startup until explicit
reinstallation, preventing accidental empty-workspace switches. Both workspace and
database paths are printed by install/status/doctor.

Before a pending upgrade, the CLI copies the whole workspace to a UUID directory
under a sibling `<workspace name> backups/`, backing up SQLite/MLflow databases using
SQLite's backup API and checking backup integrity. An external configured database
is backed up separately with `recovery.json` instructions. Links/junctions are refused.
Copies are not automatically deleted; ensure enough disk space and protect backups
as private data. Failure stops migration. No downgrade/reset/stamp is performed.
Recovery is explicit: stop all writers, restore workspace and external DB together
to their original paths with the matching application revision. Backups are offline
recovery aids, not a transactional snapshot against uncontrolled external writers.

## Lifecycle, logs and security

One install/start operation owns an OS file lock; a workspace lock also prevents
two managed checkouts from using the same workspace. Session records include a
random nonce and supervisor/server PID, executable, arguments and start time.
Status checks process identity and HTTP readiness, not just PID-file existence.
`abort` sends a nonce-scoped request to the verified live supervisor; it never kills
a PID from stale metadata. Stale records with verified live components block restart
for explicit recovery rather than guessing ownership. Data/logs are retained.

Ctrl+C or abort stops frontend/backend, waits up to 15 seconds per root, then forces
only owned processes. Windows creates each root suspended, attaches a kill-on-close
Job, then resumes it; descendant processes die if the supervisor crashes.
A Windows-only Node preload forwards targeted
CTRL_BREAK to Next's existing SIGTERM cleanup handler; it serves no HTTP or app
logic and the real Next CLI remains the entry point. Unix uses
process groups and TERM/KILL. Linux additionally requests parent-death SIGTERM for
roots. On macOS, abrupt supervisor death can leave roots alive; on Unix, grandchildren
that deliberately create new sessions are outside group containment. Normal backend
shutdown owns workload cleanup, and restart reconciliation handles interrupted ML
execution. This is not a daemon/service manager or a security sandbox. After a hard
crash inspect status/logs and original processes; do not delete locks or kill random
PIDs. CLI handles Ctrl+C/TERM but cannot handle SIGKILL/power failure gracefully.

Logs contain timestamps (UTC Unix seconds), component and stdout/stderr identifiers.
They rotate at approximately 5 MiB with three older files per component (about 40 MiB
total). Reads/tails are bounded to 32 KiB per component; follow works after rotation
and Ctrl+C only exits the log viewer. No environment dump is logged. Logs can still
contain sensitive output emitted by dependencies; protect/share them carefully.
The CLI does not copy Dataset rows into metadata or change backend privacy policies.

`doctor` is read-only: it checks runtimes/npm, venv, inputs/build, Settings, database
head, workspace existence, ports and session. It does not migrate, repair or create
databases. Failures are actionable; invalid backend configuration is sanitized.

Manual Code Run execution remains **opt-in**, defaults false, and is **not sandboxed**. Configure
MLSTUDIO_CODE_EXECUTION_ENABLED deliberately in backend/.env or the environment only
for trusted Python. install/start never enable it. The application remains local
single-user software; do not expose its ports through public proxies/tunnels.

## Acceptance and platform limits

Windows x64 is the local validation target. Linux x64/macOS ARM64/Intel have native
code/build checks. The CLI workflow now runs one disposable install/build and real
two-server lifecycle smoke on each of those four targets, using Python 3.14.2 and
Node 24.13.0. It checks version/help, prerequisite discovery, doctor, both HTTP
endpoints, status, logs, abort and closed ports. These jobs are configured, not claimed
passed until GitHub runs them; they also audit the installed production dependency tree.
Linux/macOS runtime acceptance remains pending;
passing smoke still does not replace manual UI/ML and Ctrl+C acceptance per platform.
No prebuilt bootstrap is claimed operational before asset
publication. No auto-update, remote downloader, privileged install, or global runtime
provisioning exists. Keep original manual developer startup available.
The patched Next.js 16.4.1 clean-install smoke passed locally on Windows. An earlier
run exhausted the former 90-second backend startup allowance; the CLI now allows
180 seconds per server, and the clean rerun reached backend HTTP readiness in about
75 seconds. Failed smoke runs retain their temporary evidence directory for diagnosis.
Linux candidates use the native GNU/glibc runner target, not musl/Alpine; publication
still requires validating the intended OS baseline.

Run that same narrow smoke locally with a prerequisite Python (it creates fresh
temporary application and CLI directories, forces Code Mode execution off, and builds
the frontend once):

```text
python cli/smoke.py --binary cli/target/release/mls.exe
# Unix: use cli/target/release/mls instead.
```

The candidate workflow emits `mls-windows-x64.exe`, `mls-linux-x64`,
`mls-macos-arm64`, or `mls-macos-x64`, each with its own `SHA256SUMS`. Run the
workflow manually against the reviewed commit to retain candidates; validate the
matching archive/checksum and platform before any separate authorized publication.

### Frontend security baseline

Next.js and its ESLint configuration are pinned to **16.4.1**, the minimum patched
release for [GHSA-2464-fhr4-w9xw](https://github.com/advisories/GHSA-2464-fhr4-w9xw),
[GHSA-p3m5-59mp-jv5r](https://github.com/advisories/GHSA-p3m5-59mp-jv5r), and
[GHSA-673q-mjm6-r5xr](https://github.com/advisories/GHSA-673q-mjm6-r5xr).
Source inspection found no image optimization usage, Server Actions, or `use cache`
functions; absence of explicit usage is not a reason to retain vulnerable framework
code. React remains unchanged. The development-only transitive Zod lock entry is
4.6.7, addressing [GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5)
without adding a direct dependency or override.

On 2026-11-02, `npm audit --omit=dev` reported zero vulnerabilities after lockfile
resolution. The full tree retained 14 moderate development-tooling findings and no
high/critical findings. Those are not suppressed or treated as a clean full audit;
review them separately. Re-run the production audit before publication because the
advisory database changes over time. These checks do not make Code Mode sandboxed.

Manual acceptance (use disposable MLSTUDIO_HOME and MLS_STATE_HOME first): bootstrap,
install twice, verify reuse and retained projects, start, open the printed URL,
create/open a Project, inspect Dataset/Prepare/Train/Evaluate/Code, then status/logs
from a second terminal. Follow logs and Ctrl+C (app must stay running). Abort and
verify both ports close. Start again and Ctrl+C the supervisor. Check occupied ports,
stale session safety, startup failure cleanup, and an existing-workspace upgrade
backup before accepting each platform. Never intentionally damage your real data.
