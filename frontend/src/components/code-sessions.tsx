"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/projects";
import type { CodeDraft, CodeSnapshot } from "@/lib/api/code-drafts";
import { Alert, Button, Dialog, Loading, Panel } from "./ui";

export function CodeSessions({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<Pick<CodeDraft, "id" | "status" | "origin_revision" | "created_at" | "updated_at">[] | null>(null);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api.codeSessions(projectId, offset, controller.signal).then(next => { if (!controller.signal.aborted) { setItems(next); setError(""); } }).catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Code sessions unavailable."); });
    return () => controller.abort();
  }, [projectId, offset, attempt]);
  function page(next: number) { setItems(null); setError(""); setOffset(next); }
  return <Panel title="Saved Code sessions" description="Code drafts and snapshots are separate from Runs. Ended sessions can be inspected read-only.">
    {error ? <Alert>{error}<Button onClick={() => setAttempt(v => v + 1)}>Retry</Button></Alert> : !items ? <Loading>Loading saved sessions…</Loading> : !items.length ? <p>No saved Code sessions on this page.</p> : <ul>{items.map(item => <li key={item.id}><Button onClick={() => setSelected(item.id)}>Inspect {item.status} session · visual revision {item.origin_revision} · {new Date(item.created_at).toLocaleString()}</Button></li>)}</ul>}
    <div className="actions"><Button disabled={!items || offset === 0} onClick={() => page(offset - 20)}>Newer sessions</Button><Button disabled={!items || items.length < 20} onClick={() => page(offset + 20)}>Older sessions</Button></div>
    {selected && <SavedSession key={selected} projectId={projectId} draftId={selected} onClose={() => setSelected(null)} />}
  </Panel>;
}

function SavedSession({ projectId, draftId, onClose }: { projectId: string; draftId: string; onClose: () => void }) {
  const [draft, setDraft] = useState<CodeDraft | null>(null);
  const [snapshots, setSnapshots] = useState<Omit<CodeSnapshot, "source">[] | null>(null);
  const [offset, setOffset] = useState(0);
  const [snapshotId, setSnapshotId] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([api.codeDraft(projectId, draftId, controller.signal), api.codeSnapshots(projectId, draftId, offset, controller.signal)]).then(([item, saved]) => { if (!controller.signal.aborted) { setDraft(item); setSnapshots(saved); } }).catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Saved Code unavailable."); });
    return () => controller.abort();
  }, [projectId, draftId, offset]);
  useEffect(() => {
    if (!snapshotId) return;
    const controller = new AbortController();
    api.codeSnapshot(projectId, draftId, snapshotId, controller.signal).then(item => { if (!controller.signal.aborted) setSource(item.source); }).catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Snapshot unavailable."); });
    return () => controller.abort();
  }, [projectId, draftId, snapshotId]);
  return <Dialog title="Saved Code evidence" onClose={onClose}>
    <p>Read-only saved text. This is not an execution or a Run result.</p>
    {error ? <Alert>{error}</Alert> : !draft || !snapshots ? <Loading>Loading saved Code…</Loading> : <>
      <Button onClick={() => { setSnapshotId(null); setSource(null); }}>Session source</Button>
      <ul>{snapshots.map(item => <li key={item.id}><Button disabled={snapshotId === item.id} onClick={() => { setSource(null); setSnapshotId(item.id); }}>Snapshot {new Date(item.created_at).toLocaleString()}</Button></li>)}</ul>
      <div className="actions"><Button disabled={offset === 0} onClick={() => setOffset(v => v - 20)}>Newer snapshots</Button><Button disabled={snapshots.length < 20} onClick={() => setOffset(v => v + 20)}>Older snapshots</Button></div>
      {snapshotId && source === null ? <Loading>Loading snapshot…</Loading> : <pre className="code-source" tabIndex={0} aria-label="Read-only saved Python"><code>{snapshotId ? source : draft.source}</code></pre>}
    </>}
  </Dialog>;
}
