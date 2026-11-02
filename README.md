# ML Studio

A local-first, visual machine learning workbench for building, understanding, and running real Python pipelines.

Configure an experiment visually, inspect its Python, execute that exact source locally, and return to frozen results later. ML Studio connects an approachable workflow with inspectable code instead of hiding the experiment lifecycle.

**Release candidate: v0.4.0-beta.1.** This repository prepares the first public beta; it does not imply a tag, binary, or GitHub Release has been published.

## Current capabilities

- Persistent Projects with binary classification, multiclass classification, or regression tasks.
- Managed CSV sources, physical and semantic column types, target selection, source exploration and preparation controls.
- Logistic Regression, Decision Tree and Random Forest classifiers; Linear Regression and Ridge regressors.
- Deterministic Python, local training, immutable Run evidence, task-specific evaluation and guarded two-Run comparison.
- Workspace-wide **Show Code**: a read-only Live Python Viewer that docks or floats, plus an explicit transition to full-screen Code Mode with drafts, snapshots and opt-in Code Runs.
- Local SQLite/filesystem persistence and secondary local MLflow tracking.
- A Rust CLI that installs and supervises the existing FastAPI backend and production Next.js frontend as **two independent servers**.

## Quick start

Source installation requires Git, Python >=3.12, Node.js >=22.13.0 with npm, and Rust/Cargo for CLI bootstrap. Keep the checkout after installation.

```powershell
# Windows PowerShell, from the cloned repository
.\scripts\bootstrap-cli.ps1 -FromSource
# Use the printed executable path, or add its bin directory to PATH.
mls install
mls start
```

```sh
# macOS / Linux, from the cloned repository
sh scripts/bootstrap-cli.sh --source
export PATH="$HOME/.local/bin:$PATH"
mls install
mls start
```

Open http://127.0.0.1:3000. Ctrl+C in the launcher terminal stops both servers. See [Installation](docs/installation.md) for prerequisites, PATH, backups and platform limits. No npm, Homebrew, winget or prebuilt-release distribution is assumed.

## First experiment

**Data / Explore / Prepare / Train / Evaluate**, with history in **Runs** and Python available through **Show Code** throughout the workspace.

Follow [Getting started](docs/getting-started.md) using the committed synthetic CSV. Code Mode is an optional explicit fork: arbitrary Python edits never update the preserved visual pipeline automatically.

## Documentation

- [Documentation index](docs/README.md) / [Installation](docs/installation.md) / [Getting started](docs/getting-started.md)
- [Projects and data](docs/user-guide/projects-and-data.md) / [Explore and Prepare](docs/user-guide/explore-and-prepare.md) / [Training](docs/user-guide/training.md)
- [Runs and evaluation](docs/user-guide/runs-and-evaluation.md) / [Code workspace](docs/user-guide/code-workspace.md)
- [CLI](docs/cli.md) / [Troubleshooting](docs/troubleshooting.md)
- [Architecture](docs/architecture.md) / [Development](docs/development.md) / [Beta readiness evidence](docs/development/beta-release-readiness.md)
- [Vision](VISION.md) / [Roadmap](ROADMAP.md) / [Changelog](CHANGELOG.md)

## Technology and beta boundaries

Next.js/React/TypeScript and Monaco; Python/FastAPI, pandas, scikit-learn, SQLAlchemy/SQLite, Alembic and MLflow; Rust for installation and supervision only.

This is a trusted single-user local tool, **not a production inference service or secure Python sandbox**. Keep both servers on loopback. There is no authentication or multi-user isolation. Edited Python execution is disabled by default. CSV uploads default to 50 MiB; memory usage can be much higher. Back up SQLite and managed files together before upgrades.

No ROC curves, prediction-level plots, threshold tuning, AutoML, AI assistant, cloud execution or deployment is included. Interfaces and compatibility may change during beta. Windows has local validation; macOS/Linux CI configuration alone does not prove platform acceptance. Consult the readiness report for current evidence.

## Contribute

See [Contributing](CONTRIBUTING.md), [Code of Conduct](CODE_OF_CONDUCT.md), and [Security](SECURITY.md). Use synthetic data in public reports. Licensed under [Apache License 2.0](LICENSE).
