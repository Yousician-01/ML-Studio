"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/projects";
import type { CodeEvaluation, CodeLogs, CodeRun, CodeRunPage } from "@/lib/api/code-runs";
import { ConfusionMatrixView, EvaluationMetrics } from "./run-results";
import { Alert, Button, EmptyState, Loading, Panel } from "./ui";

export function codeEvaluationHref(projectId: string, runId?: string) {
  const query = new URLSearchParams({ view: "evaluate", source: "code" });
  if (runId) query.set("code_run", runId);
  return `/projects/${projectId}?${query}`;
}

const unavailable = {
  pending: "Evaluation is not available while this Code Run is active.",
  execution_incomplete: "Execution failed or was cancelled. No completed evaluation is shown; partial logs may be available.",
  not_reported: "Execution completed, but no compatible evaluation was reported. Add mlstudio_runtime reporting calls to your code and run again. Older Code Runs are never rerun or reconstructed.",
  invalid: "Execution completed, but its reporting artifact was invalid, oversized or incompatible with the originating task. No evaluation charts are shown.",
  unavailable_or_corrupt: "Historical reporting or source integrity could not be verified. No evaluation charts are shown.",
};

function SelectedCodeEvaluation({ projectId, runId }: { projectId: string; runId: string }) {
  const [selected, setSelected] = useState<{ run: CodeRun; evidence: CodeEvaluation } | null>(null);
  const [error, setError] = useState("");
  const [logs, setLogs] = useState<CodeLogs | null>(null);
  const [logsError, setLogsError] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([api.codeRun(projectId, runId, controller.signal), api.codeRunEvaluation(projectId, runId, controller.signal)])
      .then(([run, evidence]) => { if (!controller.signal.aborted) { setSelected({ run, evidence }); setError(""); } })
      .catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Code evaluation unavailable."); });
    return () => controller.abort();
  }, [projectId, runId, attempt]);
  async function loadLogs() {
    setLogsLoading(true); setLogsError("");
    try { setLogs(await api.codeRunLogs(projectId, runId)); }
    catch (caught) { setLogsError(caught instanceof Error ? caught.message : "Logs unavailable."); }
    finally { setLogsLoading(false); }
  }
  if (error) return <Alert>Selected Code Run unavailable: {error} Its ID may be stale or belong to another Project. <Button onClick={() => setAttempt(value => value + 1)}>Retry</Button></Alert>;
  if (!selected) return <Loading>Loading immutable Code Run evidence…</Loading>;
  const { run, evidence } = selected;
  if (run.project_id !== projectId) return <Alert>This Code Run does not belong to this Project.</Alert>;
  const report = evidence.status === "available" ? evidence.report : null;
  const result = report?.evaluation;
  return <>
    <Panel title="Code Run evaluation" description="Reported aggregates from the selected immutable Python execution. These are not verified Visual Mode experiments.">
      <p className="wrap">Code Run {run.id} · {new Date(run.created_at).toLocaleString()}</p>
      <p role="status">Execution: {run.status} · Evaluation: {evidence.status.replaceAll("_", " ")}</p>
      {run.error && <Alert>{run.error}</Alert>}
      {evidence.status !== "available" && <Alert tone={evidence.status === "not_reported" || evidence.status === "pending" ? "info" : "error"}>{unavailable[evidence.status]}</Alert>}
      {result ? <EvaluationMetrics task={result.task} values={result.metrics} population={result.population} reason={result.task === "regression" ? result.r2_unavailable_reason : result.roc_auc_unavailable_reason} /> : report && <p>No stock evaluation was reported. Custom outputs are shown below.</p>}
      <p className="muted">Manual Python may change the model, features, data or split. The originating visual configuration does not establish how this code evaluated its data. Code Run comparisons and metric deltas are unavailable.</p>
      <p className="wrap">Source <code>{run.source_sha256}</code> · snapshot {run.snapshot_id}</p>
      <details><summary>Frozen execution context and exact source</summary><pre className="run-json">{JSON.stringify(run.configuration, null, 2)}</pre><pre className="code-source" tabIndex={0}><code>{run.source}</code></pre></details>
      <div className="actions"><Link href={`/projects/${projectId}?view=code`}>Return to Code Mode</Link><Button onClick={() => setAttempt(value => value + 1)}>Refresh selected Code Run</Button><Button disabled={logsLoading} onClick={() => void loadLogs()}>{logsLoading ? "Loading logs…" : "View logs"}</Button></div>
      {logsError && <Alert>{logsError}</Alert>}
      {logs && <details open><summary>Captured Code Run logs</summary>{(logs.stdout_truncated || logs.stderr_truncated || logs.stdout_tail_only || logs.stderr_tail_only) && <p className="muted">Bounded output; at most the last 64 KiB per stream is shown.</p>}<h3>stdout</h3><pre className="code-source" tabIndex={0}>{logs.stdout || "No stdout captured."}</pre><h3>stderr</h3><pre className="code-source" tabIndex={0}>{logs.stderr || "No stderr captured."}</pre></details>}
    </Panel>
    {result?.task === "binary_classification" && <ConfusionMatrixView matrix={result.confusion_matrix} />}
    {report && (Object.keys(report.metrics).length > 0 || Object.keys(report.outputs).length > 0) && <Panel title="Custom reported outputs" description="User-defined values, not built-in evaluation metrics.">
      <dl className="run-metrics">{Object.entries(report.metrics).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{String(value)}</dd></div>)}</dl>
      {Object.entries(report.outputs).map(([name, value]) => <div key={name}><h3>{name}</h3><pre className="run-json" tabIndex={0}>{typeof value === "string" ? value : JSON.stringify(value, null, 2)}</pre></div>)}
    </Panel>}
  </>;
}

export function CodeEvaluate({ projectId, runId }: { projectId: string; runId: string | null }) {
  const router = useRouter();
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<{ offset: number; data: CodeRunPage } | null>(null);
  const [error, setError] = useState("");
  const [defaultState, setDefaultState] = useState("loading");
  const [defaultError, setDefaultError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api.codeRuns(projectId, offset, controller.signal).then(data => { if (!controller.signal.aborted) { setPage({ offset, data }); setError(""); } })
      .catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Code Run history unavailable."); });
    return () => controller.abort();
  }, [projectId, offset, attempt]);
  useEffect(() => {
    if (runId) return;
    const controller = new AbortController();
    async function latestCompleted() {
      try {
        let cursor = 0;
        while (!controller.signal.aborted) {
          const next = await api.codeRuns(projectId, cursor, controller.signal);
          if (controller.signal.aborted) return;
          const selected = next.items.find(run => run.status === "COMPLETED");
          if (selected) { router.replace(codeEvaluationHref(projectId, selected.id)); return; }
          cursor += next.items.length;
          if (!next.items.length || cursor >= next.total) { setDefaultState("empty"); return; }
        }
      } catch (caught) { if (!controller.signal.aborted) { setDefaultState("error"); setDefaultError(caught instanceof Error ? caught.message : "Code evaluation unavailable."); } }
    }
    void latestCompleted();
    return () => controller.abort();
  }, [projectId, runId, router, attempt]);
  function refresh() { setPage(null); setDefaultState("loading"); setDefaultError(""); setAttempt(value => value + 1); }
  const data = page?.offset === offset ? page.data : null;
  return <div className="evaluate-view">
    <div className="section-heading"><h2>Evaluate · Code Runs</h2><Button onClick={refresh}>Refresh evaluation</Button></div>
    <p className="muted">The latest completed Code Run is selected by default. Explicit historical selection is preserved in the URL. Visual Run evidence is never substituted.</p>
    {runId ? <SelectedCodeEvaluation key={`${projectId}:${runId}:${attempt}`} projectId={projectId} runId={runId} /> : defaultState === "empty" ? <EmptyState title="No completed Code Runs">Run Python in <Link href={`/projects/${projectId}?view=code`}>Code Mode</Link>, then return here. Previous failed or active attempts can be selected below.</EmptyState> : defaultState === "error" ? <Alert>{defaultError}<Button onClick={refresh}>Retry</Button></Alert> : <Loading>Finding the latest completed Code Run…</Loading>}
    <Panel title="Select historical Code Runs" description="Newest first · Code Runs are distinct from Visual Runs.">
      {error ? <Alert>{error}<Button onClick={refresh}>Retry history</Button></Alert> : !data ? <Loading>Loading Code Run history…</Loading> : !data.items.length ? <p>No Code Runs yet.</p> : <><div className="table-scroll"><table><caption className="sr-only">Historical Code Run selection</caption><thead><tr><th>Created</th><th>Code Run</th><th>Execution</th><th>Selection</th></tr></thead><tbody>{data.items.map(run => <tr key={run.id}><td>{new Date(run.created_at).toLocaleString()}</td><th scope="row" className="wrap">{run.id}</th><td>{run.status}</td><td><Link href={codeEvaluationHref(projectId, run.id)} aria-current={run.id === runId ? "true" : undefined}>Evaluate Code Run</Link></td></tr>)}</tbody></table></div><div className="actions"><Button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous</Button><span>{offset + 1}–{offset + data.items.length} of {data.total}</span><Button disabled={offset + data.items.length >= data.total} onClick={() => setOffset(offset + 20)}>Next</Button></div></>}
    </Panel>
  </div>;
}
