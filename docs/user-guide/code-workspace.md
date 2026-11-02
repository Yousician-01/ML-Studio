# Unified Code Workspace

Inspect the current visual recipe without changing modes, or explicitly fork into manual editing. Neither rewrites historical Runs.

## Live Python Viewer

Use **Show Code** in the toolbar from Data, Explore, Prepare, Train, Runs or Evaluate. There is no separate Code bench in normal navigation. The shared read-only Monaco viewer supports search, selection, scrolling and copying. Dock, resize, float, move or redock it; small screens use a drawer.

It follows visual configuration and supported unsaved Train input. Debounced requests are bound to Project/revision/Dataset identity. Invalid input hides outdated source and shows validation. Previewing does not execute, create a draft or save proposed Train changes. The current recipe is distinct from **Inspect historical Code**, which reads a Run's frozen source.

## Editable Code Mode

Choose **Edit Code** and explicitly confirm the one-way transition. A persistent draft stores generated baseline, current source, origin configuration/revision and timestamps. Arbitrary edits are never reverse-translated into IR. The original visual recipe and historical artifacts remain preserved.

Full-screen editing includes highlighting, line numbers, undo/redo, save and unsaved-change indication. Visual Dataset/Pipeline editing and new visual execution are suspended for the active session. Closing/hiding the editor does not delete the draft. Save before leaving; recovery buffers are a convenience, not authoritative persistence.

A draft save is mutable editing state. A snapshot records source for reference. Neither is execution. Resuming an archived session creates an active copy while preserving archived source/baseline/origin/snapshots. Continue/new/cancel choices protect previous work.

## Code Runs and reporting

Manual execution is disabled by default. Opt in only for trusted code using `MLSTUDIO_CODE_EXECUTION_ENABLED=true` in a real `backend/.env` or backend environment, then restart (rerun `mls install` if installation validation requires it). Editing `.env.example` changes nothing. Keep loopback binding. Peer/Host/Origin checks are safeguards, not authentication or a sandbox.

Run/Stop use separate Code Run records: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED. Submitted source/evidence remain distinct from later draft edits. Completed process exit is not automatically an evaluated model. The explicit reporting API supplies bounded typed classification/regression evidence to Evaluate; generated baselines include reporting integration. Missing/invalid reporting has a reason, not fabricated metrics.

Executed Python has the local user's privileges. No terminal, interactive shell, arbitrary filesystem-browser API or containment guarantee is provided. Do not execute untrusted code or assume cleanup contains intentionally detached descendants.

## Return to visual editing

Return is guarded: continue editing, preserve a snapshot and return, or explicitly discard active manual changes and restore the visual recipe. Snapshots and recorded Code Runs remain distinct historical records; returning does not erase immutable source/results. Python is never parsed back into visual intent.

Return links preserve Run/Evaluate selections. See [implementation details](../development/unified-code-workspace.md) and [Security](../../SECURITY.md).
