# Unified live Python and full-screen Code Mode

Code is a companion to the Project workspace rather than a sidebar workflow bench.
The persistent **Show Code** toolbar button opens or closes the read-only viewer
without navigating away from the current bench. Current-Code actions in Train and
Runs also open this viewer; historical Run source remains separate frozen evidence.
Legacy `?view=code` links remain supported.

## State and ownership

Two independent state dimensions are used:

- Editing: visual configuration or full-screen editable Code Mode.
- Viewer presentation: closed, docked, or floating.

Opening, closing, dragging, resizing, docking, or floating the viewer does not enter
Code Mode, save the Pipeline, create a draft, or execute Python. Viewer presentation
and dock width are lightweight per-Project localStorage preferences; they are not
authoritative experiment state. Project-keyed providers isolate requests and source
when switching Projects.

SQLite remains authoritative for the saved visual Pipeline. Prepare continues to
save explicit changes through its existing API. Train retains its existing temporary
parameter/split input and publishes parsed proposed IR for preview. Invalid raw input
invalidates the displayed preview. Merely viewing Python never saves those inputs.

## Live generation

The viewer uses the existing backend validator, effective-plan resolver, and Python
generator. There is no frontend Python generator or new training implementation.

- `GET /api/v1/projects/{project_id}/code` retains its saved-Pipeline behavior.
- `POST /api/v1/projects/{project_id}/code/preview` accepts the existing
  `PipelineUpdate` shape: `{revision, ir}`. It validates proposed IR against the
  current Project/Dataset and returns the existing `CodePreview` response without
  writing the Project, creating drafts, or creating Runs.
- Draft creation accepts optional `ir` alongside the existing revision/source/plan
  hashes. The server regenerates and checks that exact proposal before admission.
  Its originating IR is copied into the draft; the saved visual recipe stays intact.

Requests use a 350 ms debounce, AbortController cancellation, and request identity
checks. Responses are also checked against Project revision and Dataset identity.
An older response cannot replace a newer request. Invalid or changing configuration
hides executable source and disables Copy/Edit rather than presenting old Python as
current. Retry and focus revalidation retain proposed unsaved intent.

The viewer reuses the local Monaco integration with read-only and DOM-read-only
options, disabled drag/drop editing, and no mutation callback. Selection, search,
scrolling, and copying remain available. Changed-line decorations are temporary
positional comparisons, not a full diff algorithm.

## Presentation

On desktop the viewer docks on the right, initially at 45% width, with a pointer and
keyboard resize separator. Floating mode uses the same mounted viewer/editor, with
pointer dragging, arrow-key movement, native resizing, and a keyboard resize control.
Panel dimensions and position are constrained to the viewport. Smaller layouts use
a full-height drawer instead. Controls reuse existing buttons, icons, colors, and
focus styling; no new editor or window-management dependency is introduced.

## Entering, preserving, and returning

**Edit Code** captures the reviewed preview and requires an explicit confirmation.
When a saved archived draft exists, users can continue that work, start a fresh
draft from the current visual configuration, or cancel. Additional archived sessions
can be inspected and continued through the paginated saved-session history.

Ended Code sessions are immutable. The new endpoint
`POST /api/v1/projects/{project_id}/code-drafts/{draft_id}/resume`, with
`{revision}`, creates a new active session from an archived session's exact saved
source, baseline, and origin. It returns 201 with a new draft ID. It does not change
the archived row, snapshots, visual Pipeline, or historical Runs. Ownership,
revision, active-session, and active visual-Run guards still apply. No database
migration is needed.

Editable Code Mode fills the application workspace while retaining essential
navigation, draft/save state, existing Run/Stop controls, reporting recovery, output,
and evaluation access. The visual bench remains mounted behind it and its controls
are disabled while a draft is active. Existing recovery-buffer protection remains
available. Code execution still requires the existing explicit opt-in and is not
sandboxed.

**Return to Visual Mode** offers snapshot-and-return, explicit discard, or continued
editing. Snapshot-and-return preserves manual source in an archived session and
snapshot for later continuation; neither is an execution. The originating bench and
its full selection query are restored, including historical Run/comparison IDs.
Unsaved Train input can retain its values across the session when the saved visual
IR is unchanged; a genuinely changed configuration still requires conflict handling.
Manual Python is never parsed back into visual configuration.

Historical Run artifacts, generated-source identity, result protocols, execution
opt-in, and the two independent FastAPI/Next.js servers are unchanged.

## Manual acceptance — pending user verification

1. **Visual-only:** open Show Code from Data, Explore, Prepare, Train, Runs, and
   Evaluate. Confirm no navigation or Code Mode transition, and that closing the
   viewer leaves visual configuration unchanged.
2. **Live generation:** change a supported preparation option and unsaved Train
   parameter/split input. Confirm Python updates without a preview-triggered save,
   draft, or Run. Enter invalid intermediate text and confirm no old executable
   source is presented as current; correct it and retry after an API error.
3. **Layout:** resize the dock; float, drag, keyboard-move/resize, and redock it.
   Check viewport containment, scroll continuity, and the small-screen drawer.
4. **Explicit editing:** cancel Edit Code once, then confirm it. Check the full-screen
   editor, Code Mode warning, disabled visual editing, and draft/save controls.
5. **Independent work:** modify Python, snapshot-and-return, change visual settings,
   and enter again. Verify continue/new/cancel choices preserve the archived source
   and snapshots. New drafts must not overwrite prior sessions.
6. **Return and history:** verify save/snapshot/discard choices, recovery buffers,
   original visual intent, unsaved Train values, and exact Run/Evaluate selection
   when returning. Check existing Code Run output/reporting/evaluation access.
7. **Project isolation:** switch Projects during a preview request and confirm that
   the previous Project's source cannot appear in the new viewer. Check reload and
   keyboard navigation as well as the existing unsaved-code leave warning.

Visual acceptance is intentionally left to the user. This guide describes the
implementation and acceptance scenarios; it does not claim browser verification.
