"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { codeEvaluationHref } from "./code-evaluate";
import { api } from "@/lib/api/projects";
import { codeRunActive, type CodeLogs, type CodeRun, type CodeRunPage } from "@/lib/api/code-runs";
import { useCodeMode } from "./code-mode-state";
import { Alert, Button, Dialog, Loading, Panel } from "./ui";

export function CodeRunControls() {
  const mode = useCodeMode();
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState("");
  const active = codeRunActive(mode.codeRun);
  async function stop() {
    if (!mode.codeRun || stopping) return;
    setStopping(true); setError("");
    try { mode.setCodeRun(await api.cancelCodeRun(mode.codeRun.project_id, mode.codeRun.id)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Cancellation failed; refresh output before retrying."); }
    finally { setStopping(false); }
  }
  return <><Button variant="primary" disabled={!mode.executionEnabled || mode.busy || Boolean(mode.recovery) || active} onClick={() => void mode.runCode()}>Run</Button>
    <Button disabled={!active || stopping} onClick={() => void stop()}>{stopping ? "Stopping…" : "Stop"}</Button>
    {error && <Alert>{error}</Alert>}</>;
}

export function CodeExecution({ projectId }: { projectId: string }) {
  const { codeRun, setCodeRun, setExecutionEnabled } = useCodeMode();
  const liveId = codeRun?.id ?? null;
  const [selection, setSelection] = useState<{ id: string; liveId: string | null } | null>(null);
  const selected = selection && selection.liveId === liveId ? selection.id : null;
  const [page, setPage] = useState<CodeRunPage | null>(null);
  const [detail, setDetail] = useState<CodeRun | null>(null);
  const [output, setOutput] = useState<{ id: string; logs: CodeLogs } | null>(null);
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState("");
  const [showLogs, setShowLogs] = useState(true);
  const [showRun, setShowRun] = useState(false);
  const [now, setNow] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const next = await api.codeRuns(projectId, offset, controller.signal);
        if (controller.signal.aborted) return;
        setPage(next); setExecutionEnabled(next.enabled); setError(""); setNow(Date.now());
        const lifecycle = next.active ?? (liveId ? await api.codeRun(projectId, liveId, controller.signal) : null);
        if (controller.signal.aborted) return;
        if (lifecycle) setCodeRun(lifecycle);
        const id = selected ?? lifecycle?.id ?? next.items[0]?.id;
        if (!id) return;
        const [run, logs] = await Promise.all([api.codeRun(projectId, id, controller.signal), api.codeRunLogs(projectId, id, controller.signal)]);
        if (controller.signal.aborted) return;
        setDetail(run); setOutput({ id, logs });
        if (!lifecycle && !liveId) setCodeRun(run);
        if (codeRunActive(lifecycle) || codeRunActive(run)) timer = setTimeout(() => void load(), 1000);
      } catch (caught) { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Code Run output unavailable."); }
    }
    void load();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [projectId, offset, attempt, liveId, selected, setCodeRun, setExecutionEnabled]);
  const shown = detail && (!(selected ?? liveId) || detail.id === (selected ?? liveId)) ? detail : null;
  const logs = shown && output?.id === shown.id ? output.logs : null;
  const elapsed = shown ? shown.duration_seconds ?? Math.max(0, (now - Date.parse(shown.started_at ?? shown.created_at)) / 1000) : 0;
  return <Panel title="Python execution" description="Managed Code Runs · captured output, not an interactive shell" action={<Button onClick={() => setAttempt(v => v + 1)}>Refresh output</Button>}>
    {error && <Alert>{error}</Alert>}
    {!page ? <Loading>Loading Code execution history…</Loading> : <>
      {!page.enabled && <Alert tone="info">Execution is disabled. For trusted local Python, set MLSTUDIO_CODE_EXECUTION_ENABLED=true and restart the loopback-bound backend. This is not a security sandbox.</Alert>}
      {!shown ? <p>No Code Run selected. Run the active Python draft or select a recorded execution.</p> : <>
        <p role="status" aria-live="polite"><strong>{shown.status}</strong> · {elapsed.toFixed(1)} seconds{shown.exit_code !== null ? ` · exit ${shown.exit_code}` : ""}</p>
        {shown.error && <Alert>{shown.error}</Alert>}
        {shown.source_integrity !== "verified" && <Alert>Recorded source evidence is missing or changed. Retained SQLite source is shown with this integrity warning.</Alert>}
        <div className="actions"><Button onClick={() => setShowLogs(v => !v)}>View logs</Button><Button onClick={() => setShowRun(true)}>View Run</Button><Link href={codeEvaluationHref(projectId, shown.id)}>Evaluate this Code Run</Link></div>
        {showLogs && logs && <div aria-label="Captured execution output">
          {(logs.stdout_truncated || logs.stderr_truncated || logs.stdout_tail_only || logs.stderr_tail_only) && <Alert tone="info">Output is bounded. This panel shows at most the latest 64 KiB per stream; capture limits may omit further bytes.</Alert>}
          <h3>stdout</h3><pre className="code-source" tabIndex={0}>{logs.stdout || "No stdout captured yet."}</pre>
          <h3>stderr</h3><pre className="code-source" tabIndex={0}>{logs.stderr || "No stderr captured yet."}</pre>
        </div>}
      </>}
      <details><summary>Recorded Code Runs ({page.total})</summary>
        <ul>{page.items.map(run => <li key={run.id}><Button onClick={() => { setSelection({ id: run.id, liveId }); setDetail(null); setOutput(null); }}>{run.status} · {run.id.slice(0, 8)} · {new Date(run.created_at).toLocaleString()}</Button></li>)}</ul>
        <div className="actions"><Button disabled={offset === 0} onClick={() => setOffset(v => v - 20)}>Newer Runs</Button><Button disabled={offset + page.items.length >= page.total} onClick={() => setOffset(v => v + 20)}>Older Runs</Button></div>
      </details>
    </>}
    {showRun && shown && <Dialog title="Recorded Code Run" onClose={() => setShowRun(false)}>
      <p>Run {shown.id} · snapshot {shown.snapshot_id} · entrypoint {shown.entrypoint}</p>
      <p className="wrap">Executed source SHA-256: <code>{shown.source_sha256}</code></p>
      <p>Artifact location: <code>{shown.artifact_directory}</code>. No evaluation metrics are inferred from console output.</p>
      <pre className="code-source" tabIndex={0} aria-label="Recorded executed Python"><code>{shown.source}</code></pre>
      <details><summary>Frozen execution configuration</summary><pre className="code-source">{JSON.stringify(shown.configuration, null, 2)}</pre></details>
    </Dialog>}
  </Panel>;
}
