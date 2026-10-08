"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api/projects";
import type { CodePreview } from "@/lib/api/code";
import type { RunRequest } from "@/lib/api/runs";
import { canRun, requestFor, restoredRequest } from "@/lib/api/run-policy";
import { Alert, Button } from "./ui";
import { RunSummary, useRun } from "./runs";

export function RunExperiment({ projectId, revision, ready, dirty, conflict, saving, onReload }: {
  projectId: string; revision: number; ready: boolean; dirty: boolean; conflict: boolean; saving: boolean; onReload: () => void;
}) {
  const [preview, setPreview] = useState<CodePreview | null>(null);
  const [occupied, setOccupied] = useState(true);
  const [busy, setBusy] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [pending, setPending] = useState<RunRequest | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const alive = useRef(true);
  const storageKey = `mlstudio.run-request.${projectId}`;
  const { run, error: runError } = useRun(projectId, runId, attempt);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function capacity() {
      try { const state = await api.capacity(projectId, controller.signal); if (!controller.signal.aborted) setOccupied(state.occupied); }
      catch { if (!controller.signal.aborted) setOccupied(true); }
      if (!controller.signal.aborted) timer = setTimeout(capacity, 3000);
    }
    void capacity();
    let saved: RunRequest | null = null;
    let storageError = "";
    try { saved = restoredRequest(localStorage.getItem(storageKey)); }
    catch { storageError = "Browser storage is unavailable. Request recovery requires local storage."; }
    api.runs(projectId, 0, controller.signal, saved?.request_id).then(page => {
      if (controller.signal.aborted) return;
      setPending(saved);
      if (storageError) setError(storageError);
      if (page.items[0]) {
        setRunId(page.items[0].id);
        if (saved) { localStorage.removeItem(storageKey); setPending(null); }
      }
    }).catch(caught => { if (!controller.signal.aborted) { setPending(saved); setError(caught instanceof Error ? caught.message : "Run history unavailable."); } })
      .finally(() => { if (!controller.signal.aborted) setRestoring(false); });
    return () => { controller.abort(); clearTimeout(timer); };
  }, [projectId, storageKey]);
  useEffect(() => {
    const controller = new AbortController();
    if (!ready || dirty || conflict) return;
    api.code(projectId, controller.signal).then(value => {
      if (!controller.signal.aborted) setPreview(value);
    }).catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Execution preview unavailable."); });
    return () => controller.abort();
  }, [projectId, revision, ready, dirty, conflict, attempt]);
  const reviewed = preview?.ready === true && preview.revision === revision;
  const enabled = canRun({ ready, dirty, conflict: conflict || stale, busy: busy || saving || restoring || Boolean(pending), occupied, reviewed });
  async function submit(recovery = false) {
    if (busy || (!recovery && !enabled)) return;
    setBusy(true); setError("");
    try {
      const payload = recovery && pending ? pending : requestFor(preview!, crypto.randomUUID());
      // Persist transport identity BEFORE POST; browser memory never owns Run state.
      localStorage.setItem(storageKey, JSON.stringify(payload)); setPending(payload);
      const created = await api.createRun(projectId, payload);
      localStorage.removeItem(storageKey);
      if (alive.current) { setPending(null); setStale(false); setRunId(created.id); setAttempt(value => value + 1); }
    } catch (caught) {
      if (!alive.current) return;
      setError(caught instanceof Error ? caught.message : "Submission could not be confirmed. Check the existing request before starting another attempt.");
      if (caught instanceof ApiError && caught.status === 409) {
        setStale(true);
        // Refresh authoritative state without resubmitting or replacing request identity.
        try { const fresh = await api.code(projectId); if (alive.current) setPreview(fresh); } catch { /* Error remains visible. */ }
      }
    } finally { if (alive.current) setBusy(false); }
  }
  async function reviewLatest() {
    if (!pending) { onReload(); return; }
    setBusy(true);
    try {
      const page = await api.runs(projectId, 0, undefined, pending.request_id);
      if (!alive.current) return;
      if (page.items[0]) { localStorage.removeItem(storageKey); setPending(null); setRunId(page.items[0].id); setStale(false); }
      else {
        const current = await api.code(projectId);
        if (!alive.current) return;
        if (current.revision === pending.expected_revision && current.source_sha256 === pending.expected_source_sha256 && current.plan_sha256 === pending.expected_plan_sha256) {
          setError("This submission may still be in progress. Use Check existing submission; its request ID will be reused.");
        } else { localStorage.removeItem(storageKey); setPending(null); setStale(false); onReload(); }
      }
    } catch (caught) { if (alive.current) setError(caught instanceof Error ? caught.message : "Could not reconcile submission."); }
    finally { if (alive.current) setBusy(false); }
  }
  return <div className="run-execution">
    <h3>Execute saved experiment</h3><p className="muted">Create an immutable Run from saved revision {revision}. Configuration is never auto-saved by this action.</p>
    <div className="actions"><Button variant="primary" disabled={!enabled} onClick={() => void submit()}>{busy ? "Confirming submission…" : "Run experiment"}</Button><Link href={`/projects/${projectId}?view=code`}>Inspect current Code</Link></div>
    <p className="muted">{dirty ? "Save local edits before execution." : conflict || stale ? "The experiment changed or capacity is occupied. Review before submitting again." : occupied ? "Execution capacity is occupied or unavailable." : !reviewed ? "Waiting for an executable preview of this saved revision." : `Ready to freeze revision ${revision}.`}</p>
    {error && <Alert>{error}</Alert>}
    {pending && <Alert tone="info">A submission is not yet confirmed. Preserve its identity to avoid duplicate execution.<div className="actions"><Button disabled={busy} onClick={() => void submit(true)}>Check existing submission</Button>{stale && <Button disabled={busy} onClick={() => void reviewLatest()}>Review latest configuration</Button>}</div></Alert>}
    {runError && <Alert>{runError}<Button onClick={() => setAttempt(value => value + 1)}>Refresh Run status</Button></Alert>}
    {run && <RunSummary run={run} />}
  </div>;
}
