# Development

## Phase 0 status

The foundation runs a FastAPI API, a Next.js shell, SQLite connectivity, and
Alembic migrations. No Project, Dataset, Pipeline, Run, ML, or AI behavior exists
yet. The [v0.1 contracts](specifications/project-v0.1.md) remain authoritative.

Keep changes scoped, use mature libraries, preserve exact generated-source
execution and training-only preprocessing in later phases, and validate behavior
with meaningful tests. Follow [Contributing](../CONTRIBUTING.md). Vision explains
why; Roadmap stages work; Prototype summarizes scope; Architecture explains the
system; specifications govern contracts; ADRs preserve decisions; Issues track
work; PRs record review; CHANGELOG records user-visible changes; Git records edits.

## Verified local setup

The backend targets Python 3.12+. These commands were verified on Windows
PowerShell using Python 3.14.2 and Node 24.13.0. The frontend requires Node 22.13+
and npm; Node 24 is recommended. Other platforms were not exercised in Phase 0.
No Docker or separate database service is needed.

From the repository root:

```powershell
python -m venv backend/.venv
cd backend
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Run backend commands from `backend/`. Defaults work without an environment file.
The optional [backend example](../backend/.env.example) lists settings; a local
`.env` in the command's current directory is loaded, and environment variables
take precedence. Never commit a real environment file.

Initialize the database, then start the backend:

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic current
.venv/Scripts/python.exe -m uvicorn mlstudio.main:create_app --factory --host 127.0.0.1 --port 8000
```

The base migration reaches `0001_foundation (head)` and creates only Alembic's
version table. There are no domain tables. Startup does not run migrations or
call `metadata.create_all()`; Alembic owns schema evolution.

In another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

Expected response:
`{"status":"ok","service":"ml-studio-api","database":"ready"}`.
The endpoint checks SQLite with a trivial query. A query failure returns a
sanitized HTTP 503, not internal paths or stack traces. Health proves database
connectivity, not migration currency; use Alembic's current command for that.
OpenAPI uses the package's `0.0.0` development metadata, not a published release.

From `frontend/`:

```powershell
npm.cmd ci
npm.cmd run dev
```

Open `http://127.0.0.1:3000`. Checking changes to Connected only after a valid
live API/database response. Network failure, invalid responses, or a five-second
timeout show Unavailable. Check again retries. The page remains usable with the
backend stopped. `npm.cmd` avoids PowerShell systems that block `npm.ps1`; no
execution-policy change is needed.

The [frontend example](../frontend/.env.example) documents public
`NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://127.0.0.1:8000/api/v1`.
It includes the API prefix and is embedded at build time. Restart development or
rebuild production after changes. The browser calls FastAPI directly; CORS must
allow the frontend origin.

## Central configuration and runtime workspace

| Setting | Default / behavior |
| --- | --- |
| `MLSTUDIO_APP_NAME` | `ML Studio` |
| `MLSTUDIO_ENVIRONMENT` | `development`; also accepts `production` and `test` |
| `MLSTUDIO_API_PREFIX` | `/api/v1`; update the frontend URL if changed |
| `MLSTUDIO_HOME` | ML Studio's platform user-data directory, via platformdirs |
| `MLSTUDIO_DATABASE_URL` | Optional absolute SQLite file URL; otherwise `mlstudio.db` under the workspace |
| `MLSTUDIO_CORS_ORIGINS` | JSON array of `http://localhost:3000` and `http://127.0.0.1:3000`; no credentials or wildcard defaults |

The default runtime workspace is outside the repository. Windows normally uses
local application data; other systems follow platformdirs conventions. Resolving
settings or importing the application creates no files. Lifespan or Alembic
initialization creates required directories. For disposable validation, this
override was verified before running migrations and starting the backend:

```powershell
$env:MLSTUDIO_HOME = Join-Path ([System.IO.Path]::GetTempPath()) ('mlstudio-phase0-' + [guid]::NewGuid().ToString())
```

Keep custom workspaces outside the repository. An explicit database URL takes
precedence over the default database and must name an absolute synchronous SQLite
file. Tests clear ambient ML Studio settings and use temporary directories rather
than the developer's real workspace or local `.env`.

Ignore rules protect environments, Python caches, Node modules, Next output,
SQLite files, logs, and local artifacts. Example environments and synthetic CSV
fixtures remain eligible for version control.

## Verified checks

From `backend/`:

```powershell
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m pytest
```

Tests cover health, actual SQLite queries, workspace isolation, migrations,
explicit CORS, invalid configuration, and sanitized database failures. The tested
Starlette release emits an upstream deprecation warning for its supported httpx
TestClient adapter; tests pass.

From `frontend/`:

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

Next.js 16.3.8 and React 19.3.0 were resolved from npm's stable releases.
TypeScript 6.0.3 is pinned because Next's typescript-eslint parser rejects 7.0.
ESLint 9.39.5 is pinned because Next's React lint plugin fails with ESLint 10.11.0.
npm labels ESLint 9 deprecated; revisit these tooling pins when upstream support
lands. No lint rules are disabled to hide these failures. Next build does not
run lint, so all three commands are required.

Run `git diff --check` and inspect `git status` before committing. Phase 0 adds
no CI, ML dependencies, or ML tests. Setup commands must stay backed by actual
verification; do not document aspirational commands as working instructions.

## Manual GitHub setup

The workspace began without a remote. Publish it to the chosen owner/repository
through the maintainer's normal process; no remote is assumed by this guide.

Before inviting public reports and contributions, maintainers should:

- Enable Private Vulnerability Reporting and verify the private report action;
  update [SECURITY.md](../SECURITY.md) if a verified private contact is added.
- Establish a private conduct-reporting channel and replace the explicit pending
  channel notice in [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md).
- Configure default-branch protection or a ruleset appropriate to the team;
  require review where feasible and require checks only when real checks exist.
- Review repository security settings, including available secret scanning and
  push protection. Enable dependency alerts when a dependency graph exists.
- Set a repository description, for example “Visual ML. Real code. Reproducible
  experiments.” Consider topics such as `machine-learning`, `local-first`,
  `tabular-data`, and `reproducibility`.
- Verify Issue Forms and the PR template render correctly on GitHub.
- Optionally enable Discussions for open-ended conversation and a Project board
  for milestones; neither is necessary to contribute.

No CODEOWNERS is supplied because ownership is not established. No Dependabot
configuration is supplied in Phase 0.
These settings are not activated by documentation and remain manual work.
