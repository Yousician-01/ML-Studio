"use client";

import { Alert, Button, Dialog, Panel } from "./ui";

export function CodeModeConfirmation({ busy, error, onConfirm, onClose }: { busy: boolean; error?: string; onConfirm: () => void; onClose: () => void }) {
  return <Dialog title="Enter Code Mode?" busy={busy} onClose={onClose}>
    {error && <Alert>{error}</Alert>}
    <p>The generated Python will become editable. Visual configuration editing will be suspended for this code session.</p>
    <p>Manual Python changes will not update the visual pipeline. Your original visual configuration will remain preserved.</p>
    <p>Returning to visual editing may discard the active manual code draft, only after your explicit choice. Saving a draft or snapshot does not record an execution.</p>
    <div className="actions"><Button onClick={onClose} disabled={busy}>Cancel</Button><Button variant="primary" onClick={onConfirm} disabled={busy}>Enter Code Mode</Button></div>
  </Dialog>;
}

export function VisualReentryWarning({ modified, dirty, busy, onContinue, onSnapshot, onDiscard }: {
  modified: boolean; dirty: boolean; busy: boolean; onContinue: () => void; onSnapshot: () => void; onDiscard: () => void;
}) {
  return <Panel title="Code Mode is active" description="Visual configuration editing is suspended for this session.">
    <Alert tone="info">{dirty ? "Unsaved code edits are present. " : ""}{modified ? "Your Python differs from the generated baseline. " : ""}Choose how to preserve your work before returning to visual editing.</Alert>
    <p>Your original visual configuration is preserved. Python changes are never converted back into the visual pipeline.</p>
    <p>A saved code snapshot is not an execution. Existing immutable Runs’ recorded source and results remain preserved.</p>
    <div className="actions">
      <Button variant="primary" disabled={busy} onClick={onContinue}>Continue editing code</Button>
      <Button disabled={busy} onClick={onSnapshot}>Save code snapshot and return</Button>
      <Button variant="danger" disabled={busy} onClick={onDiscard}>Discard active manual changes and return to Visual Mode</Button>
    </div>
  </Panel>;
}
