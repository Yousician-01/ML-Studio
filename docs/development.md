# Development

## Repository status

This is a documentation-only foundation. There are no application dependencies,
runtime, test suite, environment variables, or local launch commands. The next
work is Prototype Specification v0.1 and Pipeline IR v0.1 design, before
implementation. See the [roadmap](../ROADMAP.md).

## Working approach

Use the smallest change that validates the scoped product need. Prefer mature
ML libraries and explicit reproducible state. Keep proposed technology distinct
from accepted decisions; consult [architecture](architecture.md) and
[ADRs](decisions/README.md).

The normal path is **Issue → branch → implementation → tests → PR → merge**.
For the current foundation, implementation means the documentation/configuration
change and tests mean relevant document/form validation. Follow the lightweight
[contribution workflow and commit convention](../CONTRIBUTING.md).

Keep the README approachable, use the prototype document for scope, architecture
for current system direction, ADRs for durable reasoning, Issues for work,
PRs for review, CHANGELOG for user-visible changes, and Git for exact history.
Update documents alongside changes; do not create daily development diaries.

## Local development — to be established

Once implementation begins, this section will own verified prerequisites,
installation, environment configuration, startup, test/lint commands, a small
synthetic example, and troubleshooting. Do not copy aspirational launch commands
into working setup instructions. Add `.env.example` only when real configuration
exists, using dummy values and documenting every variable.

The current `.gitignore` excludes environment secrets and local private data
directories. Future runtime-specific ignores should accompany the chosen tools.
Deliberately contributed synthetic fixtures should live outside those private
directories and be reviewed for privacy and licensing.

## Checks and CI plan

Currently review Markdown rendering and relative links, parse Issue Form YAML,
and check consistency of feature status across the core docs. `git diff --check`
can detect whitespace errors once changes are tracked by Git. No automated CI
is configured in this bootstrap, and no application tests are claimed to pass.

When tooling is selected, add meaningful CI for formatting, linting, type checks,
and tests. ML checks should cover split/preprocessing leakage, invalid Pipeline
handling, seeded repeatability, tracking completeness, and execution/generated
Python parity. Add dependency update configuration when manifests or workflows
exist. Do not introduce speculative dependencies just to populate CI.

## Manual GitHub setup

The workspace started without Git metadata or a remote. Publish it to the chosen
owner/repository through the maintainer's normal process; no remote is assumed.

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
configuration is supplied because there are no dependency manifests or Actions.
These settings are not activated by documentation and remain manual work.
