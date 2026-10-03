"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api/projects";
import type { FeatureIntent, Operation, PipelineIR, PipelineIssue, WorkingPipeline } from "@/lib/api/pipelines";
import { Alert, Button, EmptyState, Loading, Panel } from "./ui";

function Issues({ issues }: { issues: PipelineIssue[] }) {
  return <>{issues.map((issue, index) => <p className={issue.severity === "blocking" ? "prepare-error" : "muted"} key={`${issue.code}:${index}`}>
    <strong>{issue.severity === "blocking" ? "Blocking issue" : "Non-blocking observation"}:</strong> {issue.message}
  </p>)}</>;
}

export function Prepare({ projectId, datasetId, onReload }: {
  projectId: string; datasetId: string | null; onReload: () => void;
}) {
  const [state, setState] = useState<WorkingPipeline | null>(null);
  const [error, setError] = useState("");
  const [errorScope, setErrorScope] = useState("pipeline");
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [offset, setOffset] = useState(0);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api.pipeline(projectId, controller.signal).then((data) => {
      if (!controller.signal.aborted) setState(data);
    }).catch((err: unknown) => {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Prepare unavailable.");
    });
    return () => controller.abort();
  }, [projectId]);
  async function persist(ir: PipelineIR, scope: string) {
    if (!state || busy || conflict) return;
    setBusy(true); setError(""); setSaved(false); setErrorScope(scope);
    try { setState(await api.savePipeline(projectId, state.revision, ir)); setSaved(true); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not save preparation."); setConflict(err instanceof ApiError && err.status === 409); }
    finally { setBusy(false); }
  }
  async function reset() {
    if (!state || !datasetId || !confirmed) return;
    setBusy(true); setError(""); setErrorScope("pipeline"); setSaved(false);
    try { setState(await api.resetPipeline(projectId, state.revision, datasetId)); setConfirmed(false); setOffset(0); setSaved(true); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not reset preparation."); setConflict(err instanceof ApiError && err.status === 409); }
    finally { setBusy(false); }
  }
  const localError = (scope: string) => error && errorScope === scope ? <Alert>{error} <Button onClick={onReload}>Reload Prepare</Button></Alert> : null;
  if (!state) return error ? localError("pipeline") : <Loading>Loading Working Pipeline…</Loading>;
  if (!datasetId) return <Panel title="Prepare"><EmptyState title="No Dataset attached">Upload a CSV in <Link href={`/projects/${projectId}?view=data`}>Data</Link> to configure preparation.</EmptyState></Panel>;
  const { ir } = state;
  const incompleteCodes = new Set(["target_missing", "positive_class_missing", "dataset_missing", "features_empty"]);
  const hasInvalidIntent = state.issues.some(issue => issue.severity === "blocking" && issue.scope !== "train" && !incompleteCodes.has(issue.code));
  const disabled = busy || conflict || state.stale;
  const targetColumn = state.columns.find((column) => column.name === ir.target?.column);
  const names = [...state.columns.map(c => c.name).filter(name => name !== ir.target?.column), ...Object.keys(ir.features).filter(name => !state.columns.some(c => c.name === name))];
  function updateFeature(name: string, feature: FeatureIntent) {
    void persist({ ...ir, features: { ...ir.features, [name]: feature } }, `feature:${name}`);
  }
  function changeOperation(name: string, feature: FeatureIntent, family: Operation["type"], value: string) {
    const operations = feature.operations.filter(op => op.type !== family);
    if (value) {
      const op = family === "impute" ? { type: family, strategy: value } : { type: family, method: value };
      if (family === "impute") operations.unshift(op as Operation); else operations.push(op as Operation);
    }
    updateFeature(name, { ...feature, operations });
  }
  return <div className="prepare-view">
    <Panel title="Prepare" description="Define feature participation and ordered preprocessing. Source data stays unchanged. Each change saves immediately.">
      <p role="status"><strong>{state.stale ? "Stale configuration" : state.prepare_valid ? "Prepare configuration valid" : hasInvalidIntent ? "Prepare has blocking issues" : "Prepare configuration incomplete"}</strong>{busy ? " · Saving…" : saved ? " · Saved" : ""}</p>
      <p className="muted">Complete model and split configuration in Train. No training executes yet.</p>
      <Issues issues={state.issues.filter(i => i.scope === "pipeline")} />
      {localError("pipeline")}
      {conflict && <Alert>Newer Project state exists. Reload Prepare to review it before making further edits. <Button onClick={onReload}>Reload Prepare</Button></Alert>}
      <details><summary>Reset preparation</summary>
        <p>Replace this working recipe with the current Dataset and target. All feature candidates start included, with no operations. Previous preparation choices, positive class, model, and split will be cleared.</p>
        <label className="check-label"><input type="checkbox" checked={confirmed} disabled={busy || conflict} onChange={e => setConfirmed(e.target.checked)} /> I understand that this replaces the working preparation.</label>
        <Button disabled={!confirmed || busy || conflict} onClick={() => void reset()}>Reset for current Dataset</Button>
      </details>
    </Panel>
    {!state.stale && <>
      <Panel title="Target" description="Choose the positive class for the target selected in Data.">
        <p><strong>{ir.target?.column ?? "No target selected"}</strong>{targetColumn ? ` · ${targetColumn.effective_semantic_type}` : ""} · <Link href={`/projects/${projectId}?view=data`}>Change target in Data</Link></p>
        <Issues issues={state.issues.filter(i => i.scope === "target")} />
        {localError("target")}
        {ir.target && <label>Positive class
          <select aria-label="Positive class" disabled={disabled || state.target_classes.length !== 2} value={state.target_classes.findIndex(c => JSON.stringify(c) === JSON.stringify(ir.target?.positive_class))} onChange={e => void persist({ ...ir, target: { ...ir.target!, positive_class: Number(e.target.value) < 0 ? null : state.target_classes[Number(e.target.value)] } }, "target")}>
            <option value={-1}>Choose explicitly</option>
            {state.target_classes.map((c, index) => <option value={index} key={index}>{String(c.value)} ({c.value_type})</option>)}
          </select>
        </label>}
        <p className="muted">Missing target rows: {state.target_missing_count}. The fixed policy excludes these rows before training and evaluation; the target is never imputed. Choosing a positive class confirms this policy.</p>
      </Panel>
      <Panel title="Features" description="Operations are ordered: imputation first, then scaling or encoding. None means no operation. Excluded features retain dormant choices.">
        <div className="table-scroll"><table className="prepare-table"><thead><tr><th>Feature / effective type</th><th>Participation</th><th>Missing values</th><th>Scaling / encoding</th><th>Validation / intent</th></tr></thead><tbody>
          {names.slice(offset, offset + 20).map(name => {
            const feature = Object.hasOwn(ir.features, name) ? ir.features[name] : undefined;
            const column = state.columns.find(c => c.name === name);
            const numeric = column?.effective_semantic_type === "continuous";
            const categorical = column?.effective_semantic_type === "categorical" || column?.effective_semantic_type === "binary";
            const supported = numeric || categorical;
            const impute = feature?.operations.find(op => op.type === "impute");
            const transform = feature?.operations.find(op => op.type === (numeric ? "scale" : "encode"));
            return <tr key={name}><th scope="row"><span className="column-name">{name}</span><small>{column?.effective_semantic_type ?? "Missing column"}</small><small>{column?.missing_count ?? "—"} missing</small></th>
              <td>{feature ? <label className="check-label"><input aria-label={`Include ${name}`} type="checkbox" checked={feature.included} disabled={disabled} onChange={e => updateFeature(name, { ...feature, included: e.target.checked })} />{feature.included ? "Included" : "Excluded"}</label> : <Button disabled={disabled} onClick={() => updateFeature(name, { included: false, operations: [] })}>Restore excluded</Button>}</td>
              <td>{feature && supported ? <select aria-label={`Missing values for ${name}`} disabled={disabled} value={impute?.strategy ?? ""} onChange={e => changeOperation(name, feature, "impute", e.target.value)}><option value="">None</option>{numeric && <><option value="mean">Mean</option><option value="median">Median</option></>}<option value="most_frequent">Most frequent</option>{!numeric && impute && impute.strategy !== "most_frequent" && <option value={impute.strategy}>{impute.strategy} (incompatible)</option>}</select> : "Not supported"}</td>
              <td>{feature && supported ? <select aria-label={`${numeric ? "Scaling" : "Encoding"} for ${name}`} disabled={disabled} value={transform && "method" in transform ? transform.method : ""} onChange={e => changeOperation(name, feature, numeric ? "scale" : "encode", e.target.value)}><option value="">None</option>{numeric ? <><option value="standard">Standard</option><option value="min_max">MinMax</option><option value="robust">Robust</option></> : <option value="one_hot">One-hot</option>}</select> : "No v0.1 transform"}</td>
              <td>{!supported && <p className="muted">Review the semantic type in Data or exclude this feature.</p>}
                {feature && <small>{feature.operations.length ? feature.operations.map(op => op.type === "impute" ? `Impute ${op.strategy}` : `${op.type} ${op.method}`).join(" → ") : "No operations"}{!feature.included && " · dormant"}</small>}
                <Issues issues={state.issues.filter(i => i.scope === "feature" && i.column === name)} />{localError(`feature:${name}`)}
                {!!feature?.operations.length && <Button disabled={disabled} onClick={() => updateFeature(name, { ...feature, operations: [] })}>Clear operations</Button>}
                {!column && <Button disabled={disabled} onClick={() => { const features = { ...ir.features }; delete features[name]; void persist({ ...ir, features }, `feature:${name}`); }}>Remove absent column</Button>}
              </td></tr>;
          })}
        </tbody></table></div>
        <div className="actions"><Button disabled={offset === 0 || busy} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous features</Button><span>{names.length ? offset + 1 : 0}–{Math.min(offset + 20, names.length)} of {names.length}</span><Button disabled={offset + 20 >= names.length || busy} onClick={() => setOffset(offset + 20)}>Next features</Button></div>
      </Panel>
    </>}
    <details className="panel"><summary>Pipeline configuration · IR {ir.ir_version}</summary><pre>{JSON.stringify(ir, null, 2)}</pre></details>
  </div>;
}
