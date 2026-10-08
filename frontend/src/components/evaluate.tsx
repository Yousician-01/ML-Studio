"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/projects";
import type { Run, RunPage } from "@/lib/api/runs";
import { compareContext, comparisonSelection, metrics, metricDelta, metricText, successful } from "@/lib/api/evaluation-policy";
import { RunStatus, useRun } from "./runs";
import { ConfusionMatrix, FrozenRunContext, IntegrityNotice, RunMetrics } from "./run-results";
import { Alert, Button, EmptyState, Loading, Panel } from "./ui";

export function evaluationHref(projectId: string, runId: string, compareId?: string, latest = false) {
  const query = new URLSearchParams({ view: "evaluate", run: runId });
  if (compareId) query.set("compare", compareId);
  if (latest) query.set("selection", "latest");
  return `/projects/${projectId}?${query}`;
}

export function EvaluationComparison({ projectId, runs }: { projectId: string; runs: Run[] }) {
  const selection = comparisonSelection(projectId, runs);
  if (selection) return <Alert>{selection}</Alert>;
  const context = compareContext(projectId, runs);
  return <Panel title={`Compare Run #${runs[0].sequence} and Run #${runs[1].sequence}`} description="Values from two immutable Runs. No ranking or winner is implied.">
    {context.compatible ? <p>Evaluation contexts match. Deltas are Run B − Run A.</p> : <Alert tone="info"><strong>Different or unverifiable evaluation contexts — no metric deltas.</strong><ul>{context.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></Alert>}
    {context.notes.map(note => <p className="muted" key={note}>{note}</p>)}
    <div className="table-scroll"><table><caption className="sr-only">Frozen Run metrics comparison</caption><thead><tr><th scope="col">Metric</th><th scope="col">A · Run #{runs[0].sequence}</th><th scope="col">B · Run #{runs[1].sequence}</th>{context.compatible && <th scope="col">B − A</th>}</tr></thead><tbody>{metrics.map(({ key, label }) => { const delta = metricDelta(projectId, runs, key); return <tr key={key}><th scope="row">{label}</th>{runs.map(run => <td key={run.id}>{metricText(run.result?.metrics[key])}</td>)}{context.compatible && <td>{delta === null ? "Unavailable" : `${delta > 0 ? "+" : ""}${delta.toFixed(4)}`}</td>}</tr>; })}</tbody></table></div>
  </Panel>;
}

function RunEvaluation({ run }: { run: Run }) {
  return <div className="evaluation-run"><Panel title={`Run #${run.sequence} · ${run.summary.model.name}`} description={`Created ${new Date(run.created_at).toLocaleString()} · immutable historical evidence`}>
    <p className="wrap">Run ID: {run.id}</p><RunStatus run={run} /><IntegrityNotice run={run} />
    {successful(run) && run.result ? <RunMetrics result={run.result} /> : run.state === "FAILED" ? <Alert>Failed Runs have no completed evaluation. {run.failure?.message}</Alert> : run.state === "SUCCEEDED" ? <Alert>Completed evaluation results are unavailable.</Alert> : <p role="status">Evaluation is unavailable until execution succeeds. This attempt is still active.</p>}
    <Link href={`/projects/${run.project_id}?view=runs&run=${encodeURIComponent(run.id)}`}>Open historical Run details</Link>
  </Panel>{successful(run) && run.result && <ConfusionMatrix result={run.result} />}<FrozenRunContext run={run} /></div>;
}

function SelectedEvaluation({ projectId, runId, compareId }: { projectId: string; runId: string; compareId: string | null }) {
  const [attempt, setAttempt] = useState(0);
  const primary = useRun(projectId, runId, attempt);
  const secondary = useRun(projectId, compareId, attempt);
  const error = primary.error || secondary.error;
  if (error) return <Alert>Selected Run unavailable: {error} The ID may be stale or belong to another Project. <Button onClick={() => setAttempt(value => value + 1)}>Retry selected Runs</Button></Alert>;
  if (!primary.run || (compareId && !secondary.run)) return <Loading>Loading frozen evaluation evidence…</Loading>;
  if (primary.run.project_id !== projectId || (secondary.run && secondary.run.project_id !== projectId)) return <Alert>Selected Runs must belong to this Project.</Alert>;
  return <>{compareId && secondary.run && <EvaluationComparison projectId={projectId} runs={[primary.run, secondary.run]} />}<div className={compareId ? "evaluation-columns" : ""}><RunEvaluation run={primary.run} />{secondary.run && compareId !== runId && <RunEvaluation run={secondary.run} />}</div></>;
}

export function Evaluate({ projectId, runId, compareId, latest }: { projectId: string; runId: string | null; compareId: string | null; latest: boolean }) {
  const router = useRouter();
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<RunPage | null>(null);
  const [error, setError] = useState("");
  const [defaultError, setDefaultError] = useState("");
  const [defaultState, setDefaultState] = useState("loading");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api.runs(projectId, offset, controller.signal).then(next => { if (!controller.signal.aborted) { setPage(next); setError(""); } }).catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "History unavailable."); });
    return () => controller.abort();
  }, [projectId, offset, attempt]);
  useEffect(() => {
    if (runId) return;
    const controller = new AbortController();
    async function selectLatest() {
      try {
        let cursor = 0;
        while (!controller.signal.aborted) {
          const next = await api.runs(projectId, cursor, controller.signal);
          if (controller.signal.aborted) return;
          const selected = next.items.find(successful);
          if (selected) { router.replace(evaluationHref(projectId, selected.id, undefined, true)); return; }
          cursor += next.items.length;
          if (!next.items.length || cursor >= next.total) { setDefaultState("empty"); return; }
        }
      } catch (caught) { if (!controller.signal.aborted) { setDefaultState("error"); setDefaultError(caught instanceof Error ? caught.message : "Evaluation unavailable."); } }
    }
    void selectLatest();
    return () => controller.abort();
  }, [projectId, runId, router, attempt]);
  function refresh() { setPage(null); setError(""); setDefaultState("loading"); setDefaultError(""); setAttempt(value => value + 1); }
  return <div className="evaluate-view"><div className="section-heading"><div><h2>Evaluate</h2><p className="muted">{latest ? "Defaulted to the latest successful Run; selection retained in this URL." : "Selected historical Run evidence; current workspace changes do not alter these results."}</p></div><Button onClick={refresh}>Refresh evaluation</Button></div>
    {compareId && runId && <Link href={evaluationHref(projectId, runId)}>Remove comparison</Link>}
    {runId ? <SelectedEvaluation key={`${projectId}:${runId}:${compareId}:${attempt}`} projectId={projectId} runId={runId} compareId={compareId} /> : defaultState === "empty" ? <EmptyState title="No successful Runs yet">Complete an experiment in <Link href={`/projects/${projectId}?view=train`}>Train</Link> to evaluate its held-out results.</EmptyState> : defaultState === "error" ? <Alert>{defaultError}<Button onClick={refresh}>Retry evaluation</Button></Alert> : <Loading>Finding the latest successful Run…</Loading>}
    <Panel title="Select historical Runs" description="Newest first · select one Run to evaluate, or a second successful Run to compare. Selection is retained in the URL.">
      {error ? <Alert>{error}<Button onClick={refresh}>Retry history</Button></Alert> : !page || page.offset !== offset ? <Loading>Loading historical selection…</Loading> : !page.items.length ? <p>No historical Runs.</p> : <><div className="table-scroll"><table><caption className="sr-only">Paginated historical evaluation selection</caption><thead><tr><th>Run</th><th>Status</th><th>Model</th><th>Selection</th></tr></thead><tbody>{page.items.map(run => <tr key={run.id}><th scope="row">#{run.sequence}</th><td><RunStatus run={run} /></td><td>{run.summary.model.name}</td><td><div className="actions"><Link aria-current={runId === run.id ? "true" : undefined} href={evaluationHref(projectId, run.id)}>Evaluate #{run.sequence}</Link>{runId && <Button disabled={!successful(run) || run.id === runId} onClick={() => router.push(evaluationHref(projectId, runId, run.id))}>Compare #{run.sequence}</Button>}</div></td></tr>)}</tbody></table></div><div className="actions run-pagination"><Button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous</Button><span>{offset + 1}–{offset + page.items.length} of {page.total}</span><Button disabled={offset + page.items.length >= page.total} onClick={() => setOffset(offset + 20)}>Next</Button></div></>}
    </Panel>
  </div>;
}
