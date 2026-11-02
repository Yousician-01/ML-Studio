"use client";

import dynamic from "next/dynamic";
import { useCodeMode } from "./code-mode-state";
import { CodeRunControls } from "./code-execution";
import { CodeReportingRecovery } from "./code-reporting-recovery";
import { Alert, Button, Panel } from "./ui";
import { Icon } from "./icons";

const PythonEditor = dynamic(() => import("./python-editor"), { ssr: false, loading: () => <p className="code-status-line" role="status">Loading Python editor…</p> });
export function CodeModeEditor({ onReturn }: { onReturn?: () => void }) {
  const mode = useCodeMode();
  if (!mode.draft) return null;
  return <Panel className="code-mode-panel" title="Code Mode" description={`Editable Python · originating visual revision ${mode.draft.origin_revision}`}
    action={<div className="editor-toolbar"><CodeRunControls /><span className="editor-draft-actions"><Button disabled={mode.busy} onClick={() => void mode.save()}>Save draft</Button><Button disabled={mode.busy} onClick={() => void mode.save(true)}>Save code snapshot</Button><Button disabled={mode.busy} onClick={() => void mode.reopen()}>Reopen saved draft</Button></span></div>}>
    <p className="code-status-line" role="status">{mode.busy ? "Saving…" : mode.dirty ? "Unsaved changes" : "All changes saved"}{mode.modified ? " · Modified from generated baseline" : " · Matches generated baseline"}</p>
    {mode.error && <Alert>{mode.error}</Alert>}
    {mode.notice && <p role="status">{mode.notice}</p>}
    {mode.recovery && <Alert>Recovered text belongs to an earlier draft revision. Copy it before explicitly discarding the recovery buffer.<pre className="code-source" tabIndex={0}>{mode.recovery.source}</pre><Button onClick={mode.dropRecovery}>Use saved state and discard recovered text</Button></Alert>}
    {onReturn && <Button onClick={onReturn}>Return to Visual Mode</Button>}
    <p className="muted">Draft {mode.draft.id}</p>
    <Alert tone="info">You are editing Python directly. Visual pipeline editing is disabled while Code Mode is active. Your original recipe is preserved. Python edits do not update it. Run explicitly records and executes a frozen copy when enabled. Saving a draft or snapshot alone does not execute it. Trusted local Python runs with your operating-system privileges, without a sandbox.</Alert>
    <p className="muted">Python text, up to 1 MiB UTF-8. Use the editor’s Undo/Redo commands or Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z. Leaving this workspace preserves saved drafts; save unsaved edits before closing.</p>
    <div className="editor-frame"><div className="editor-filebar"><Icon name="code" /><span>main.py</span><span className="editor-state">Python · persistent draft</span></div><PythonEditor value={mode.source} readOnly={mode.busy || Boolean(mode.recovery)} onChange={mode.edit} /></div>
    <CodeReportingRecovery />
    <details><summary>Preserved generated baseline</summary><pre className="code-source" tabIndex={0}><code>{mode.draft.baseline_source}</code></pre></details>
  </Panel>;
}
