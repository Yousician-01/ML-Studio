# Open-source platform readiness

Date: 2026-10-24. Scope: inspected source tree, local Git evidence and read-only
package metadata. No installation, test suite, dependency vulnerability scan or
GitHub account inspection was performed. See [baseline](V0_1_BASELINE_AUDIT.md).

## Assessment

ML Studio is suitable for source-oriented prototype contributions in its declared
Windows environment. It is not yet a cross-platform packaged application, public
plugin platform or safe executor for untrusted code. These are documented release
boundaries, not reasons to add hosted infrastructure. Contributor safety and the
historical evidence contract are stronger than the breadth of supported ML tasks.

## Readiness inventory

| Area | Already present | Limit / action |
| --- | --- | --- |
| License | Root `LICENSE` is Apache-2.0; contribution terms refer to it | Distribution notice/compliance inventory is not a completed transitive-license audit |
| README | Current workspaces, binary scope, source setup, exact-source execution, tracking, safety and synthetic demo | Do not market wheel-only install, AI or general ML task support |
| Setup | PowerShell venv/editable install, Alembic upgrade, backend loopback, npm ci/dev; `.env.example` in both packages | Fresh installation was not repeated here; exact supported versions versus broad manifest ranges must stay distinct |
| Supported environment | Windows, Python 3.14.2, Node 24.13.0 in docs and CI | macOS/Linux and other versions NOT VERIFIED; portable-looking branches do not prove support |
| Contributor guidance | CONTRIBUTING, code of conduct, issue/PR forms, changelog and development commands | Existing docs contain phase-era drift; report it, do not silently override frozen contracts |
| Tests | pytest unit/domain/API/real-process tests; Node policy/polling/SSR tests; byte goldens | Browser acceptance is not encoded in an automated frontend interaction suite |
| CI | PRs to `main`, Windows frontend/backend jobs, SHA-pinned actions, read-only permissions, no persisted Git write credentials | No push/tag publishing workflow; external run outcomes and required checks unverified |
| Security reports | SECURITY explains trusted-local assumptions and conditional private-reporting instructions | Maintainer must verify a private channel; no invented email or response SLA |
| Data handling | Managed UUID paths, exact SHA, bounded request/source/artifact sizes, safe failures, local tracking | Local access permissions/retention/backup remain user responsibilities |
| API | `/api/v1`, Pydantic boundaries, Project scoping, version/revision guards and OpenAPI | Not a promised stable external SDK; typed result fields are partially generic dicts |
| Extensions | Explicit fixed imports/model constructors; core runs without AI | No plugin protocol/discovery, provider SDK or arbitrary transformer loading |

## Licensing evidence and limits

Read-only installed metadata reports MIT for FastAPI, Pydantic/settings,
SQLAlchemy, Alembic and platformdirs; BSD-3-Clause for Uvicorn, sklearn, joblib
and psutil; pandas includes BSD license text; python-multipart and MLflow carry
Apache licensing metadata. NumPy reports the compound expression
`BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`. These are installed-environment
observations, not proof that every allowed future version has identical metadata.

`frontend/package-lock.json` records MIT for Next/React/ReactDOM/ESLint and
eslint-config-next, and Apache-2.0 for TypeScript. The local wheel's native/bundled
libraries and all transitive packages have not been legally cleared by this audit.
No direct dependency-license blocker was identified from the inspected declarations;
that is narrower than a complete compatibility conclusion. Preserve notices and
review exact redistributed binaries before changing distribution strategy.

Future editor/canvas candidates have their own upstream licensing references:
[React Flow/xyflow license](https://github.com/xyflow/xyflow/blob/main/LICENSE) and
[Monaco license](https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt).
Review the exact chosen package, wrapper and language-service versions at adoption.
Likewise, optional boosting/deep-learning extras need a separate dependency/license
and Python/platform check. No blanket future-extra compatibility is assumed.

## CI, reproducibility and release process

`.github/workflows/ci.yml` contains exact job names **Frontend checks** and
**Backend checks**. Frontend runs `npm ci`, test, typecheck, lint, production build
and `git diff --check HEAD^ HEAD`. Backend uses editable `.[dev]`, pytest,
Ruff lint/format, pip check and a Hatchling wheel through pip. Both use
`windows-latest`, fixed accepted runtime versions and `contents: read`; PR code
receives no configured repository secrets or checkout write credentials. No
`pull_request_target`, Docker or deployment is present.

The previously diagnosed picomatch peer-layout repair is in the committed lockfile;
the scoped `.gitattributes` rule forces LF for `backend/tests/golden/*.py.txt`.
Tests still compare generated bytes directly. The prior validation proved 28
frontend tests and six targeted goldens after that repair; this audit does not
reassert today's npm registry state or GitHub check result.

Frontend pins/lockfile make installs repeatable within platform/package availability
limits. Backend exact sklearn/MLflow pins plus broad remaining ranges are not a full
environment lock. Run provenance detects mismatched environments; it does not
recreate a historical environment or guarantee model compatibility across versions.
Prefer a recorded acceptance constraints snapshot before broadening the dependency
matrix; do not introduce a lock-manager rewrite just for v0.2 regression.

A local `v0.1.0` tag exists and its tree matches the audited HEAD. Git cannot prove
that origin contains the same tag, that it is protected/signed, that a GitHub Release
is published, or that checks passed for its merge. CHANGELOG's statement that no
releases are published may be stale, but a local tag alone does not disprove it.
Keep release verification separate from application correctness.

Minimum manual release checklist for maintainers:

1. Confirm source/tag/commit identity and clean release changes; exclude personal
   next-env churn, stray command-output files and runtime data.
2. Confirm both named CI checks pass and are actually required by a `main` ruleset;
   verify review/force-push policy in GitHub, not by reading CONTRIBUTING.
3. Verify private vulnerability reporting or establish an accurate private channel.
4. Publish source-install support and known limitations with the release; do not
   imply the wheel includes the repository Alembic tree or the frontend application.
5. Preserve tested environment versions, migration instructions and a synthetic demo.

## Security and dependency risks

SECURITY already discloses a development-only `braces` advisory in the ESLint
dependency chain and five historical high-severity npm audit entries. A prior
production-only audit reported zero; **no fresh vulnerability result is claimed
on 2026-10-24**. Advisory state changes, so recheck before a release or pin update
using a narrowly scoped command and primary advisory evidence. Backend dependency
security has not been established merely by `pip check`, which checks requirements
consistency rather than vulnerabilities. No audit-fix command is recommended here.

Current security boundaries to retain:

- Bind to loopback; no authentication or multi-user security boundary exists.
  CORS is not authorization. Exposing the API beyond trusted-local use requires
  a separate threat model, not just a different bind address.
- Generated code executes with local-user privileges. Environment filtering,
  isolated-interpreter flags and timeout are useful protections against accidental
  inheritance/failure, not a sandbox for custom code or models.
- CSV bytes are bounded before spooling and at ingestion. Parsing and fitting can
  expand memory substantially; forest sizes/one-hot vocabulary can still be costly.
- Raw source rows are in managed source/explicit preview, not normal SQLite row
  metadata or generated logs. Column names/class labels and future vocabulary
  inspection can still disclose sensitive information.
- Model joblib is a trusted local executable serialization format. Backend success
  validation does not load arbitrary model bytes; do not add an untrusted model
  upload/load feature under the existing artifact abstraction.
- Replacement retains old Dataset sources. Project deletion removes domain rows
  and managed Project files but can leave local MLflow records. No erasure, backup,
  automatic GC or encryption-at-rest guarantee exists.

## External contributor blockers and priorities

No confirmed P0 contributor blocker was found statically. The minimum next work is:

| Priority | Action | Reason / scope |
| --- | --- | --- |
| P1 before v0.2 task development | Publish the approved version/migration/result design and compatibility acceptance fixtures | Prevent contributors widening v1 unions and rewriting history |
| P2 | Correct architecture/Evaluate status and clearly distinguish existing frozen specs from future proposal docs | Prevent phase-era documentation from guiding incompatible implementations |
| P2 | Verify GitHub required checks and private reporting | Repository recommendations cannot enforce remote settings |
| P2 | Document local npm peer configuration pitfalls and preserved lockfile workflow during future authorized docs maintenance | A machine's permissive peer config can hide a CI install failure |
| P2 | Add macOS/Linux acceptance only if the product intends to support them | File locks, junction checks, launch paths and termination are platform-sensitive |
| P2 | Add task/descriptor API contract fixtures and limited real-browser acceptance for expanded workflows | Existing Node SSR/policy checks do not simulate React effects and interaction |
| P3 | Lightweight versioned extension interfaces after two proven built-in adapters | Avoid freezing an SDK based on hypothetical needs |

## Documentation architecture recommendation

Keep `docs/specifications/*-v0.1.md` frozen. These audit documents should link to
source and approved future contracts, not become substitute normative schemas.
Later authorized work should add versioned task/result/migration decisions and
update architecture/development status once; avoid continuing phase diaries.
The eight-document audit structure is an evidence index and proposal handoff, not
an approval to implement its roadmap. No enterprise services or commercial-only
features are required for a useful open-source platform.
