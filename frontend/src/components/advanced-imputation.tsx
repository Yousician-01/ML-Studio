"use client";

import { useEffect, useRef, useState } from "react";
import { api, type Column } from "@/lib/api/projects";
import type { ColumnImputation, ImputationFallback, ImputationRule, ImputationStrategy, PipelineIR, TemporalPreview, WorkingPipeline } from "@/lib/api/pipelines";
import { derivedCall } from "@/lib/derived";
import { imputationInputs, imputationRecipe, imputationStrategies } from "@/lib/imputation";
import { DerivedExpressionInput } from "./derived-features";
import { Alert, Button, Panel } from "./ui";

const newRule = (): ImputationRule => ({ condition: null, strategy: "constant", value: 0, group_by: [] });
type Scalar = ImputationRule["value"];
function ConstantInput({ value, onChange }: { value: Scalar; onChange: (value: Scalar) => void }) {
  const type = value === null ? "string" : typeof value;
  return <>
    <label>Constant type<select value={type} onChange={event => onChange(event.target.value === "number" ? 0 : event.target.value === "boolean" ? false : "")}><option value="string">Text</option><option value="number">Number</option><option value="boolean">Boolean</option></select></label>
    {type === "boolean" ? <label>Boolean constant<select value={String(value)} onChange={event => onChange(event.target.value === "true")}><option value="true">True</option><option value="false">False</option></select></label> : <label>Replacement constant<input type={type === "number" ? "number" : "text"} step={type === "number" ? "any" : undefined} maxLength={1000} value={typeof value === "number" && !Number.isFinite(value) ? "" : String(value ?? "")} onChange={event => onChange(type === "number" ? event.target.value === "" ? NaN : Number(event.target.value) : event.target.value)} /></label>}
  </>;
}

export function AdvancedImputationEditor({ projectId, state, column, disabled, onApply, onCancel, onDirtyChange }: {
  projectId: string; state: WorkingPipeline; column: Column; disabled: boolean;
  onApply: (ir: PipelineIR) => void; onCancel: () => void; onDirtyChange: (dirty: boolean) => void;
}) {
  const saved = state.ir.imputation?.columns[column.name];
  const initial: ColumnImputation = saved ?? { rules: [{ ...newRule(), strategy: imputationStrategies(column).includes("median") ? "median" : "most_frequent", value: null }], fallback: { strategy: "leave_missing", value: null }, indicator: null, previous_strategy: null };
  const [config, setConfig] = useState<ColumnImputation>(initial);
  const [editing, setEditing] = useState(0);
  const [error, setError] = useState("");
  const [pendingSignature, setPendingSignature] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ signature: string; data: TemporalPreview } | null>(null);
  const request = useRef<AbortController | null>(null), requestId = useRef(0);
  const inputs = imputationInputs(state.ir, state.columns), strategies = imputationStrategies(column);
  const groups = inputs.all.filter(name => name !== column.name);
  let candidate: PipelineIR | null = null, validation = "";
  try { candidate = imputationRecipe(state.ir, column.name, config, state.columns); }
  catch (err) { validation = err instanceof Error ? err.message : "Review the imputation configuration."; }
  const signature = JSON.stringify([projectId, state.revision, candidate, config]);
  const current = preview?.signature === signature ? preview.data : null;
  const diagnostics = current?.imputation?.[column.name];
  const busy = pendingSignature === signature;
  const matched = !!current && current.revision === state.revision && !current.errors.length && !!diagnostics;
  const changed = JSON.stringify(config) !== JSON.stringify(initial);
  useEffect(() => { onDirtyChange(changed); }, [changed, onDirtyChange]);
  useEffect(() => () => { request.current?.abort(); requestId.current++; onDirtyChange(false); }, [onDirtyChange]);
  useEffect(() => () => { request.current?.abort(); requestId.current++; }, [signature]);
  function invalidate() { request.current?.abort(); requestId.current++; setPreview(null); setPendingSignature(null); setError(""); }
  function update(next: ColumnImputation) { invalidate(); setConfig(next); }
  function updateRule(index: number, next: ImputationRule) { update({ ...config, rules: config.rules.map((rule, position) => position === index ? next : rule) }); }
  function move(index: number, offset: number) {
    const rules = [...config.rules], destination = index + offset;
    [rules[index], rules[destination]] = [rules[destination], rules[index]];
    update({ ...config, rules }); setEditing(destination);
  }
  async function loadPreview() {
    if (!candidate || disabled) return;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    const id = ++requestId.current;
    setPendingSignature(signature); setPreview(null); setError("");
    try {
      const data = await api.temporalPreview(projectId, state.revision, candidate, controller.signal);
      if (!controller.signal.aborted && requestId.current === id) setPreview({ signature, data });
    } catch (err) { if (!controller.signal.aborted && requestId.current === id) setError(err instanceof Error ? err.message : "Imputation preview unavailable."); }
    finally { if (requestId.current === id) setPendingSignature(null); }
  }
  return <Panel title={`Advanced Imputation: ${column.name}`} description="Fill only missing target cells. Ordered rules use the first successful fill; existing values are preserved.">
    <p>Target: {column.name} · {column.effective_semantic_type} · Missing values: {column.missing_count}</p>
    <fieldset disabled={disabled}>
      {config.rules.map((rule, index) => <fieldset className="panel" key={index} aria-label={`Imputation rule ${index + 1}`}>
        <legend>Rule {index + 1}: {rule.strategy.replaceAll("_", " ")}{rule.group_by.length ? ` by ${rule.group_by.join(", ")}` : ""}</legend>
        <div className="actions"><Button aria-label={`Edit rule ${index + 1}`} aria-expanded={editing === index} onClick={() => setEditing(index)}>Edit Rule</Button><Button aria-label={`Remove rule ${index + 1}`} onClick={() => { update({ ...config, rules: config.rules.filter((_, position) => position !== index) }); setEditing(Math.max(0, index - 1)); }}>Remove Rule</Button><Button aria-label={`Move rule ${index + 1} up`} disabled={index === 0} onClick={() => move(index, -1)}>Up</Button><Button aria-label={`Move rule ${index + 1} down`} disabled={index === config.rules.length - 1} onClick={() => move(index, 1)}>Down</Button></div>
        {editing === index && <>
          <label>Condition<select value={rule.condition === null ? "all" : "predicate"} onChange={event => updateRule(index, { ...rule, condition: event.target.value === "all" ? null : derivedCall("is_missing", [{ kind: inputs.references.includes(column.name) ? "reference" : "column", name: column.name }]) })}><option value="all">All remaining missing values</option><option value="predicate">When predicate is true</option></select></label>
          {rule.condition && <DerivedExpressionInput value={rule.condition} onChange={condition => updateRule(index, { ...rule, condition })} columns={inputs.columns} references={inputs.references} />}
          <label>Fill strategy<select value={rule.strategy} onChange={event => { const strategy = event.target.value as ImputationStrategy; updateRule(index, { ...rule, strategy, value: strategy === "constant" ? rule.value ?? (column.effective_semantic_type === "continuous" ? 0 : "") : null, group_by: strategy === "constant" ? [] : rule.group_by }); }}>{!strategies.includes(rule.strategy) && <option value={rule.strategy}>{rule.strategy} (review incompatible strategy)</option>}{strategies.map(strategy => <option value={strategy} key={strategy}>{strategy.replaceAll("_", " ")}</option>)}</select></label>
          {rule.strategy === "constant" ? <ConstantInput value={rule.value} onChange={value => updateRule(index, { ...rule, value })} /> : <label>Group by (up to 4; none means global)<select multiple value={rule.group_by} onChange={event => updateRule(index, { ...rule, group_by: Array.from(event.target.selectedOptions, option => option.value) })}>{[...groups, ...rule.group_by.filter(name => !groups.includes(name))].map(name => <option key={name} value={name}>{name}{!groups.includes(name) ? " (unavailable)" : ""}</option>)}</select></label>}
        </>}
      </fieldset>)}
      <Button disabled={config.rules.length >= 16} onClick={() => { update({ ...config, rules: [...config.rules, newRule()] }); setEditing(config.rules.length); }}>Add Rule</Button>
      <label>Final fallback<select value={config.fallback.strategy} onChange={event => { const strategy = event.target.value as ImputationFallback["strategy"]; update({ ...config, fallback: { strategy, value: strategy === "constant" ? column.effective_semantic_type === "continuous" ? 0 : "" : null } }); }}><option value="leave_missing">Leave missing and warn</option>{!strategies.includes(config.fallback.strategy as ImputationStrategy) && config.fallback.strategy !== "leave_missing" && <option value={config.fallback.strategy}>{config.fallback.strategy} (review incompatible strategy)</option>}{strategies.map(strategy => <option key={strategy} value={strategy}>{strategy === "constant" ? "Constant" : `Global training ${strategy.replaceAll("_", " ")}`}</option>)}</select></label>
      {config.fallback.strategy === "constant" && <ConstantInput value={config.fallback.value} onChange={value => update({ ...config, fallback: { ...config.fallback, value } })} />}
      <label><input type="checkbox" checked={config.indicator !== null} onChange={event => update({ ...config, indicator: event.target.checked ? `${column.name}_was_missing` : null })} />Create missingness indicator</label>
      {config.indicator !== null && <label>Indicator output name<input maxLength={200} value={config.indicator} onChange={event => update({ ...config, indicator: event.target.value })} /></label>}
      <p className="muted">Only explicitly true conditions match; missing predicates do not match. Missing group keys, unseen groups and unavailable group statistics continue to later rules or the explicit fallback. Grouping and predicates use values before imputation, including excluded context columns; the supervised target and missingness indicators cannot be inputs.</p>
      <p className="muted">Mean, median and most frequent values are fitted on training rows only. Fitted imputed values are unavailable in this configuration preview.</p>
      {validation && <p role="status">{validation}</p>}
      <div className="actions"><Button disabled={busy || !candidate} onClick={() => void loadPreview()}>{busy ? "Validating preview..." : "Preview imputation"}</Button><Button disabled={busy || !candidate || !matched} onClick={() => { if (!disabled && candidate && matched) { onDirtyChange(false); onApply(candidate); } }}>Apply imputation</Button></div>
    </fieldset>
    <Button onClick={() => { invalidate(); onDirtyChange(false); onCancel(); }}>Cancel</Button>
    {error && <Alert>{error}</Alert>}
    {current && <>
      {current.errors.map((message, index) => <Alert key={index}>{message}</Alert>)}
      {current.warnings.map((message, index) => <p className="muted" key={index}>{message}</p>)}
      {current.revision !== state.revision && <Alert>The project revision changed. Reload the preparation workspace before applying.</Alert>}
      {diagnostics && <div aria-label="Imputation configuration preview"><p>Missing source values: {diagnostics.missing_count}</p><p>Observational rule matches may overlap. These counts do not predict successful fills.</p><ol>{diagnostics.rule_matches.map((count, index) => <li key={index}>Rule {index + 1}: {count} matching missing rows</li>)}</ol>{config.indicator && <p>Original missingness indicator (first 20 rows): {diagnostics.indicator_values.slice(0, 20).join(", ")}</p>}</div>}
    </>}
  </Panel>;
}
