# Troubleshooting

Start with `mls doctor`, `mls status` and bounded `mls logs`. Redact private paths, column/class labels, code secrets and Dataset contents before sharing diagnostics. Never attach a real workspace publicly.

| Symptom | Check / safe next step |
| --- | --- |
| `mls` not found | Use the printed executable path or add its bin directory to user PATH. Open a new terminal after persistent changes. Bootstrap does not edit PATH. |
| Python/Node missing or old | Verify versions and npm; use `--python`/`--node` with absolute executables. Python >=3.12 and Node >=22.13 are minima, not proof of wheel compatibility. |
| Cargo missing during bootstrap | Install Rust/Cargo for source builds; verified local-artifact bootstrap needs trusted candidates. |
| PowerShell blocks script | Review script and organization policy; see [Installation](installation.md). Do not globally disable script security. |
| Port 3000/8000 occupied | Stop the instance you own or identify the unrelated listener. CLI will not kill it or select a new port. Avoid concurrent manual/CLI servers. |
| Missing/stale install or BUILD_ID | Stop the session and rerun `mls install` after relevant changes or a manual frontend rebuild. |
| Windows npm ci EPERM on a native binary | Stop your own frontend before reinstalling; loaded native binaries cannot be replaced. Do not kill an unrelated process. |
| Frontend build/npm failure | Inspect install output; verify Node/npm and committed lockfile. Do not delete the lockfile or blanket-use force/legacy-peer-deps. |
| Interrupted install | Partial operations are not marked successful. Inspect logs/doctor, resolve cause and retry. Do not blindly delete workspace/environment. |
| Migration failure | Stop writers; retain diagnostics, backup and recovery record. Do not force schema versions or delete history. Restore a consistent backup if needed. |
| API unavailable | Check `http://127.0.0.1:8000/api/v1/health`, frontend build-time API URL and loopback origins. CLI uses fixed local ports. |
| Invalid CSV | Use UTF-8 comma CSV with valid header/consistent widths. Missing values are allowed; infinity, malformed/unusable and oversized sources are rejected. No auto-repair/dialect detection. |
| Target rejected | Check [task rules](user-guide/projects-and-data.md), effective semantics and class population. Multiclass rejects missing targets; binary/regression exclude missing targets later. |
| Stale revision/preview | Refresh current Project/Dataset and review changes before save/run. Do not reuse hashes from another revision. |
| Run failure/unavailable metric | Read frozen diagnostics or metric reason. Unavailable is not zero. MLflow failure is separate from execution. |
| Integrity warning | Retain evidence and investigate storage changes. Do not regenerate historical source or edit hashes to conceal damage. |
| Code Run disabled | Configure real backend setting only for trusted local execution and restart. Saving drafts never executes them. See [Code workspace](user-guide/code-workspace.md). |

## Projects appear missing

Deleting a Git branch normally deletes source references, not the external application workspace. Confirm checkout/CLI installation, resolved `MLSTUDIO_HOME`, explicit `MLSTUDIO_DATABASE_URL`, saved CLI `--home`, and the backend working directory's `.env`. Different databases legitimately show different Projects. `MLS_STATE_HOME` controls launcher metadata, not Project storage.

Stop services before restoration. Locate the database and corresponding managed files together; do not migrate a guessed database over them or merge unrelated files manually. Keep a consistent backup. Ordinary CLI install preserves `.env` and data; Project deletion is a separate permanent action.

## Recovery limits

Recovery fails closed when process/storage ownership is uncertain; crash remnants may remain. Back up SQLite and managed files together offline. MLflow has separate records and may retain copies after deletion. No automatic garbage collection or continuous backup is provided. See [recovery guidance](development.md#recovery-and-retention) and [CLI](cli.md) for paths/process limits.
