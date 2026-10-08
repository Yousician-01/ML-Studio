"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api/projects";
import type { ModelIntent, PipelineIR, PipelineIssue, WorkingPipeline } from "@/lib/api/pipelines";
import { Alert, Button, EmptyState, Loading, Panel } from "./ui";
import { RunExperiment } from "./run-experiment";

const models = {
  logistic_regression: ["Logistic Regression", "Linear probabilistic classifier."],
  decision_tree: ["Decision Tree", "Rule-based nonlinear classifier."],
  random_forest: ["Random Forest", "Ensemble of decision trees."],
};
const labels: Record<string, string> = {
  C: "Inverse regularization strength (C)", max_iter: "Maximum iterations",
  max_depth: "Maximum tree depth", min_samples_split: "Minimum samples to split",
  min_samples_leaf: "Minimum samples per leaf", n_estimators: "Number of trees",
};
const hints: Record<string, string> = {
  C: "Greater than zero. Smaller values apply stronger regularization.",
  max_iter: "Integer of at least 1.", max_depth: "Leave blank for unlimited depth; otherwise an integer of at least 1.",
  min_samples_split: "Integer of at least 2.", min_samples_leaf: "Integer of at least 1.",
  n_estimators: "Integer of at least 1.",
};

function Issues({ issues }: { issues: PipelineIssue[] }) {
  return <>{issues.map((i, n) => <p className={i.severity === "blocking" ? "prepare-error" : "muted"} key={n}>
    {i.column && <strong className="wrap">{i.column}: </strong>}{i.message}
  </p>)}</>;
}

// Raw editor strings are temporary UI state; only parsed explicit intent is saved.
function ConfigurationForm({ state, kind, disabled, onSave, onDirty }: {
  state: WorkingPipeline; kind: "model" | "split"; disabled: boolean;
  onSave: (ir: PipelineIR) => Promise<void>; onDirty: () => void;
}) {
  const source = kind === "model" ? state.ir.model!.parameters : state.ir.split!;
  const keyValue = (k: string, v: string | number | boolean) => k === "test_size" ? String(Number((Number(v) * 100).toFixed(10))) : String(v);
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(source).map(([k, v]) => [k, v === null ? "" : keyValue(k, v)])),
  );
  const [error, setError] = useState("");
  const [dirty, setDirty] = useState(false);
  function change(key: string, value: string) {
    setValues(v => ({ ...v, [key]: value })); setDirty(true); setError(""); onDirty();
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setError("");
    const parsed: Record<string, number | string | boolean | null> = {};
    for (const [key, raw] of Object.entries(values)) {
      if (key === "penalty") { parsed[key] = raw || null; continue; }
      if (key === "stratify") { parsed[key] = raw === "" ? null : raw === "true"; continue; }
      if (raw.trim() === "") { parsed[key] = null; continue; }
      const value = Number(raw);
      if (!Number.isFinite(value) || (!['C', 'test_size'].includes(key) && !Number.isSafeInteger(value))) {
        setError(`${labels[key] ?? "Experiment seed"}: enter a finite ${['C', 'test_size'].includes(key) ? "number" : "integer"}.`);
        return;
      }
      parsed[key] = value;
    }
    const ir = kind === "model"
      ? { ...state.ir, model: { ...state.ir.model!, parameters: parsed } as ModelIntent }
      : { ...state.ir, split: { test_size: parsed.test_size === null ? null : Number(parsed.test_size) / 100, random_seed: parsed.random_seed as number | null, stratify: parsed.stratify as boolean | null } };
    await onSave(ir);
  }
  return <form onSubmit={submit} noValidate>
    <fieldset disabled={disabled}>
      <div className="train-fields">
        {Object.keys(values).map(key => {
          const field = `${kind}.${kind === "model" ? "parameters." : ""}${key}`;
          const issues = state.issues.filter(i => i.field === field);
          return <div key={key}>
            <label htmlFor={`train-${key}`}>{key === "test_size" ? "Test size (%)" : key === "random_seed" ? "Experiment seed" : key === "stratify" ? "Stratify by target" : key === "penalty" ? "Regularization penalty" : labels[key]}</label>
            {key === "penalty" || key === "stratify" ? <select id={`train-${key}`} value={values[key]} onChange={e => change(key, e.target.value)} aria-invalid={issues.length > 0} aria-describedby={`help-${key}`}>
              <option value="">Not configured</option>
              {key === "penalty" ? <><option value="l2">L2</option><option value="l1">L1</option></> : <><option value="true">Yes — preserve class proportions</option><option value="false">No — class representation is not guaranteed</option></>}
            </select> : <input id={`train-${key}`} inputMode={key === "C" || key === "test_size" ? "decimal" : "numeric"} value={values[key]} placeholder={key === "max_depth" ? "Unlimited" : "Not configured"} onChange={e => change(key, e.target.value)} aria-invalid={issues.length > 0} aria-describedby={`help-${key}`} />}
            <p id={`help-${key}`} className="muted">{key === "test_size" ? "5–50% held out. Saved as a fraction in Pipeline IR." : key === "random_seed" ? "0–2147483647. One experiment seed; no separate model seed." : key === "stratify" ? "Checked against non-missing target counts without sampling rows." : key === "penalty" ? "L1 and L2 are the supported v0.1 penalties." : hints[key]}</p>
            <Issues issues={issues} />
          </div>;
        })}
      </div>
      {error && <Alert>{error}</Alert>}
      <div className="actions"><Button variant="primary" type="submit" disabled={!dirty}>{kind === "model" ? "Save model parameters" : "Save split"}</Button><span className="muted">{dirty ? "Unsaved edits. Save to update validation." : "Saved configuration"}</span></div>
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
  const [scope, setScope] = useState("pipeline");
  useEffect(() => {
    const controller = new AbortController();
    api.pipeline(projectId, controller.signal).then(value => {
      if (!controller.signal.aborted) setState(value);
    }).catch((err: unknown) => {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Train configuration unavailable.");
    });
    return () => controller.abort();
  }, [projectId]);
  async function save(ir: PipelineIR, section: string) {
    if (!state || busy || conflict) return;
    setBusy(true); setError(""); setScope(section);
    try { setState(await api.savePipeline(projectId, state.revision, ir)); setDirty(null); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not save configuration."); setConflict(err instanceof ApiError && err.status === 409); }
    finally { setBusy(false); }
  }
  const feedback = (section: string) => error && scope === section ? <Alert>{error} <Button onClick={onReload}>Reload Train</Button></Alert> : null;
  if (!state) return error ? feedback("pipeline") : <Loading>Loading experiment configuration…</Loading>;
  if (!datasetId) return <Panel title="Train"><EmptyState title="Add a source Dataset first">Upload a CSV in <Link href={`/projects/${projectId}?view=data`}>Data</Link> to start configuring an experiment.</EmptyState></Panel>;
  if (state.stale) return <Panel title="Experiment source changed"><Alert>The Working Pipeline still references the previous Dataset. Review and explicitly reset it in <Link href={`/projects/${projectId}?view=prepare`}>Prepare</Link>. Model and split have not been copied to the new source.</Alert></Panel>;
  const { ir } = state;
  const features = Object.values(ir.features), included = features.filter(f => f.included);
  const count = (type: string) => included.filter(f => f.operations.some(op => op.type === type)).length;
  const modelName = ir.model ? models[ir.model.type][0] : "Not selected";
  const testPercent = ir.split?.test_size === null || ir.split?.test_size === undefined ? null : Number((ir.split.test_size * 100).toFixed(10));
  const validProportion = testPercent !== null && testPercent >= 5 && testPercent <= 50;
  const disabled = busy || conflict;
  const checks = [
    ["Dataset binding", state.issues.filter(i => i.scope === "pipeline" && i.code.startsWith("dataset"))],
    ["Target & positive class", state.issues.filter(i => i.scope === "target")],
    ["Features & preparation", state.issues.filter(i => i.scope === "feature" || i.column !== null || i.code === "features_empty")],
    ["Data split", state.issues.filter(i => i.field?.startsWith("split"))],
    ["Model", state.issues.filter(i => i.field?.startsWith("model"))],
  ] as const;
  return <div className="train-view">
    <div className="section-heading"><div><div className="eyebrow">Experiment configuration</div><h2>Train</h2><p className="muted">Configure, review, and execute a saved experiment.</p></div><span className="badge subtle" role="status">{busy ? "Saving…" : dirty ? "Unsaved edits" : `Saved · revision ${state.revision}`}</span></div>
    {conflict && <Alert>Newer Project state exists. Reload before editing further. <Button onClick={onReload}>Reload Train</Button></Alert>}
    {feedback("pipeline")}
    <Panel title="Experiment" description={state.original_filename ?? "Source Dataset"}>
      <div className="train-flow" aria-label="Saved experiment flow"><span>Source Dataset</span><span aria-hidden="true">→</span><span>{included.length} included features</span><span aria-hidden="true">→</span><span>{validProportion ? `${100 - testPercent!} / ${testPercent} split` : "Split not valid"}</span><span aria-hidden="true">→</span><strong>{modelName}</strong></div>
      <dl className="train-summary">
        <div><dt>Target</dt><dd className="wrap">{ir.target?.column ?? "Not selected"}</dd></div>
        <div><dt>Positive class</dt><dd className="wrap">{ir.target?.positive_class ? `${String(ir.target.positive_class.value)} (${ir.target.positive_class.value_type})` : "Not configured"}</dd></div>
        <div><dt>Participation</dt><dd>{included.length} included · {features.length - included.length} excluded</dd></div>
        <div><dt>Preparation</dt><dd>{count("impute")} imputed · {count("scale")} scaled · {count("encode")} encoded</dd></div>
      </dl>
      <p className="muted">{state.eligible_rows} rows have non-missing targets; {state.target_missing_count} missing-target rows will be excluded before splitting. Source data stays unchanged.</p>
      <div className="train-links"><Link href={`/projects/${projectId}?view=data`}>Review target in Data</Link><Link href={`/projects/${projectId}?view=prepare`}>Edit features and positive class in Prepare</Link></div>
    </Panel>
    <Panel title="Data split" description="Keep a held-out test partition separate from training. Preprocessing will learn only from training data.">
      {validProportion && <div className="split-visual" aria-label={`Training ${100 - testPercent!}%, testing ${testPercent}%`}><div className="split-labels"><strong>Training · {100 - testPercent!}%</strong><span>Testing · {testPercent}%</span></div><div className="split-track"><span style={{ width: `${100 - testPercent!}%` }} /><span style={{ width: `${testPercent}%` }} /></div><p className="muted">{state.train_rows} training / {state.test_rows} test rows · {ir.split?.stratify ? "Stratified" : "Not stratified"} · seed {ir.split?.random_seed ?? "not configured"}</p></div>}
      {feedback("split")}
      {ir.split ? <ConfigurationForm key={`split:${state.revision}`} kind="split" state={state} disabled={disabled || (dirty !== null && dirty !== "split")} onDirty={() => setDirty("split")} onSave={value => save(value, "split")} /> : <Button disabled={disabled || Boolean(dirty)} onClick={() => void save({ ...ir, split: state.split_defaults }, "split")}>Configure 80 / 20 split</Button>}
      <Issues issues={state.issues.filter(i => i.scope === "train" && i.field === "split")} />
    </Panel>
    <Panel title="Model" description="Choose one classifier. Selecting a different model replaces its parameters with explicit ML Studio defaults.">
      <div className="model-selector">{state.model_defaults.map(model => <button key={model.type} aria-pressed={ir.model?.type === model.type} disabled={disabled || Boolean(dirty) || ir.model?.type === model.type} onClick={() => void save({ ...ir, model }, "model")}><strong>{models[model.type][0]}</strong><span>{models[model.type][1]}</span></button>)}</div>
      {dirty && <p className="muted">Save current edits before switching models. Navigating away discards unsaved input.</p>}
      {feedback("model")}
      {ir.model && <ConfigurationForm key={`model:${state.revision}`} kind="model" state={state} disabled={disabled || (dirty !== null && dirty !== "model")} onDirty={() => setDirty("model")} onSave={value => save(value, "model")} />}
    </Panel>
    <Panel title="Pipeline readiness" description="Validation of saved intent against the current source and effective semantics.">
      <p className={`readiness-status ${state.code_generation_ready && !dirty ? "complete" : ""}`} role="status">{dirty ? "Save edits to update readiness" : state.code_generation_ready ? "Ready for code generation" : "Pipeline needs attention"}</p>
      <div className="readiness-checks">{checks.map(([label, issues]) => <div key={label}><strong>{issues.some(i => i.severity === "blocking") ? "Needs attention" : "✓"} · {label}</strong><Issues issues={issues} /></div>)}</div>
      <RunExperiment projectId={projectId} revision={state.revision} ready={state.code_generation_ready && !state.stale} dirty={Boolean(dirty)} conflict={conflict} saving={busy} onReload={onReload} />
    </Panel>
    <details className="panel"><summary>Saved Pipeline IR · {ir.ir_version}</summary><pre>{JSON.stringify(ir, null, 2)}</pre></details>
  </div>;
}
