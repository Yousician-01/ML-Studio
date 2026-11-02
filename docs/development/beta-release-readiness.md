# v0.4.0-beta.1 release readiness

## Release identity

- Target: **v0.4.0-beta.1**, prepared, not published.
- Branch: `release/v0.4.0-beta.1`.
- Audited implementation commit: `f853718fff9130f35da52bf9ea7338335a9a5cfb`.
- Evaluation: **2026-11-03 (Asia/Calcutta)**; commands span the preceding UTC evening.
- This report accompanies uncommitted documentation changes above that commit.
  No commit, push, merge, tag, binary publication or GitHub Release was performed.
- Recommendation: **NOT READY - BLOCKERS REMAIN** for public release publication.
  No new functional defect was found by the passing gates. Outstanding maintainer
  reporting-channel and acceptance gates are listed below; this is not a request
  for an architectural rewrite or new product features.

## Implemented feature verification

Static inspection covered routes/services, persistence, compiler/result protocols,
frontend workspace/provider and tests, CLI/bootstrap, migrations and workflows.
Fresh test results and the narrower real-server exercise are distinguished below.

| Capability | Implementation and evidence |
| --- | --- |
| Projects and managed CSV | Persistent fixed-task Projects, immutable SHA-256 sources, validation, semantics/roles/target, explicit replacement and deletion guards; backend tests |
| Tasks/models | Binary and multiclass with Logistic Regression/Decision Tree/Random Forest; regression with Linear Regression/Ridge; versioned dispatch/tests |
| Explore/Prepare | Source profiles/visualizations, bounded regression relationships, explicit compatible preparation; training-only fitting |
| Train and reproducibility | Reviewed revision/plan/source admission, exact persisted Python execution, frozen results/model/provenance; backend tests plus one real binary Run |
| Runs/Evaluate | Immutable task-specific metrics, typed matrices, historical Code, integrity warnings, exactly-two compatible-context deltas; frontend/backend tests |
| Live Python Viewer | Shared read-only dock/floating viewer, guarded proposed Train previews without save/draft/execute side effects; frontend tests/static inspection |
| Code Mode | Explicit fork, persistent draft/baseline/origin, snapshots, archived resume copy, visual-write guards and default-off Code Runs/reporting; existing tests |
| CLI | Installer/supervisor of two real independent servers, checked ownership/logs/backups; six tests, build and temporary Windows artifact-bootstrap verification. Full managed lifecycle blocked locally, not claimed passed |
| MLflow | Secondary local tracking after core finalization; existing tests. Integration smoke verified core Run evidence, not a separate fresh MLflow UI inspection |
| Storage/migrations | SQLite/files authoritative; Alembic head 0009_multiclass; migration tests and disposable real fresh upgrade |

## Documentation status

Created a public index, OS-specific installation guide, practical synthetic tutorial,
five focused user guides and troubleshooting. Updated README, Vision, Roadmap,
Changelog, contributor/security policy, architecture/development/CLI references and
both existing examples. Preserved frozen specifications, ADRs, historical audits
and phase records; nothing was relocated or removed.

Public/CLI identity is 0.4.0-beta.1. Frontend/backend package metadata remains 0.2.0,
consistent with the existing independent-version convention in the CLI reference.
IR/compiler/result versions retain their historical meaning. No manifest, lockfile,
implementation, dependency, schema or API change is part of this release-doc pass.

## Validation matrix

Frontend commands ran from `frontend/`; backend commands used
`backend/.venv/Scripts/python.exe` and ran from `backend/`. CLI commands ran from
the repository root. Results below are fresh for this working tree, not copied
from earlier phase reports.

| Area | Command / method | Result | Notes |
| --- | --- | --- | --- |
| Frontend tests | `npm.cmd run test` | PASS | 68 tests, zero failures |
| Frontend types | `npm.cmd run typecheck` | PASS | Next typegen and tsc |
| Frontend lint | `npm.cmd run lint` | PASS | ESLint |
| Frontend production | `npm.cmd run build` | PASS | Next 16.4.1 production build |
| Lockfile install, live checkout | `npm.cmd ci` | BLOCKED | Windows EPERM unlinking loaded next-swc native binary; existing Node processes left running |
| Lockfile install, disposable copy | `npm.cmd ci` | PASS | Same package.json/package-lock.json and prepare-editor script, 354 packages installed; postinstall passed; missing ignored checkout dependencies restored without replacing live locked files |
| Local dependency recovery | `npm.cmd ls --depth=0`, `npm.cmd run prepare-editor` | PASS (bounded) | Direct dependencies resolve; two extraneous optional platform-package remnants were retained. Clean disposable npm ci is the lockfile-install evidence |
| Backend tests | `python -m pytest -q` | PASS | 719 tests, 553 warnings, 373.18 seconds |
| Backend lint | `python -m ruff check .` | PASS | No findings |
| Backend format | `python -m ruff format --check .` | PASS | 111 files already formatted |
| Python consistency | `python -m pip check` | PASS | No broken requirements |
| Backend packaging | `python -m pip wheel --no-deps --wheel-dir <temporary-directory> .` | PASS | Isolated Hatchling build produced mlstudio-0.2.0 wheel outside checkout; not proof of standalone app installation |
| CLI format | `cargo fmt --manifest-path cli/Cargo.toml --check` | PASS | No changes |
| CLI lint | `cargo clippy --manifest-path cli/Cargo.toml --locked --all-targets -- -D warnings` | PASS | No warnings |
| CLI tests | `cargo test --manifest-path cli/Cargo.toml --locked` | PASS | Six passed |
| CLI release | `cargo build --manifest-path cli/Cargo.toml --release --locked` | PASS | Windows x64 compilation |
| CLI identity | `cli/target/release/mls.exe --version`, `--help` | PASS | mls 0.4.0-beta.1 and six expected commands |
| Windows bootstrap | `scripts/bootstrap-cli.ps1 -ArtifactDirectory <temporary-assets> -InstallRoot <temporary-install>` then installed `mls.exe --version` | PASS | Locally built binary and matching SHA256SUMS; no user PATH/install changes; source bootstrap reviewed, not separately installed |
| CLI managed lifecycle | `python cli/smoke.py --binary cli/target/release/mls.exe` | BLOCKED | Existing port 3000 listener; smoke refused before install/start. No unrelated listener stopped |
| Windows real servers | Temporary inline Python HTTP driver, real uvicorn factory on 8019 and production Next start on 3019 | PASS (bounded) | Fresh Alembic head, HTTP readiness, synthetic visual ML workflow and backend restart; not CLI-managed start/abort or browser interaction |
| macOS runtime | Not run | NOT TESTED | Apple Silicon/Intel CI configured, results not verified here |
| Linux runtime | Not run | NOT TESTED | GNU x64 Ubuntu CI configured, results not verified here |
| Browser acceptance | User's prior explicit Unified Code Workspace approval | USER-REPORTED | No fresh automated visual/accessibility/browser acceptance in this pass |
| Production npm audit | `npm.cmd audit --omit=dev --json` | PASS | Zero vulnerabilities at query time |
| Full npm audit | `npm.cmd audit --json` | FINDINGS | 14 moderate, zero low/high/critical; development tooling retained, no forced upgrade |
| Python vulnerability audit | `python -m pip_audit --version` | NOT RUN | Module unavailable; pip check is not a vulnerability audit |
| Rust vulnerability audit | `cargo audit --version` | NOT RUN | cargo-audit unavailable; no claim of clean Rust advisories |
| Repository hygiene | Tracked-path/size and obvious credential-pattern scan | PASS (bounded) | No tracked runtime DB/env/build/dependency files, files >5 MiB, or obvious private-key/GitHub/AWS token matches; not exhaustive secret certification |
| Relative documentation links | Inline Python scan of repository Markdown link/reference targets and heading fragments | PASS | 54 Markdown files, 239 relative links, zero unresolved targets/fragments; external URLs not exhaustively checked |
| Whitespace / scope | `git diff --check`, `git status --short`, complete changed-file review | PASS | Documentation-only intended diff; generated next-env declaration restored |

Warnings were not suppressed. Existing warnings include Starlette/httpx test-client
deprecation, sklearn penalty deprecation and joblib/NumPy compatibility notices.
ESLint 9 deprecation and the 14 moderate npm development findings need future
upstream/tooling review, not blind major upgrades in this release pass.

## Real integration method and limits

A temporary driver (not added to the repository) checked unused ports 8019/3019,
set explicit temporary `MLSTUDIO_HOME` **and** `MLSTUDIO_DATABASE_URL`, disabled
manual Code execution and used the existing backend venv. It ran:

```text
python -m alembic upgrade head
python -m uvicorn mlstudio.main:create_app --factory --host 127.0.0.1 --port 8019
node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3019
```

HTTP steps: readiness for both actual servers; POST Project; multipart CSV upload
(40 synthetic age/label rows); target PATCH; pipeline GET/PATCH with explicit typed
positive class, Logistic Regression and default split; code GET; revision/hash-bound
Run POST; terminal GET polling; assert SUCCEEDED, exact historical code equality
and managed source-byte equality. Restart the owned backend, then assert the same
Project, frozen Run result and historical source. Finally terminate/wait only the
owned process handles. No existing user database or listener was changed.

The temporary frontend HTML was served successfully. Its build-time API URL was
not changed, so this was **not** a browser-driven UI flow against the temporary API.
The driver used direct HTTP for mutations. Evidence lives outside the repository
in an OS temporary directory; it is synthetic and is not release content.

The standard CLI smoke was attempted and blocked by port occupancy. It did not
complete install/doctor/start/status/logs/abort in this pass. A clean-host rerun is
required; passing compile/unit/bootstrap checks are not substituted for it.

## Release blockers and required maintainer actions

1. **Private community reporting is incomplete.** CODE_OF_CONDUCT explicitly says
   no private conduct contact is established, and SECURITY cannot verify Private
   Vulnerability Reporting. Establish a private conduct channel and verify GitHub
   private vulnerability reporting before inviting public participation. No email,
   response SLA or enabled setting has been invented in documentation.
2. **Finish clean-host installer acceptance.** Stop the appropriate services yourself
   or use a clean host, then run the standard CLI smoke and the install/start/status/
   logs/abort/restart checklist. Current Windows evidence is partial for managed
   installation, and other platform runtime acceptance is unverified locally.
3. **Verify remote release-commit CI/settings.** Repository files cannot establish
   passing remote runs or branch rules. Require `Frontend checks` and `Backend checks`,
   PR review and an up-to-date branch in GitHub; review the four platform CLI jobs.
   Confirm whether CLI path filters require manual workflow dispatch for this
   documentation-only release PR. No settings were weakened or changed.

No confirmed new code blocker or frozen-contract mutation was found. If publishing
only a Windows beta, explicitly keep non-Windows runtime status experimental until
its actual acceptance evidence is available; do not infer it from matrix entries.

## Documented non-blocking limits

- Trusted local single user, loopback only; no authentication or secure sandbox.
- Python/Node externally supplied; source checkout required, no assumed package
  registry/prebuilt release distribution. Python dependency ranges are not a
  cross-platform reproducible environment lock.
- No hard memory quota, continuous backup, automatic artifact GC or secure erasure.
  MLflow copies may remain after deletion; uncertain recovery fails closed.
- Process-tree cleanup is not containment of hostile/detached descendants, with
  platform-specific supervisor-death limits described in the CLI reference.
- No per-sample prediction artifacts/ROC curves/residual plots, threshold tuning,
  AutoML, AI, deployment or extra models beyond the current catalogue.
- Moderate development advisories and unavailable Python/Rust security tooling are
  disclosed; clean production npm audit is not a system-wide security guarantee.

## Final maintainer acceptance checklist

- [ ] Review installation commands on the intended release platforms and confirm
  exact remote CI outcomes for the final release commit.
- [ ] On a clean/disposable host, bootstrap, install twice, doctor, start, status,
  logs/follow, abort, restart and Ctrl+C; verify both ports close and unrelated
  listeners/PIDs are never terminated.
- [ ] Back up and rehearse an existing-workspace upgrade with all writers stopped.
- [ ] Follow Getting started in the browser; check loading/errors, preparation,
  Run result/history, integrity warnings, comparison and persistence after restart.
- [ ] Spot-check binary, regression and multiclass workflows, including old history.
- [ ] Recheck Show Code dock/float, unsaved Train validation, Edit Code cancel/confirm,
  archived resume and guarded visual return; opt into Code Runs only deliberately.
- [ ] Enable/verify private security reporting and publish a private conduct contact.
- [ ] Review package/license notices and any candidate binaries/checksums before
  separately authorizing tag/release publication.

**Recommendation: NOT READY - BLOCKERS REMAIN.** Documentation and fresh local
functional gates are complete; public community/reporting and installer/platform
acceptance gates require maintainer closure. Nothing has been published.
