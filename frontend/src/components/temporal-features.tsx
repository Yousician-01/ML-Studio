"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/projects";
import type { PipelineIR, TemporalConfig, TemporalExpression, TemporalOperation, TemporalPreview, WorkingPipeline } from "@/lib/api/pipelines";
import { componentFeatures, periodicComponents, temporalCall, temporalOperations, temporalRecipe } from "@/lib/temporal";
import { Alert, Button, Panel } from "./ui";
import { useLivePipeline } from "./live-pipeline";

type ExpressionProps = { value: TemporalExpression; onChange: (value: TemporalExpression) => void; columns: string[]; references: string[]; depth?: number };

function ExpressionInput({ value, onChange, columns, references, depth = 0 }: ExpressionProps) {
  const first = (): TemporalExpression => ({ kind: "column", name: columns[0] ?? "" });
  const updateOperation = (operation: TemporalOperation) => {
    const binary = operation === "date_diff" || operation === "calendar_age";
    onChange(temporalCall(operation, Array.from({ length: binary ? 2 : 1 }, first), operation === "date_diff" ? { unit: "days" } : {}));
  };
  return <fieldset className="panel" aria-label={`Expression argument level ${depth + 1}`}>
    <label>Expression type<select value={value.kind} onChange={e => {
      const kind = e.target.value;
      onChange(kind === "column" ? first() : kind === "reference" ? { kind: "reference", name: references[0] ?? "" } : kind === "literal" ? { kind: "literal", value: "" } : temporalCall("month", [first()]));
    }}>
      <option value="column">Datetime source column</option><option value="reference">Derived feature</option><option value="literal">Fixed ISO date / timestamp</option>{depth < 7 && <option value="call">Temporal function</option>}
    </select></label>
    {(value.kind === "column" || value.kind === "reference") && <label>{value.kind === "column" ? "Source column" : "Derived reference"}<select value={value.name} onChange={e => onChange({ ...value, name: e.target.value })}><option value="">Choose a reference</option>{(value.kind === "column" ? columns : references).map(name => <option key={name}>{name}</option>)}</select></label>}
    {value.kind === "literal" && <label>Explicit reference datetime<input value={value.value} placeholder="2026-01-01T00:00:00Z" onChange={e => onChange({ ...value, value: e.target.value })} /></label>}
    {value.kind === "call" && <>
      <label>Operation<select value={value.operation} onChange={e => updateOperation(e.target.value as TemporalOperation)}>{temporalOperations.map(op => <option key={op}>{op}</option>)}</select></label>
      {value.operation === "date_diff" && <label>Duration unit<select value={value.parameters.unit ?? "days"} onChange={e => onChange({ ...value, parameters: { unit: e.target.value as "days" } })}>{["seconds", "minutes", "hours", "days"].map(unit => <option key={unit}>{unit}</option>)}</select></label>}
      {(value.operation === "date_diff" || value.operation === "calendar_age") && <p className="muted">{value.operation === "date_diff" ? "First argument minus second; negative durations are retained." : "Birth/event first, reference second; completed calendar years, not days / 365."}</p>}
      {value.arguments.map((argument, index) => <ExpressionInput key={index} value={argument} columns={columns} references={references} depth={depth + 1} onChange={next => onChange({ ...value, arguments: value.arguments.map((arg, i) => i === index ? next : arg) })} />)}
    </>}
  </fieldset>;
}

export function TemporalFeaturesEditor({ projectId, state, disabled, onSave, onDirtyChange, managed = false, initialSource, initialOperation = "month", initialMode = "guided", initialEncoding = "raw", initialFeature }: {
  projectId: string; state: WorkingPipeline; disabled: boolean; onSave: (ir: PipelineIR) => Promise<void>; onDirtyChange: (dirty: boolean) => void;
  managed?: boolean; initialSource?: string; initialOperation?: TemporalOperation; initialMode?: "guided" | "expression"; initialEncoding?: "raw" | "cyclical" | "both"; initialFeature?: string;
}) {
  const publish = useLivePipeline()?.publish;
  const columns = state.columns.filter(column => column.effective_semantic_type === "datetime" && column.name !== state.ir.target?.column).map(column => column.name);
  const [temporal, setTemporal] = useState<TemporalConfig>(state.ir.temporal ?? { version: "temporal-v1", sources: {}, features: [] });
  const chosenSource = initialSource && columns.includes(initialSource) ? initialSource : columns[0] ?? "";
  const edited = state.ir.temporal?.features.find(feature => feature.name === initialFeature);
  const [source, setSource] = useState(chosenSource);
  const [policy, setPolicy] = useState<TemporalConfig["sources"][string]>(state.ir.temporal?.sources[chosenSource] ?? { format: "ISO8601", naive: "reject", invalid: "reject" });
  const [mode, setMode] = useState<"guided" | "expression">(edited ? "expression" : initialMode);
  const [operation, setOperation] = useState<TemporalOperation>(initialOperation);
  const [encoding, setEncoding] = useState<"raw" | "cyclical" | "both">(initialEncoding);
  const [reference, setReference] = useState<TemporalExpression>({ kind: "literal", value: "" });
  const [unit, setUnit] = useState<"seconds" | "minutes" | "hours" | "days">("days");
  const [name, setName] = useState(edited?.name ?? "");
  const [expression, setExpression] = useState<TemporalExpression>(edited?.expression ?? temporalCall("month", [{ kind: "column", name: chosenSource }]));
  const [editing, setEditing] = useState<string | null>(edited?.name ?? null);
  const [excludeSources, setExcludeSources] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<{ signature: string; data: TemporalPreview } | null>(null);
  const candidate = temporalRecipe(state.ir, temporal, excludeSources);
  const signature = JSON.stringify(candidate);
  const current = preview?.signature === signature ? preview.data : null;
  const changed = JSON.stringify(state.ir.temporal ?? null) !== JSON.stringify(candidate.temporal ?? null) || JSON.stringify(state.ir.features) !== JSON.stringify(candidate.features);
  const binary = operation === "date_diff" || operation === "calendar_age";
  function changePolicy(next: typeof policy) {
    setPolicy(next);
    if (source) setTemporal({ ...temporal, sources: { ...temporal.sources, [source]: next } });
  }
  useEffect(() => {
    onDirtyChange(changed);
    return () => onDirtyChange(false);
  }, [changed, onDirtyChange]);
  useEffect(() => {
    if (managed) return;
    publish?.(changed ? { revision: state.revision, ir: JSON.parse(signature) as PipelineIR } : undefined);
    return () => publish?.(undefined);
  }, [changed, signature, state.revision, publish, managed]);
  useEffect(() => {
    if (!changed || managed) return;
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const navigate = (event: MouseEvent) => {
      const anchor = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!anchor || event.defaultPrevented || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("#") || new URL(href, window.location.href).href === window.location.href) return;
      if (!window.confirm("Discard unsaved temporal configuration and leave Prepare?")) { event.preventDefault(); event.stopImmediatePropagation(); }
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", navigate, true);
    return () => { window.removeEventListener("beforeunload", unload); document.removeEventListener("click", navigate, true); };
  }, [changed, managed]);

  function addFeature() {
    try {
      if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(name)) throw new Error("Use a name starting with a letter, containing only letters, numbers and underscores.");
      const next = mode === "expression" ? [{ name, expression }] : binary ? [{ name, expression: temporalCall(operation, operation === "calendar_age" ? [{ kind: "column", name: source }, reference] : [reference, { kind: "column", name: source }], operation === "date_diff" ? { unit } : {}) }] : componentFeatures(name, operation, source, encoding);
      const retained = temporal.features.filter(feature => feature.name !== editing);
      const occupied = new Set([...state.columns.filter(column => !state.ir.temporal?.features.some(feature => feature.name === column.name)).map(column => column.name), ...retained.map(feature => feature.name)]);
      if (next.some(feature => occupied.has(feature.name))) throw new Error("A source or derived feature already uses this name.");
      setTemporal({ ...temporal, sources: source ? { ...temporal.sources, [source]: policy } : temporal.sources, features: [...retained, ...next] });
      setName(""); setEditing(null); setError("");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not add feature."); }
  }

  async function loadPreview() {
    setBusy(true); setError("");
    try { setPreview({ signature, data: await api.temporalPreview(projectId, state.revision, candidate) }); }
    catch (err) { setError(err instanceof Error ? err.message : "Temporal preview unavailable."); }
    finally { setBusy(false); }
  }

  return <Panel title="Datetime feature engineering" description="Create explicit numeric/binary features. Raw CSV values remain unchanged; calendar extraction uses UTC.">
    {!columns.length && <p>Mark a non-target column as datetime in Data to configure temporal sources.</p>}
    <fieldset disabled={disabled || busy}>
      <legend>Source parsing</legend>
      <label>Datetime column<select value={source} onChange={e => { setSource(e.target.value); setPolicy(temporal.sources[e.target.value] ?? { format: "ISO8601", naive: "reject", invalid: "reject" }); }}><option value="">Select source</option>{columns.map(column => <option key={column}>{column}</option>)}</select></label>
      <p className="muted">Effective semantic type: datetime. Date-only values are midnight; timezone offsets are converted to UTC. Day of week: Monday 0, Sunday 6. Fixed naive references use UTC. No system clock is used.</p>
      <label>Format (ISO8601 or explicit strptime)<input value={policy.format} placeholder="%d/%m/%Y" onChange={e => changePolicy({ ...policy, format: e.target.value })} /></label>
      <label>Naive/date-only timestamps<select value={policy.naive} onChange={e => changePolicy({ ...policy, naive: e.target.value as "utc" | "reject" })}><option value="reject">Reject without timezone</option><option value="utc">Interpret explicitly as UTC</option></select></label>
      <label>Invalid dates<select value={policy.invalid} onChange={e => changePolicy({ ...policy, invalid: e.target.value as "reject" | "coerce" })}><option value="reject">Reject</option><option value="coerce">Coerce to missing</option></select></label>
      <Button disabled={!source} onClick={() => setTemporal({ ...temporal, sources: { ...temporal.sources, [source]: policy } })}>Apply source parsing</Button>
      <ul>{Object.keys(temporal.sources).map(name => <li key={name}>Configured source: <strong>{name}</strong> <Button onClick={() => { const sources = { ...temporal.sources }; delete sources[name]; setTemporal({ ...temporal, sources }); }}>Remove parsing policy for {name}</Button></li>)}</ul>
      <p className="muted">Configure each referenced source, including reference columns. Missing/invalid derived values require compatible imputation below. Raw datetime cannot be an estimator input.</p>
      <div className="actions"><Button aria-pressed={mode === "guided"} onClick={() => setMode("guided")}>Guided Mode</Button><Button aria-pressed={mode === "expression"} onClick={() => setMode("expression")}>Expression Mode</Button></div>
      <label>Output feature name<input value={name} onChange={e => setName(e.target.value)} placeholder="signup_month" /></label>
      <p className="muted">Builder inputs enter the recipe only when you add or replace a feature.</p>
      {mode === "guided" ? <>
        <label>Temporal operation<select value={operation} onChange={e => { setOperation(e.target.value as TemporalOperation); setEncoding("raw"); }}>{temporalOperations.filter(op => !op.startsWith("cyclic_")).map(op => <option key={op}>{op}</option>)}</select></label>
        {binary ? <>
          <p>{operation === "calendar_age" ? "Age: selected source is birth/event; reference is the second argument." : "Elapsed time / tenure / recency: reference minus selected source. Reverse operands in Expression Mode for time until an event."}</p>
          <ExpressionInput value={reference} onChange={setReference} columns={columns} references={temporal.features.map(feature => feature.name)} />
          {operation === "date_diff" && <label>Duration unit<select value={unit} onChange={e => setUnit(e.target.value as typeof unit)}>{["seconds", "minutes", "hours", "days"].map(value => <option key={value}>{value}</option>)}</select></label>}
        </> : <label>Component representation<select value={encoding} onChange={e => setEncoding(e.target.value as typeof encoding)}><option value="raw">Raw component</option>{periodicComponents.has(operation) && <><option value="cyclical">Cyclical sine + cosine</option><option value="both">Both</option></>}</select></label>}
      </> : <ExpressionInput value={expression} onChange={setExpression} columns={columns} references={temporal.features.map(feature => feature.name)} />}
      <div className="actions"><Button disabled={!name || (mode === "guided" && !source)} onClick={addFeature}>{editing ? "Replace feature" : "Add feature"}</Button>{editing && <Button onClick={() => { setEditing(null); setName(""); }}>Cancel feature edit</Button>}</div>
      <ul>{temporal.features.map(feature => <li key={feature.name}><strong>{feature.name}</strong> <code>{feature.expression.kind === "call" ? feature.expression.operation : feature.expression.kind}</code> <Button onClick={() => { setEditing(feature.name); setName(feature.name); setExpression(feature.expression); setMode("expression"); }}>Edit {feature.name}</Button> <Button onClick={() => setTemporal({ ...temporal, features: temporal.features.filter(item => item.name !== feature.name) })}>Remove {feature.name}</Button></li>)}</ul>
      <label className="check-label"><input type="checkbox" checked={excludeSources} onChange={e => setExcludeSources(e.target.checked)} />Exclude configured raw datetime sources from estimator input on save</label>
      <p role="status">{changed ? managed ? "Unapplied temporal changes. Preview, then Apply to the studio draft." : "Unsaved temporal changes. Preview, then save explicitly." : managed ? "Matches the current studio draft." : "Temporal configuration saved."}</p>
      <div className="actions"><Button onClick={() => void loadPreview()}>{busy ? "Calculating preview..." : "Preview temporal features"}</Button><Button disabled={!changed || !current || !!current.errors.length} onClick={() => void onSave(candidate)}>{managed ? "Apply temporal changes" : "Save temporal configuration"}</Button><Button disabled={!changed} onClick={() => { setTemporal(state.ir.temporal ?? { version: "temporal-v1", sources: {}, features: [] }); setExcludeSources(false); setPreview(null); setError(""); }}>Discard unsaved temporal changes</Button></div>
    </fieldset>
    {error && <Alert>{error}</Alert>}
    {current && <>
      {current.errors.map((message, index) => <Alert key={index}>{message}</Alert>)}
      {current.warnings.map((message, index) => <p className="muted" key={index}>{message}</p>)}
      <p>Preview: up to {current.limit} source rows; counts cover the source, not a test split.</p>
      {Object.entries(current.sources).map(([name, counts]) => <p key={name}><strong>{name}</strong>: {counts.missing_count} missing, {counts.invalid_count} invalid/disallowed, {counts.date_only_count} date-only.</p>)}
      <div className="table-scroll" role="region" tabIndex={0} aria-label="Derived feature preview"><table><thead><tr><th>Feature</th><th>Output type</th><th>Missing</th><th>Source sample values</th></tr></thead><tbody>{current.columns.map(column => <tr key={column.name}><th scope="row">{column.name}</th><td>{column.semantic_type}</td><td>{column.missing_count}</td><td>{column.values.map(value => value === null ? "Missing" : typeof value === "number" ? String(Number(value.toPrecision(6))) : String(value)).join(", ")}</td></tr>)}</tbody></table></div>
    </>}
  </Panel>;
}
