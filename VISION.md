# Vision

## Problem and product thesis

An unfamiliar dataset demands more than a model choice. People must understand
columns, avoid leakage, choose evaluation methods, and preserve what they tried.
Notebooks offer control, but assembling and maintaining this workflow creates
friction. Visual tools can reduce that friction while hiding important decisions.

ML Studio's thesis is that visual workflows and inspectable Python can reinforce
each other: make routine ML work accessible without making its behavior opaque.
The first audience is learners, analysts, and Python practitioners building
classical tabular baselines. It is not initially a shared production platform.

## Product principles

**Visual-first, never visual-only.** Every meaningful visual operation should have
an understandable representation in a Pipeline. The intended progression is
Visual → Inspect → Extend: configure visually, learn from generated code, and
use explicit Code Mode. The beta implements one-way generation and an explicit
manual-code fork, never arbitrary Python round trips.

**Reproducibility over convenience.** Dataset identity, Pipeline configuration,
seed, and environment should explain a Run. Identical inputs should reproduce
results wherever technically possible; library, hardware, and numerical limits
must be visible. Invisible dataset mutation undermines this contract.

**Correctness by default.** Deterministic checks should make leakage, invalid
splits, unsuitable metrics, and unsupported preprocessing harder to overlook.
Warnings must explain the issue rather than promise that all ML mistakes can be
automatically detected.

**AI advises; deterministic systems execute.** The AI Advisor should be an
Advisor, Critic, and Teacher, grounding recommendations in actual Project facts.
It should explain reasons, evidence, confidence, and alternatives. It must not
silently modify a Pipeline. An experimental Experimenter role is a later idea.

**Local-first.** Users should be able to keep datasets on their own infrastructure.
The source-based CLI now installs and launches the local application. Any external AI provider would require explicit data-sharing
choices; local-first does not imply that remote requests remain local.

**Integrate mature OSS.** The beta uses dataframe tooling, scikit-learn and MLflow rather than custom
equivalents. XGBoost, Optuna and Evidently are possible later
integrations, subject to actual needs.

## Direction, not a delivery commitment

Tabular ML → experimentation → MLOps → NLP/deep learning → LLM experimentation
is a possible evolution. None of the later domains justifies extra prototype
infrastructure today. The [current guides](docs/README.md) define implemented beta behavior;
the [roadmap](ROADMAP.md) records intended sequencing.

Success is a person understanding the project, eventually installing it without
help, completing an Experiment, returning, reporting a useful issue, and perhaps
contributing. Clear docs, working examples when available, and approachable
architecture matter more than GitHub stars.
