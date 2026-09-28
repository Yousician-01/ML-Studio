# Architecture Decision Records

ADRs preserve significant product and technical decisions and their reasoning.
Use them when changing a durable boundary, representation, dependency strategy,
or execution contract. Routine implementation details belong in Issues and PRs.

Create `NNNN-short-decision-title.md` using the next available four-digit number.
Include: **Title, Status, Date, Context, Options considered, Decision, Rationale,
Tradeoffs, Consequences**. Dates use `YYYY-MM-DD`.

Start proposals as **Proposed**. Review through a PR; mark agreed decisions
**Accepted**, or **Rejected** if declined. When replacing an accepted decision,
write a new ADR and mark the old one **Superseded by ADR NNNN**, linking both.
Preserve original reasoning rather than silently rewriting history. Small
clarifications may be edited with normal Git history.

| ADR | Status | Boundary |
| --- | --- | --- |
| [0001 — Use Pipeline IR](0001-use-pipeline-ir.md) | Accepted | Shared representation; schema not finalized |
