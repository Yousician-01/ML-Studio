# Repository-based CLI runtime implementation plan

The user brief and explicit two-server constraint are the authority. No commits,
publishing, application-server changes, new ML behavior, or full test suites.

## Verified architecture

Rust installs and supervises the existing Python FastAPI factory and Node Next.js
production server as independent processes. Backend Settings remains authoritative
for workspace, SQLite, MLflow, artifacts, and Code Mode opt-in. Default fixed ports
are 8000/3000; the frontend API URL is baked into its production build.

## Implementation passes

1. Add CLI parsing, checkout discovery, versioned local metadata, runtime checks,
   and a small Python bridge for existing Settings/migration/backup operations.
2. Install into a separate managed venv without replacing backend/.venv; hash build
   inputs, reuse unchanged installations, back up workspace and external SQLite
   databases before pending Alembic upgrades. Never clear or relocate user data.
3. Add foreground supervision, installation/workspace locks, health readiness,
   identity-bearing session records, cooperative abort, crash/partial startup
   cleanup, bounded shutdown, Windows Job containment, and Unix process groups.
4. Add bounded rotating logs and read-only status/doctor diagnostics.
5. Add local-artifact/source bootstrap, build-only cross-platform workflow,
   checksums, CLI guide, and minimal README quickstart changes.
6. Run at most six focused Rust tests, fmt/clippy, one installer production build,
   focused disposable-workspace runtime checks, and git diff --check.

## Decisions and limits

- Rust CLI version is independent of the existing backend/frontend package version.
- CLI records live outside the workspace in the OS user-local data directory.
- Ports remain fixed; no misleading fallback that would break baked API URLs.
- Python/Node are prerequisites, never silently provisioned or PATH-modified.
- Preserve .env; record effective home/database and reject later silent changes.
- abort sends an installation-scoped nonce request to the live supervisor; it never
  kills an arbitrary PID from a file. Stale ownership uncertainty blocks startup.
- Prebuilt artifacts are prepared but not claimed published. Windows is locally
  validated; Unix implementations/build jobs require platform acceptance.

## Implementation review rulings

- Record/check BUILD_ID as well as source inputs; manual builds can change baked
  API configuration without changing sources.
- Retain Unix roots with waitid(WNOWAIT) until group cleanup, so exited roots do
  not lose ownership through PID reuse. Refresh Next argv evidence after readiness
  because its process title changes during initialization.
- Windows uses a small Node signal preload forwarding CTRL_BREAK to the real
  Next server's existing SIGTERM cleanup, never an HTTP/server implementation.
- Include npm build dependencies explicitly even under NODE_ENV=production.
- Keep six focused Rust tests. Disposable runtime and backup checks supplement
  those tests without adding a new end-to-end framework.
