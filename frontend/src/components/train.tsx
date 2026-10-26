"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api/projects";
import type { ModelIntent, PipelineIR, PipelineIssue, WorkingPipeline, ParameterSchema } from "@/lib/api/pipelines";
import { Alert, Button, EmptyState, Loading, Panel } from "./ui";
import { readDraft, writeDraft, clearDraft } from "@/lib/train-drafts";
import { parameterType, parseParameters, editedSplit, readinessGroups } from "@/lib/api/task-policy";
import { TrainDraftGuard } from "./train-draft-guard";
import { RunExperiment } from "./run-experiment";

function Issues({ issues }: { issues: PipelineIssue[] }) {
  return <>{issues.map((i, n) => <p className={i.severity === "blocking" ? "prepare-error" : "muted"} key={n}>
    {i.column && <strong className="wrap">{i.column}: </strong>}{i.message}
  </p>)}</>;
}

// Raw editor strings are temporary UI state; only parsed explicit intent is saved.
export function ConfigurationForm({ state, kind, disabled, onSave, onDirty, projectId, onReset }: {
  projectId: string; onReset: () => void; state: WorkingPipeline; kind: "model" | "split"; disabled: boolean;
  onSave: (ir: PipelineIR) => Promise<void>; onDirty: () => void;
}) {
  const source = kind === "model" ? state.ir.model!.parameters : state.ir.split!;
  const keyValue = (k: string, v: string | number | boolean) => k === "test_size" ? String(Number((Number(v) * 100).toFixed(10))) : String(v);
  const draft = readDraft(projectId);
  const recovered = draft?.revision === state.revision && draft.section === kind ? draft.values : null;
  const [values, setValues] = useState<Record<string, string>>(recovered ?? Object.fromEntries(Object.entries(source).map(([k, v]) => [k, v === null ? "" : keyValue(k, v)])));
  const [error, setError] = useState("");
  const [dirty, setDirty] = useState(Boolean(recovered));
  function change(key: string, value: string) {
    const next = { ...values, [key]: value }; setValues(next); writeDraft(projectId, { revision: state.revision, section: kind, values: next }); setDirty(true); setError(""); onDirty();
  }
  const descriptor = state.model_catalogue.find(d => d.id === state.ir.model?.type);
  const schemas: Record<string, ParameterSchema> = kind === "model" ? descriptor?.parameter_schema.properties ?? {} : Object.fromEntries(Object.keys(source).map(k => [k, { anyOf: [{ type: k === "stratify" ? "boolean" : k === "random_seed" ? "integer" : "number" }, { type: "null" }] }]));
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setError("");
    let parsed: Record<string, number | string | boolean | null>;
    try { parsed = parseParameters(values, schemas); }
    catch (error) { setError(error instanceof Error ? error.message : "Invalid parameters."); return; }
    const ir = kind === "model"
      ? { ...state.ir, model: { ...state.ir.model!, parameters: parsed } as ModelIntent }
      : { ...state.ir, split: editedSplit(state.ir.split!, parsed) };
    await onSave(ir);
  }
  return <form onSubmit={submit} noValidate>
    <fieldset disabled={disabled}>
      <div className="train-fields">
        {Object.keys(values).map(key => {
          const field = `${kind}.${kind === "model" ? "parameters." : ""}${key}`;
          const schema = schemas[key] ?? {};
          const type = parameterType(schema);
          const enumValues = schema.enum ?? schema.anyOf?.find(v => v.enum)?.enum;
          const choices = descriptor?.contextual_constraints[key]?.choices ?? enumValues;
          const issues = state.issues.filter(i => i.field === field);
          return <div key={key}>
            <label htmlFor={`train-${key}`}>{key === "test_size" ? "Test size (%)" : key === "random_seed" ? "Experiment seed" : key === "stratify" ? "Stratify by target" : key === "penalty" ? "Regularization penalty" : key === "fit_intercept" ? "Fit intercept" : key === "alpha" ? "Regularization strength (alpha)" : schema.title ?? key}</label>
            {type === "boolean" || choices ? <select id={`train-${key}`} value={values[key]} onChange={e => change(key, e.target.value)} aria-invalid={issues.length > 0 || error.startsWith(key + ":")} aria-describedby={`help-${key}${error.startsWith(key + ":") ? " train-local-error" : ""}`}>
              <option value="">Not configured</option>
              {type === "boolean" ? <><option value="true">Yes</option><option value="false">No</option></> : choices?.filter(v => v !== null).map(v => <option key={v} value={v!}>{v}</option>)}
            </select> : <input id={`train-${key}`} inputMode={type === "number" ? "decimal" : "numeric"} value={values[key]} placeholder={key === "max_depth" ? "Unlimited" : "Not configured"} onChange={e => change(key, e.target.value)} aria-invalid={issues.length > 0 || error.startsWith(key + ":")} aria-describedby={`help-${key}${error.startsWith(key + ":") ? " train-local-error" : ""}`} />}
            <p id={`help-${key}`} className="muted">{key === "test_size" ? "5–50% held out. Saved as a fraction in Pipeline IR." : key === "random_seed" ? "0–2147483647. One experiment seed; no separate model seed." : key === "stratify" ? "Checked against non-missing target counts without sampling rows." : key === "penalty" ? "L1 and L2 are the supported v0.1 penalties." : descriptor?.contextual_constraints[key]?.message ?? (schema.minimum !== undefined ? `Minimum: ${schema.minimum}.` : schema.exclusiveMinimum !== undefined ? `Greater than ${schema.exclusiveMinimum}.` : "Validated by the saved model contract.")}</p>
            <Issues issues={issues} />
          </div>;
        })}
      </div>
      {error && <Alert id="train-local-error">{error}</Alert>}
      <div className="actions"><Button variant="primary" type="submit" disabled={!dirty}>{kind === "model" ? "Save model parameters" : "Save split"}</Button><Button onClick={onReset} disabled={!dirty}>Reset unsaved edits</Button><span className="muted">{dirty ? "Unsaved edits. Save to update validation." : "Saved configuration"}</span></div>
    </fieldset>
  </form>;
}

export function Train({ projectId, datasetId, onReload }: {
  projectId: string; datasetId: string | null; onReload: () => void;
}) {
  const [state, setState] = useState<WorkingPipeline | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [dirty, setDirty] = useState<string | null>(null);
  const saving = useRef(false);
  const [scope, setScope] = useState("pipeline");
  useEffect(() => {
    const controller = new AbortController();
    api.pipeline(projectId, controller.signal).then(value => {
      if (!controller.signal.aborted) { setState(value); const draft = readDraft(projectId); if (draft) { setDirty(draft.section); if (draft.revision !== value.revision) { setConflict(true); setError("Saved configuration changed. Your old draft is retained; reset it before editing the newer revision."); } } }
    }).catch((err: unknown) => {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Train configuration unavailable.");
    });
    return () => controller.abort();
  }, [projectId]);
  async function save(ir: PipelineIR, section: string) {
    if (!state || saving.current || conflict) return;
    saving.current = true;
    setBusy(true); setError(""); setScope(section);
    try { setState(await api.savePipeline(projectId, state.revision, ir)); setDirty(null); clearDraft(projectId); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not save configuration."); setConflict(err instanceof ApiError && err.status === 409); }
    finally { saving.current = false; setBusy(false); }
  }
  function resetDraft() { clearDraft(projectId); setDirty(null); onReload(); }
  const feedback = (section: string) => error && scope === section ? <Alert>{error} <Button onClick={onReload}>Reload Train</Button></Alert> : null;
  if (!state) return error ? feedback("pipeline") : <Loading>Loading experiment configuration…</Loading>;
  if (!datasetId) return <Panel title="Train"><EmptyState title="Add a source Dataset first">Upload a CSV in <Link href={`/projects/${projectId}?view=data`}>Data</Link> to start configuring an experiment.</EmptyState></Panel>;
  if (state.stale) return <Panel title="Experiment source changed"><Alert>The Working Pipeline still references the previous Dataset. Review and explicitly reset it in <Link href={`/projects/${projectId}?view=prepare`}>Prepare</Link>. Model and split have not been copied to the new source.</Alert></Panel>;
  const { ir } = state;
  const features = Object.values(ir.features), included = features.filter(f => f.included);
  const count = (type: string) => included.filter(f => f.operations.some(op => op.type === type)).length;
  const modelName = state.model_catalogue.find(d => d.id === ir.model?.type)?.name ?? "Not selected";
  const testPercent = ir.split?.test_size === null || ir.split?.test_size === undefined ? null : Number((ir.split.test_size * 100).toFixed(10));
  const validProportion = testPercent !== null && testPercent >= 5 && testPercent <= 50;
  const disabled = busy || conflict;
  const checks = readinessGroups(state.issues, ir.ir_version === "0.2");
  return <div className="train-view"><TrainDraftGuard projectId={projectId} dirty={Boolean(dirty)} saving={busy} />{dirty && <Alert tone="info">An unsaved Train draft is retained in this tab. Save it or <Button disabled={busy} onClick={resetDraft}>Reset unsaved draft</Button> before changing configuration.</Alert>}
    <div className="section-heading"><div><div className="eyebrow">Experiment configuration</div><h2>Train</h2><p className="muted">Configure, review, and execute a saved experiment.</p></div><span className="badge subtle" role="status">{busy ? "Saving…" : dirty ? "Unsaved edits" : `Saved · revision ${state.revision}`}</span></div>
    {conflict && <Alert>Newer Project state exists. Reload before editing further. <Button onClick={resetDraft}>Reset draft and reload Train</Button></Alert>}
    {feedback("pipeline")}
    <Panel title="Experiment" description={state.original_filename ?? "Source Dataset"}>
      <div className="train-flow" aria-label="Saved experiment flow"><span>Source Dataset</span><span aria-hidden="true">→</span><span>{included.length} included features</span><span aria-hidden="true">→</span><span>{validProportion ? `${100 - testPercent!} / ${testPercent} split` : "Split not valid"}</span><span aria-hidden="true">→</span><strong>{modelName}</strong></div>
      <dl className="train-summary">
        <div><dt>Target</dt><dd className="wrap">{ir.target?.column ?? "Not selected"}</dd></div>
        {ir.ir_version === "0.1" && <div><dt>Positive class</dt><dd className="wrap">{ir.target?.positive_class ? `${String(ir.target.positive_class.value)} (${ir.target.positive_class.value_type})` : "Not configured"}</dd></div>}
        <div><dt>Participation</dt><dd>{included.length} included · {features.length - included.length} excluded</dd></div>
        <div><dt>Preparation</dt><dd>{count("impute")} imputed · {count("scale")} scaled · {count("encode")} encoded</dd></div>
      </dl>
      <p className="muted">{state.eligible_rows} rows have non-missing targets; {state.target_missing_count} missing-target rows will be excluded before splitting. Source data stays unchanged.</p>
      <div className="train-links"><Link href={`/projects/${projectId}?view=data`}>Review target in Data</Link><Link href={`/projects/${projectId}?view=prepare`}>{ir.ir_version === "0.2" ? "Edit features in Prepare" : "Edit features and positive class in Prepare"}</Link></div>
    </Panel>
    <Panel title="Data split" description="Keep a held-out test partition separate from training. Preprocessing will learn only from training data.">
      {validProportion && <div className="split-visual" aria-label={`Training ${100 - testPercent!}%, testing ${testPercent}%`}><div className="split-labels"><strong>Training · {100 - testPercent!}%</strong><span>Testing · {testPercent}%</span></div><div className="split-track"><span style={{ width: `${100 - testPercent!}%` }} /><span style={{ width: `${testPercent}%` }} /></div><p className="muted">{state.train_rows} training / {state.test_rows} test rows · {ir.split?.stratify ? "Stratified" : "Not stratified"} · seed {ir.split?.random_seed ?? "not configured"}</p></div>}
      {feedback("split")}
      {ir.split ? <ConfigurationForm projectId={projectId} onReset={resetDraft} key={`split:${state.revision}`} kind="split" state={state} disabled={disabled || (dirty !== null && dirty !== "split")} onDirty={() => setDirty("split")} onSave={value => save(value, "split")} /> : <Button disabled={disabled || Boolean(dirty)} onClick={() => void save({ ...ir, split: state.split_defaults }, "split")}>Configure 80 / 20 split</Button>}
      <Issues issues={state.issues.filter(i => i.scope === "train" && i.field === "split")} />
    </Panel>
    <Panel title="Model" description="Choose one supported model. Selection uses the backend catalogue and its explicit defaults.">
      <div className="model-selector">{state.model_catalogue.map(descriptor => <button key={descriptor.id} aria-pressed={ir.model?.type === descriptor.id} disabled={disabled || Boolean(dirty) || ir.model?.type === descriptor.id} onClick={() => void save({ ...ir, model: { type: descriptor.id, parameters: descriptor.defaults } as ModelIntent }, "model")}><strong>{descriptor.name}</strong><span>{descriptor.task === "regression" ? "Numeric target regression" : "Binary classifier"}</span></button>)}</div>
      {dirty && <p className="muted">Save current edits before switching models. Navigation asks for confirmation; drafts are retained in this tab.</p>}
      {feedback("model")}
      {ir.model && <ConfigurationForm projectId={projectId} onReset={resetDraft} key={`model:${state.revision}`} kind="model" state={state} disabled={disabled || (dirty !== null && dirty !== "model")} onDirty={() => setDirty("model")} onSave={value => save(value, "model")} />}
    </Panel>
    <Panel title="Pipeline readiness" description="Validation of saved intent against the current source and effective semantics.">
      <p className={`readiness-status ${state.code_generation_ready && !dirty ? "complete" : ""}`} role="status">{dirty ? "Save edits to update readiness" : state.code_generation_ready ? "Saved configuration valid · ready for Code review" : "Pipeline needs attention"}</p>
      <div className="readiness-checks">{checks.map(([label, issues]) => <div key={label}><strong>{issues.some(i => i.severity === "blocking") ? "Needs attention" : "✓"} · {label}</strong><Issues issues={issues} /></div>)}</div>
      <RunExperiment projectId={projectId} revision={state.revision} ready={state.code_generation_ready && !state.stale} dirty={Boolean(dirty)} conflict={conflict} saving={busy} onReload={onReload} />
    </Panel>
    <details className="panel"><summary>Saved Pipeline IR · {ir.ir_version}</summary><pre>{JSON.stringify(ir, null, 2)}</pre></details>
  </div>;
}
