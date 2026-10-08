"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/projects";
import type { Run, RunCode, RunPage } from "@/lib/api/runs";
import { metricText } from "@/lib/api/evaluation-policy";
import { ConfusionMatrix, FrozenRunContext, IntegrityNotice, RunMetrics } from "./run-results";
import { active } from "@/lib/api/run-policy";
import { pollRuns } from "@/lib/api/run-polling";
import { Alert, Button, EmptyState, Loading, Panel } from "./ui";

export const runHref = (projectId: string, runId: string) => `/projects/${projectId}?view=runs&run=${runId}`;
const date = (value: string | null) => value ? new Date(value).toLocaleString() : "—";

export function RunStatus({ run }: { run: Run }) {
  return <span className={`run-status run-${run.state.toLowerCase()}`}>{run.state === "CREATED" ? "Preparing execution" : run.state === "RUNNING" ? "Running experiment" : run.state === "SUCCEEDED" ? "Succeeded" : "Failed"}</span>;
}

export function RunSummary({ run }: { run: Run }) {
  return <div className="run-summary">
    <div className="section-heading"><div><strong>Run #{run.sequence} · {run.summary.model.name}</strong><p className="muted">Dataset {run.dataset_id} · started {date(run.started_at)}</p></div><span role="status" aria-live="polite"><RunStatus run={run} /></span></div>
    {run.state === "SUCCEEDED" && run.result && <><IntegrityNotice run={run} /><RunMetrics result={run.result} /><Link href={`/projects/${run.project_id}?view=evaluate&run=${run.id}`}>Evaluate this Run</Link></>}
    {run.failure && <Alert><strong>{run.failure.stage} · {run.failure.code}</strong><p>{run.failure.message}</p></Alert>}
    {active(run.state) && <p className="muted">Execution continues if you navigate away or close this browser. No completion percentage is available.</p>}
    <Link href={runHref(run.project_id, run.id)}>Open Run details</Link>
  </div>;
}

export function useRun(projectId: string, runId: string | null, attempt = 0) {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!runId) return;
    return pollRuns(
      signal => api.run(projectId, runId, signal),
      next => { setRun(next); setError(""); },
      next => active(next.state),
      caught => setError(caught instanceof Error ? caught.message : "Run unavailable."),
    );
  }, [projectId, runId, attempt]);
  return { run: run?.id === runId ? run : null, error };
}

export function Runs({ projectId, runId }: { projectId: string; runId: string | null }) {
  return <div className="runs-view">{runId ? <RunDetail key={runId} projectId={projectId} runId={runId} /> : <RunList projectId={projectId} />}</div>;
}

function RunList({ projectId }: { projectId: string }) {
  const [page, setPage] = useState<RunPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    return pollRuns(
      signal => api.runs(projectId, offset, signal),
      next => { setPage(next); setError(""); },
      next => next.items.some(run => active(run.state)),
      caught => setError(caught instanceof Error ? caught.message : "History unavailable."),
    );
  }, [projectId, offset, attempt]);
  function refresh() { setError(""); setPage(null); setAttempt(value => value + 1); }
  return <Panel title="Runs" description="Immutable experiment history · newest first" action={<Button onClick={refresh}>Refresh history</Button>}>
    {error ? <Alert>{error}<Button onClick={refresh}>Retry</Button></Alert> : !page || page.offset !== offset ? <Loading>Loading experiment history…</Loading> : page.items.length === 0 ? <EmptyState title="No Runs yet">Configure a saved experiment in <Link href={`/projects/${projectId}?view=train`}>Train</Link> to create your first historical Run.</EmptyState> : <>
      <div className="table-scroll"><table className="run-ledger"><caption className="sr-only">Historical Runs</caption><thead><tr><th>Run</th><th>Status</th><th>Experiment</th><th>Created</th><th>Accuracy</th><th>Tracking</th></tr></thead><tbody>{page.items.map(run => <tr key={run.id}><th scope="row"><Link href={runHref(projectId, run.id)}>#{run.sequence}</Link></th><td><RunStatus run={run} /></td><td><strong>{run.summary.model.name}</strong><small>Target: {run.summary.target.column}</small><small title={run.dataset_id}>Dataset {run.dataset_id.slice(0, 8)}</small></td><td>{date(run.created_at)}</td><td>{run.state === "SUCCEEDED" && run.result ? metricText(run.result.metrics.accuracy) : "—"}</td><td>{run.tracking_status === "SYNCHRONIZED" ? "Synchronized" : run.tracking_status === "FAILED" ? "Tracking failed" : "Not yet synchronized"}</td></tr>)}</tbody></table></div>
      <div className="actions run-pagination"><Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous</Button><span>{offset + 1}–{Math.min(offset + page.items.length, page.total)} of {page.total}</span><Button disabled={offset + page.items.length >= page.total} onClick={() => setOffset(offset + 20)}>Next</Button></div>
    </>}
  </Panel>;
}

function RunDetail({ projectId, runId }: { projectId: string; runId: string }) {
  const [attempt, setAttempt] = useState(0);
  const { run, error } = useRun(projectId, runId, attempt);
  const [showCode, setShowCode] = useState(false);
  return <>
    <div className="section-heading"><Link href={`/projects/${projectId}?view=runs`}>← All Runs</Link><Button onClick={() => setAttempt(value => value + 1)}>Refresh Run</Button></div>
    {error ? <Alert>{error}</Alert> : !run ? <Loading>Loading frozen Run…</Loading> : <>
      <Panel title={`Run #${run.sequence}`} description="Immutable historical experiment"><RunSummary run={run} /><dl className="run-facts"><div><dt>Run ID</dt><dd>{run.id}</dd></div><div><dt>Created</dt><dd>{date(run.created_at)}</dd></div><div><dt>Started</dt><dd>{date(run.started_at)}</dd></div><div><dt>Completed</dt><dd>{date(run.finished_at)}</dd></div><div><dt>Frozen revision</dt><dd>{run.revision}</dd></div><div><dt>MLflow tracking</dt><dd>{run.tracking_status.replaceAll("_", " ")}</dd></div></dl>{run.tracking_error && <Alert tone="info">{run.tracking_error}</Alert>}{run.mlflow_run_id && <p className="muted wrap">MLflow Run: {run.mlflow_run_id}</p>}</Panel>
      <FrozenRunContext run={run} />
      {run.state === "SUCCEEDED" && run.result && <ConfusionMatrix result={run.result} />}
      <Panel title="Artifacts & provenance"><p className="wrap">Dataset {run.dataset_id}<br /><code>{run.summary.dataset_fingerprint}</code></p><dl className="run-facts">{Object.entries(run.provenance).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl><div className="table-scroll"><table><thead><tr><th>Artifact</th><th>Integrity</th><th>SHA-256</th></tr></thead><tbody>{Object.entries(run.artifacts).map(([name, artifact]) => <tr key={name}><th scope="row">{name}</th><td>{artifact.integrity.replaceAll("_", " ")}</td><td className="run-hash"><code>{artifact.sha256}</code></td></tr>)}</tbody></table></div><Button onClick={() => setShowCode(value => !value)}>{showCode ? "Hide historical Code" : "Inspect historical Code"}</Button></Panel>
      {showCode && <HistoricalCode run={run} />}
    </>}
  </>;
}

function HistoricalCode({ run }: { run: Run }) {
  const [code, setCode] = useState<RunCode | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api.runCode(run.project_id, run.id, controller.signal).then(value => { if (!controller.signal.aborted) setCode(value); }).catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Historical source unavailable."); });
    return () => controller.abort();
  }, [run.id, run.project_id]);
  async function copy() {
    try { await navigator.clipboard.writeText(code!.source); setCopied("Copied exact historical Python source."); }
    catch { setCopied("Clipboard unavailable. Select and copy the source below."); }
  }
  return <Panel title={`Run #${run.sequence} · generated_run.py`} description="Historical Code · immutable · read-only">
    <p>{run.started_at ? "Exact Python source executed for this Run." : "Exact Python source prepared for this attempt; the workload did not start."}</p><p className="muted wrap">{run.provenance.generator} · Run {run.id}</p>
    {error ? <Alert>{error}</Alert> : !code ? <Loading>Reading original source…</Loading> : <><Button onClick={copy}>Copy historical code</Button><p role="status">{copied}</p><p className="wrap"><code>{code.source_sha256}</code></p><pre className="code-source" tabIndex={0} aria-label="Read-only historical Python"><code>{code.source.trimEnd().split("\n").map((line, index) => <span className="code-line" key={index}><span className="code-line-number" aria-hidden="true">{index + 1}</span>{line || " "}{"\n"}</span>)}</code></pre></>}
    <Link href={`/projects/${run.project_id}?view=code`}>Open current Working Pipeline Code</Link>
  </Panel>;
}
