# ML Studio documentation

Public guide to the v0.4.0-beta.1 checkout. Start with installation and a real experiment, then use the references as needed.

| Goal | Read |
| --- | --- |
| Install and launch | [Installation](installation.md), [CLI](cli.md) |
| Complete a first experiment | [Getting started](getting-started.md) |
| Manage sources and targets | [Projects and data](user-guide/projects-and-data.md) |
| Inspect and prepare features | [Explore and Prepare](user-guide/explore-and-prepare.md) |
| Configure and execute models | [Training](user-guide/training.md) |
| Understand immutable results | [Runs and evaluation](user-guide/runs-and-evaluation.md) |
| Inspect or edit Python | [Code workspace](user-guide/code-workspace.md) |
| Resolve setup/runtime errors | [Troubleshooting](troubleshooting.md) |
| Understand or contribute code | [Architecture](architecture.md), [Development](development.md), [Contributing](../CONTRIBUTING.md) |
| Assess this release candidate | [Beta readiness](development/beta-release-readiness.md) |

## Current behavior and historical contracts

The implementation and current guides describe the beta. [ADRs](decisions/README.md) preserve decisions. The frozen [v0.1 specifications](specifications/project-v0.1.md) and [prototype](prototype.md) describe the original binary-classification boundary; they have not been rewritten to pretend later extensions existed then.

Versioned documents linked from [Development](development.md) and reports under `audits/` preserve phase-specific contracts and evidence. Their historical test counts, pending steps and scope statements are not current release acceptance. Follow the current readiness report for fresh validation.

[Vision](../VISION.md) describes direction, [Roadmap](../ROADMAP.md) separates delivered work from ideas, and [Changelog](../CHANGELOG.md) records user-visible changes. A prepared changelog entry is not release publication.
