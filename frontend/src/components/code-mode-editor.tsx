"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCodeMode } from "./code-mode-state";
import { CodeRunControls } from "./code-execution";
import { CodeReportingRecovery } from "./code-reporting-recovery";
import { Alert, Button, Panel } from "./ui";

const PythonEditor = dynamic(() => import("./python-editor"), { ssr: false, loading: () => <p role="status">Loading Python editor…</p> });
export function CodeModeEditor() {
  const mode = useCodeMode();
  if (!mode.draft) return null;
  return <Panel title="Code Mode" description={`Editable Python · originating visual revision ${mode.draft.origin_revision}`}
    action={<div className="actions"><CodeRunControls /><Button disabled={mode.busy} onClick={() => void mode.reopen()}>Reopen saved draft</Button><Button disabled={mode.busy} onClick={() => void mode.save(true)}>Save code snapshot</Button><Button variant="primary" disabled={mode.busy} onClick={() => void mode.save()}>Save draft</Button></div>}>
    <p role="status">{mode.busy ? "Saving…" : mode.dirty ? "Unsaved changes" : "All changes saved"}{mode.modified ? " · Modified from generated baseline" : " · Matches generated baseline"}</p>
    <Link className="button button-secondary" href={`/projects/${mode.draft.project_id}?view=runs`}>Close editor</Link>
    <Alert tone="info">Visual editing is suspended. Your original recipe is preserved. Python edits do not update it. Run explicitly records and executes a frozen copy when enabled. Saving a draft or snapshot alone does not execute it. Trusted local Python runs with your operating-system privileges, without a sandbox.</Alert>
    <p className="muted">Python text, up to 1 MiB UTF-8. Use the editor’s Undo/Redo commands or Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z. Leaving this workspace preserves saved drafts; save unsaved edits before closing.</p>
    <PythonEditor value={mode.source} readOnly={mode.busy || Boolean(mode.recovery)} onChange={mode.edit} />
    <CodeReportingRecovery />
    <details><summary>Preserved generated baseline</summary><pre className="code-source" tabIndex={0}><code>{mode.draft.baseline_source}</code></pre></details>
  </Panel>;
}
