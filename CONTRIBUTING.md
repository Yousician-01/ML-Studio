# Contributing to ML Studio

ML Studio's Prototype v0.1 specifications are complete and implementation is
under active development. Read the [prototype](docs/prototype.md), current
[architecture](docs/architecture.md), and authoritative
[v0.1 specifications](docs/specifications/project-v0.1.md) before proposing
behavior changes. Keep work focused on the frozen binary-classification scope.

## Discuss a problem first

Search existing GitHub Issues and PRs. Use the feature form to explain who has a
problem, why it matters, and an example workflow before proposing a solution.
Use the bug form for reproducible problems, including documentation defects.
Small typo fixes can go straight to a PR; discuss substantial changes first.
Discussions may be used if maintainers enable them, but are not required.

Never attach confidential datasets, credentials, API keys, personal information,
or other sensitive data. Prefer a small synthetic example. Report vulnerabilities
privately according to [SECURITY.md](SECURITY.md), not in public Issues.
Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Contribution workflow

1. Agree on the problem and scope in an Issue when appropriate.
2. Fork the repository if needed and create a descriptive branch such as
   `docs/pipeline-semantics` or `fix/schema-validation`.
3. Make a focused change. Keep unrelated cleanup separate.
4. Validate the change and update affected documentation.
5. Open a PR explaining what changed, why, how, and what was checked; link the Issue.
6. Address review feedback before a maintainer merges.

Use Conventional Commit-style messages, for example:

```text
feat(data): add CSV profiling
feat(train): add random forest configuration
fix(pipeline): prevent preprocessing leakage
docs(architecture): document pipeline execution
test(profiling): add semantic inference cases
refactor(executor): separate preprocessing execution
```

These illustrate commit-message formatting, not proposed changes to v0.1 scope.

## Validation and documentation

For documentation changes, check relative links, consistency of scope, Markdown
rendering, and Issue Form YAML. Report checks actually performed using the
[verified development commands](docs/development.md). Include tests appropriate to
behavior changes, especially leakage prevention, validation, reproducibility,
and proof that the exact persisted generated Python is executed. Preserve the
complete fitted pipeline and immutable historical Run contracts. Explain
untested cases honestly.

Pull requests targeting `main` run [Contributor CI](.github/workflows/ci.yml).
The exact required status-check names are **Frontend checks** and **Backend checks**.
Both must pass before merge; a maintainer must configure that requirement in
GitHub branch protection or a ruleset. The frontend job runs dependency installation,
tests, typecheck, lint, production build, and a whitespace check of the PR diff.
The backend job installs development dependencies, runs pytest and Ruff lint/format
checks, checks dependency consistency, and builds a wheel with Hatchling via pip.
CI uses GitHub-hosted runners, read-only permissions, no repository secrets, and
no persisted checkout credentials. See the [development guide](docs/development.md#contributor-ci)
for runtime versions and maintainer setup. Local Git hooks are not required.

Update the authoritative document rather than duplicating its contents. Add an
[ADR](docs/decisions/README.md) for significant architectural/product decisions.
Use the [changelog](CHANGELOG.md) for user-visible changes, PRs for implementation
discussion, and Git history for exact edits. Do not maintain daily diaries.

The [development guide](docs/development.md) owns setup instructions and
test commands. Contributions to project material are under the
[Apache License 2.0](LICENSE); preserve third-party notices and attribution.
