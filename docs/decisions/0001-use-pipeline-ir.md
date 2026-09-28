# ADR 0001: Use Pipeline IR

## Status

Accepted for architectural direction. **The exact Pipeline IR schema is not finalized.**

## Date

2026-09-28

## Context

ML Studio needs visual configuration, deterministic execution, inspectable
Python, reproducible Runs, tracking, comparison, validation, and grounded AI
context. Independent dataset mutations in each Bench would make these views
drift and obscure how a result was produced.

## Options considered

1. Let each Bench own mutable data and execution logic. Simple locally, but
   difficult to reconstruct and inconsistent across consumers.
2. Make arbitrary Python the primary state and infer visual structure from it.
   Flexible, but reliable round trips exceed the prototype's scope.
3. Use a structured Pipeline IR shared by all consumers, with managed Python
   generated from it.

## Decision

Choose option 3. Structured Pipeline state will be the central representation
between the UI, execution, code generation, MLflow tracking, comparison,
reproducibility, deterministic validation, and AI context.

The next design phase will define Pipeline IR v0.1. This ADR accepts no concrete
field names, serialization format, operation registry, or compatibility contract.

## Rationale

One explicit representation makes visual actions inspectable and gives execution
and code generation a common meaning. It supports validation before execution
and records the configuration behind each Run. AI can reason about this state
without becoming the source of execution truth.

## Tradeoffs

The IR introduces design and versioning work and initially limits expressiveness
to supported operations. Consumers can still diverge unless parity is verified.
Custom Python extension semantics will need separate design. Reproducibility
also requires data and environment identity; an IR alone cannot guarantee it.

## Consequences

- Benches must not independently and invisibly mutate datasets.
- Define split semantics, operation ordering, column roles, seeds, dataset
  identity, validation, and evolution before implementing consumers.
- Generate managed Python in one direction; do not promise arbitrary round trips.
- Record Pipeline state with Runs and retain enough context for reconstruction.
- Require explicit user action and deterministic validation for AI suggestions.
- Keep schema examples illustrative until the v0.1 design is reviewed.
