# Frontend and workflow audit

Date: 2026-10-24. Static audit of the baseline recorded in
[V0_1_BASELINE_AUDIT.md](V0_1_BASELINE_AUDIT.md). No running-browser evaluation was
performed. Appearance, interaction quality, actual contrast, screen-reader output,
zoom/reflow and responsive behavior are **NOT VERIFIED**. Source affordances below
are evidence of implementation intent, not a visual acceptance certificate.

## Actual composition and state

- Next App Router entry points: `frontend/src/app/page.tsx` and
  `app/projects/[projectId]/page.tsx`. `Workspace` in `components/workspace.tsx`
  maps `?view=data|explore|prepare|train|evaluate|runs|code` to components. Run and
  comparison selection live in URL query parameters. No separate mode switch exists.
- `app/layout.tsx` imports `./globals.css`. CSS defines root tokens, body typography,
  reusable surfaces, buttons, focus indicators and responsive breakpoints. This
  tree's source is a light neutral/indigo system; it is not evidence that another
  branch's redesign was merged or that a previous runtime styling fault persists.
- `components/ui.tsx` supplies Button, Panel, Alert, EmptyState, Loading, Stats and
  native Dialog. Other controls sometimes use raw buttons with local styling.
- `lib/api/projects.ts` owns the fetch boundary; typed contract modules cover
  pipelines/profiles/runs/code/scalars. Fetch has no-store caching, abort handling,
  GET and mutation timeouts, sanitized string errors and structured ApiError status.
- React local state owns loading, drafts, filters and selection. Backend responses
  own persisted state. The localStorage Run request entry recovers transport
  identity; it does not own the Run lifecycle. No Redux/Zustand or chart framework
  is installed or necessary for the present workspace.

## Workflow-by-workflow assessment

| Journey | What works in source | Friction / recommendation |
| --- | --- | --- |
| Find/create Project | `projects.tsx`, `project-form.tsx`: loading/retry/empty state, required problem statement, opening and explicit deletion | All Projects fetched without pagination. Fine for a prototype; measure history scale before adding search infrastructure |
| Ingest source | `data-view.tsx`: file picker, selected name, busy state, explicit replacement confirmation and contextual errors | No byte-progress display. Existing busy state is honest; do not fabricate percentages |
| Interpret columns | Physical/inferred/effective types and overrides; bounded source preview; target distinct-count hints | All columns visible in Data, while Explore/Prepare page them. Wide tables need browser zoom/reflow verification |
| Select target | Data persists one target; Prepare asks explicit typed positive class | Two-surface handoff is semantically sound but requires back-and-forth. Add task-aware prerequisite links and summary, not a compulsory wizard |
| Explore | Full-source profile, filter/search, quality facets, selectable column distributions and correlation | Source scope is correctly labelled. Reset-on-focus remount can lose exploration position; preserving filters/selection by Dataset identity is a useful P2 improvement |
| Prepare | Immediate save for participation/operations, explicit reset with warning, stale/409 lockout, dormant warnings retained | Saving one feature blocks all rows; large recipes take many requests. Batch editing is not required yet; future draft policy must be consistent with Train |
| Train | Curated models, explicit defaults, split/model forms, saved readiness, distinct unsaved state, review links | Save semantics differ from Prepare. Unsaved Train edits are deliberately discarded on navigation; add navigation confirmation before introducing mode switching |
| Execute | `run-experiment.tsx`: saved revision/hashes, occupied/recovery state, uncertain submission recovery, no automatic duplicate attempt | User sees active state rather than fake progress. No cancel control is correct today; long-running adapters need a future cancellation contract |
| Inspect history | Runs list/detail, frozen context, exact historical Code and tracking state; current active source is not needed | Some config is raw JSON; readable parameter summaries should grow from model descriptors rather than repeated hand-written forms |
| Evaluate | Default visibly selects latest successful Run, URL retains ID, paginated history, failed/active/stale/cross-Project handling | Latest search may request multiple history pages and trigger expensive backend integrity work. Optimize only after measurement; preserve honest selection semantics |
| Compare | Exactly two successful distinct owned Runs, values/contexts side by side, warnings and conditional B-minus-A deltas | Secondary button can be available while primary is failed; pure policy rejects comparison. Improve disabled-state explanation rather than weakening policy |
| Code | Read-only generated current preview, copy fallback, revision check and focus refresh; historical source in Runs | No editor, source fork or custom-code revision exists. Presenting this as editable Code Mode would mislead users |

## Findings by category

### Functional correctness and error handling

No newly confirmed release-blocking frontend defect was established. Safeguards
are visible for aborting stale reads, 404/409 errors, loading/empty states and
Run integrity. Tests cover the high-risk comparison policy and result components.

Two limitations deserve focused follow-up rather than a generic rewrite:

1. `api/projects.ts:updateProject` sends no revision token. A settings form opened
   earlier can overwrite newer metadata in a later, non-overlapping request. The
   ORM guard only catches conflicting transactions. This is risk A14, not a claim
   that Pipeline/Dataset writes lack concurrency protection.
2. `RunExperiment.submit` persists request identity before POST and removes it
   after a confirmed response. Browser storage exceptions can therefore surface
   before submission or during reconciliation. UI source handles failure, but
   storage-disabled and quota-exhausted interactive flows are not browser-tested
   here. Keep the pending identity and avoid automatic new POSTs.

### Usability

- **P2 A11:** add a draft-discard guard for Train navigation/mode changes. The UI
  explicitly says navigation discards unsaved input; this is a workflow cost,
  not a silent database loss claim. Tests should prove stay/discard outcomes.
- **P2:** after replacement, the target resets but old recipe remains stale until
  explicit Prepare reset. Data's replacement copy describes configuration reset
  broadly; distinguish target/semantic reset from retained stale recipe in future
  authorized copy work. Never auto-bind the old recipe to new source bytes.
- **P2:** selected target errors should make attempted versus persisted selection
  unmistakable. `DataView` updates its candidate before awaiting validation.
  The visible error is present; whether users understand the retained target is
  unverified. Do not silently accept a third class or clear a good prior target.
- **P2:** strengthen task-aware links and concise readiness summaries before
  expanding the algorithm catalogue. Regression must not show positive-class or
  stratification controls; do not simply disable unexplained binary-only widgets.
- **P3:** remember Explore pagination/filters within a Dataset/revision context;
  never restore a selected index against another Dataset without reconciliation.

### Visual/design and accessibility

There is a meaningful CSS system in source; a cosmetic rewrite is not justified
by this static audit. `globals.css` contains tokens, panels, button variants,
responsive table containers, `:focus-visible` and reduced-motion rules. CSS grows
through many global view selectors, making future changes harder to isolate.
Extract by component when touching that area; do not add Tailwind or a new kit
just to gain another styling vocabulary.

Accessibility affordances are concrete: labelled native inputs, aria-invalid/help
links, status/alert regions, native modal dialog with Escape handling and focus
restoration, current navigation, matrix table row/column orientation and typed
labels. Histograms use focusable SVG bins with Enter/Space handlers; boxplots
provide values/readouts; correlation has keyboard buttons and a table fallback.
These are strengths, but keyboard tab density and screen-reader verbosity need
real evaluation on wide profiles. Native dialog support alone does not establish
complete focus behavior in all target browsers. Do not declare WCAG compliance.

The workspace header/nav and tables have breakpoint rules; actual horizontal
scroll discoverability, 200% zoom, long column names and narrow comparison panels
must be accepted in-browser. This audit neither certifies nor redesigns them.

### Maintainability

- Components such as Train, Prepare and Evaluate mix resource orchestration,
  contextual error routing, editing and markup. Extract common resource/conflict
  behavior only after identifying repeated semantics; maintain per-field context.
- Algorithm names/help/input rendering are embedded in `train.tsx`. Consume the
  proposed capability catalogue rather than growing nested model-type conditions.
- `RunResult` and `FrozenRunContext` assume a binary target and fixed metrics. Add
  discriminated result renderers before enabling regression; never infer task from
  the current Project or hide an old result because the active recipe changed.
- Keep `RunMetrics`, `ConfusionMatrix`, `IntegrityNotice` and `FrozenRunContext`
  shared by Runs/Evaluate. They already avoid a duplicated evaluation presentation.
- API request types and backend Pydantic schemas can drift. Shared descriptor
  fixtures and task-specific contract tests are a smaller first step than a new
  state library or generated-client build system.

### Missing capabilities, deliberately not defects

No node canvas, editable editor, undo history, structured recipe revisions,
task selector, text pipeline, neural training monitor or optional AI exists.
These require approved product/contracts work. A canvas library or Monaco import
does not supply execution semantics, revision lineage or custom-code safety.

## Incremental UX priorities and acceptance

1. In v0.2: task-aware target/metric controls and guard unsaved Train edits.
2. With model expansion: metadata-driven labels/help/defaults with accessible forms.
3. Show a read-only recipe map before enabling arbitrary canvas connections.
4. Introduce visual editing only for operations representable without loss in IR.
5. Introduce editable code as a distinct revision authority, never a misleading
   tab over the same mutable structured configuration.

Minimum future browser acceptance: empty Project -> synthetic upload -> target ->
Prepare -> unsaved Train navigation -> saved execution -> URL deep-linked result ->
two-Run comparison -> corrupt-evidence warning. Repeat with regression after it is
implemented. Exercise keyboard-only dialogs/charts, long labels, 200% zoom and
narrow widths. Preserve existing policy/SSR tests and add only focused interaction
coverage for new high-risk behavior. No browser test stack was added by this audit.
