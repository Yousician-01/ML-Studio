# Security

## Report vulnerabilities privately

Do not disclose vulnerabilities, exploit details, sensitive logs or affected data
in public Issues or PRs. GitHub Private Vulnerability Reporting has **not been
verified** for this release preparation. If the repository offers **Security →
Advisories → Report a vulnerability**, use that private action.

No private reporting email or alternative maintainer contact has been established.
If the private action is unavailable, withhold vulnerability details. You may open
a neutral administrative Issue asking maintainers to enable private reporting,
without naming the affected component, exploit or sensitive data. Share details
only after a verified private channel is available. Maintainers must verify the
GitHub setting before claiming private reporting is enabled; no response-time
guarantee is offered.

A private report should identify the relevant version/commit, impact and a minimal
synthetic reproduction. Redact credentials, private paths and Dataset contents.

## Supported boundary: trusted local development

ML Studio v0.4.0-beta.1 is a source-installed local beta supporting binary
classification, multiclass classification and regression.
Its verified acceptance environment is Windows, Python 3.14.2 and Node.js 24.13.0. Other platforms
and runtime versions are not acceptance-verified. It is not a production service.

- Bind frontend and backend to loopback using the documented startup commands.
  There is **no authentication or multi-user isolation**. CORS settings do not
  substitute for an authorization boundary. Do not expose the API to untrusted
  networks or treat the workspace as safe for mutually untrusted users.
- The exact generated Python runs in a separate subprocess with restricted
  environment inheritance, timeouts and bounded logs. It is **not sandboxed** and
  inherits the local user's filesystem and operating-system privileges. The API
  accepts only generated source for visual Runs.
- Code drafts are stored text; saving never executes them.
  Separate Code Run execution requires `MLSTUDIO_CODE_EXECUTION_ENABLED=true` and
  loopback peer/Host plus approved local Origin checks. Bind the backend to
  `127.0.0.1`. Trusted Python can access anything allowed to the local user; isolated
  working copies and path restrictions are not a sandbox. Process-tree cleanup is
  best effort, not containment of deliberately detached children. There is no
  interactive shell or filesystem-browsing API. Drafts/snapshots live in SQLite; recovery uses
  memory/sessionStorage. Code can contain secrets: treat these stores and source
  previews accordingly. Saved code snapshots are not execution records.
- CSV uploads default to a 50 MiB source limit. Parsing, profiling and model fitting
  can use substantially more memory than the source size; there is no hard memory
  quota or guaranteed workload isolation. Use appropriately sized trusted data.
- SQLite metadata, managed sources, generated code, results, model files and logs
  are local. MLflow's database and tracking artifacts are also under the configured
  MLSTUDIO_HOME; a remote server is not required or used by this integration.
- Source fingerprints and artifact hashes establish byte integrity, not file
  secrecy or trustworthiness. No encryption-at-rest or secure model-exchange format
  is provided. Never load untrusted external joblib/pickle artifacts as trusted
  ML Studio models.

## Sensitive data, recovery and retention

Keep sensitive Datasets, credentials and runtime workspaces out of Git and public
reports. Ignore rules are a convenience, not a security control. Frozen code and
tracking records can contain column names, target class labels and configuration;
logs and artifacts require appropriate local permissions and handling.

Source replacement retains old managed sources needed by historical Runs. Project
deletion is permanent but may leave local MLflow tracking copies. Crash remnants
may remain, and uncertain process/storage ownership blocks execution rather than
guessing that cleanup is safe. Follow [recovery and retention guidance](docs/development.md#recovery-and-retention);
do not edit historical Run rows or delete evidence to force recovery.

There is no cloud execution, deployment, arbitrary model import, automatic garbage
collection, backup service or multi-tenant security claim in this beta. Security
fixes should preserve immutable experiment evidence and avoid expanding scope.

## Dependency audit evidence

The 2026-11-03 release preparation audit reported zero npm production
vulnerabilities and 14 moderate development-tooling entries (no high/critical).
Advisory results change over time and do not establish absence of vulnerabilities.
Do not process untrusted repositories/patterns as though developer tools were
sandboxed. Python `pip-audit` and Rust `cargo-audit` were unavailable locally;
`pip check` verifies dependency consistency, not vulnerability status.

See [beta readiness](docs/development/beta-release-readiness.md) for exact commands,
validation limits and outstanding maintainer checks. No dependency upgrades were
made as part of the documentation release pass.
