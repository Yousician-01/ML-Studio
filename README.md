# ML Studio

**Visual ML. Real code. Reproducible experiments.**

ML Studio is an early-stage, open-source project for a local-first visual workspace
for building, understanding, and experimenting with machine-learning systems while
keeping access to the underlying Python.

Building a baseline in a notebook often means assembling data inspection,
preprocessing, evaluation, and tracking yourself. ML Studio aims to make that
workflow easier to understand and reproduce. It is not intended to become another
opaque AutoML button.

## Status

**Available now:** product scope, proposed architecture, an initial architectural
decision, and contribution guidelines. There is no runnable application yet.

**Planned:** a CSV-to-baseline workflow for tabular classification and regression,
with visual configuration, MLflow tracking, basic Run comparison, and readable
generated Python. See the authoritative [prototype scope](docs/prototype.md).

The next step is **Prototype Specification v0.1 and Pipeline IR v0.1 design**,
before application implementation. No releases or delivery dates are announced.

## What we are validating

Can an unfamiliar tabular dataset become a correct, reproducible baseline ML
Experiment more easily and understandably than with a manually assembled notebook?

The planned workflow moves through specialized **Benches**:

```text
Create Project → Data → Explore → Feature Engineering → Train → Evaluate → Compare Experiments
```

Users would describe the problem, upload a CSV, inspect its schema, choose a target,
configure preprocessing and a model, train, evaluate, compare Runs, and inspect
generated Python.

## Principles

- Visual-first, never visual-only: progress from **Visual → Inspect → Extend**.
- Reproducibility: transformations belong to explicit Pipeline state.
- ML correctness: prevent or explain leakage and other common mistakes.
- AI advises; deterministic systems execute. Recommendations require user action.
- Local-first: keep datasets on infrastructure you control.
- Integrate mature OSS rather than rebuild ML infrastructure.

Python extension points are a later consideration. Arbitrary visual ↔ Python
synchronization is outside prototype scope.

## Learn more and contribute

- [Vision](VISION.md) — why this project exists
- [Roadmap](ROADMAP.md) — milestones and open work
- [Prototype](docs/prototype.md) — intended scope and success criteria
- [Architecture](docs/architecture.md) and [decisions](docs/decisions/README.md)
- [Development](docs/development.md) and [contributing](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md), [security](SECURITY.md), and [changelog](CHANGELOG.md)

Screenshots and a demo will be added when a working workflow exists.
Installation instructions will live in the development guide once validated.

## License

ML Studio is licensed under the [Apache License 2.0](LICENSE).
The Code of Conduct includes its own standard attribution.
