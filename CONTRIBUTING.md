# Contributing to ML Studio

ML Studio currently contains repository documentation and design direction, not
an application. Useful contributions now include scope clarification, acceptance
examples, and review of the upcoming Prototype Specification v0.1 and Pipeline
IR v0.1. Read the [prototype](docs/prototype.md) before proposing implementation.

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

These illustrate future changes; they do not imply code exists today.

## Validation and documentation

For current documentation changes, check relative links, consistency of scope,
Markdown rendering, and Issue Form YAML. Report checks actually performed;
there is no application test command yet. Once implementation exists, include
tests appropriate to behavior changes, especially leakage prevention, validation,
reproducibility, and generated-code parity. Explain untested cases honestly.

Update the authoritative document rather than duplicating its contents. Add an
[ADR](docs/decisions/README.md) for significant architectural/product decisions.
Use the [changelog](CHANGELOG.md) for user-visible changes, PRs for implementation
discussion, and Git history for exact edits. Do not maintain daily diaries.

The [development guide](docs/development.md) owns setup instructions and future
test commands. Contributions to project material are under the
[Apache License 2.0](LICENSE); preserve third-party notices and attribution.
