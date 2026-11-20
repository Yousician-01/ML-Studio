"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/projects";
import type { EngineeringFeature, PipelineIR, TemporalPreview, WorkingPipeline } from "@/lib/api/pipelines";
import { engineeringCategorical, engineeringFitted, engineeringRecipe, newEngineeringFeature } from "@/lib/feature-engineering";
import { Alert, Button } from "./ui";

const numericMethods = ["log", "log1p", "sqrt", "reciprocal", "yeo_johnson", "box_cox", "quantile", "boundaries", "width", "quantile_bins"] as const;
export function EngineeringEditor({ projectId, state, initialSource, initialMethod = "log1p", initialFeature, disabled, onApply, onCancel, onDirtyChange }: {
  projectId: string; state: WorkingPipeline; initialSource?: string; initialMethod?: EngineeringFeature["method"]; initialFeature?: string; disabled: boolean;
  onApply: (ir: PipelineIR) => void; onCancel: () => void; onDirtyChange: (dirty: boolean) => void;
}) {
  const saved = state.ir.feature_engineering?.features.find(f => f.name === initialFeature);
  const [feature, setFeature] = useState<EngineeringFeature>(() => saved ?? newEngineeringFeature(initialMethod, initialSource ?? ""));
  const [preview, setPreview] = useState<{ signature: string; data: TemporalPreview } | null>(null);
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null), requestId = useRef(0);
  const outputNames = new Set(state.ir.feature_engineering?.features.map(f => f.name));
  const indicators = new Set(Object.values(state.ir.imputation?.columns ?? {}).map(c => c.indicator));
  const earlier = state.ir.feature_engineering?.features.slice(0, initialFeature ? state.ir.feature_engineering.features.findIndex(f => f.name === initialFeature) : undefined).filter(f => !engineeringFitted(f)).map(f => f.name) ?? [];
  const categoricalInput = feature.method === "rare" || feature.method === "ordinal";
  const inputs = state.columns.filter(c => c.name !== state.ir.target?.column && (!outputNames.has(c.name) || earlier.includes(c.name)) && !indicators.has(c.name) && (categoricalInput ? ["categorical", "binary"].includes(c.effective_semantic_type) : c.effective_semantic_type === "continuous" && /int|float|numeric|double/i.test(c.physical_dtype)));
  let candidate = state.ir, validation = "";
  try {
    if (!inputs.some(c => c.name === feature.source)) throw new Error("Choose a compatible source, temporal or generalized feature.");
    candidate = engineeringRecipe(state.ir, feature, state.columns, initialFeature);
  } catch (err) { validation = err instanceof Error ? err.message : "Review the transformation."; }
  const signature = JSON.stringify([state.revision, candidate, feature]);
  const current = preview?.signature === signature ? preview.data : null;
  const diagnostics = current?.feature_engineering?.[feature.name];
  const matched = !!diagnostics && current?.revision === state.revision && !current.errors.length;
  const changed = JSON.stringify(feature) !== JSON.stringify(saved ?? newEngineeringFeature(initialMethod, initialSource ?? ""));
  useEffect(() => { onDirtyChange(changed); }, [changed, onDirtyChange]);
  useEffect(() => () => { request.current?.abort(); requestId.current++; }, [signature]);
  useEffect(() => () => { onDirtyChange(false); }, [onDirtyChange]);
  function update(next: EngineeringFeature) { request.current?.abort(); requestId.current++; setPreview(null); setPending(""); setError(""); setFeature(next); }
  async function load() {
    if (disabled || validation) return;
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    const id = ++requestId.current;
    setPending(signature); setError(""); setPreview(null);
    try {
      const data = await api.temporalPreview(projectId, state.revision, candidate, controller.signal);
      if (!controller.signal.aborted && requestId.current === id) setPreview({ signature, data });
    } catch (err) { if (!controller.signal.aborted && requestId.current === id) setError(err instanceof Error ? err.message : "Preview unavailable."); }
    finally { if (requestId.current === id) setPending(""); }
  }
  return <div className="studio-editor"><fieldset disabled={disabled}>
    <legend>Advanced feature transformation</legend>
    <label>Transformation<select value={feature.method} onChange={e => update(newEngineeringFeature(e.target.value as EngineeringFeature["method"], feature.source))}>{[...numericMethods, "rare", "ordinal"].map(method => <option key={method} value={method}>{method.replaceAll("_", " ")}</option>)}</select></label>
    <label>Input feature<select value={feature.source} onChange={e => update({ ...feature, source: e.target.value })}><option value="">Choose compatible feature</option>{inputs.map(c => <option key={c.name}>{c.name}</option>)}</select></label>
    <label>Output feature<input maxLength={200} value={feature.name} onChange={e => update({ ...feature, name: e.target.value })} /></label>
    <p>Creates a new {engineeringCategorical(feature) ? "categorical" : "numeric"} feature. The original feature remains unchanged; review feature participation separately. {engineeringCategorical(feature) ? "One-hot encoding is configured on the output." : "Existing numeric scaling is available on the output."}</p>
    {"invalid" in feature && <><label>Invalid numeric domain<select value={feature.invalid} onChange={e => update({ ...feature, invalid: e.target.value as "reject" | "coerce" })}><option value="reject">Reject invalid values</option><option value="coerce">Mark invalid values as missing</option></select></label>{feature.invalid === "coerce" && <Alert tone="info">Invalid domains become missing. Configure an output imputer if the estimator requires complete values. No clipping or silent imputation is performed.</Alert>}</>}
    {(feature.method === "box_cox" || feature.method === "yeo_johnson") && <p>{feature.method === "box_cox" ? "Box-Cox requires strictly positive observed values; no automatic offset is added." : "Yeo-Johnson supports negative, zero and positive values."} At least two distinct observed training values are required. Missing values are preserved.</p>}
    {feature.method === "quantile" && <><label>Output distribution<select value={feature.distribution} onChange={e => update({ ...feature, distribution: e.target.value as "normal" | "uniform" })}><option value="uniform">Uniform</option><option value="normal">Normal</option></select></label><label>Quantiles (2–1000)<input type="number" min={2} max={1000} value={feature.quantiles} onChange={e => update({ ...feature, quantiles: Number(e.target.value) })} /></label><p>Deterministic full training partition estimation; count is capped to observed training rows. Inference extremes map to the fitted distribution bounds.</p></>}
    {feature.method === "boundaries" && <label>Ordered boundaries (comma separated)<input value={feature.boundaries.join(",")} onChange={e => update({ ...feature, boundaries: e.target.value.split(",").map(v => v.trim() ? Number(v) : NaN) })} /></label>}
    {"bins" in feature && <label>Requested bins (2–100)<input type="number" min={2} max={100} value={feature.bins} onChange={e => update({ ...feature, bins: Number(e.target.value) })} /></label>}
    {["boundaries", "width", "quantile_bins"].includes(feature.method) && <p>Labels are bin_0, bin_1, …; intervals include the left boundary and exclude the right. Underflow and overflow use the end bins; missing stays missing. {feature.method === "width" ? "Equal-width edges are learned from training minimum/maximum." : feature.method === "quantile_bins" ? "Quantile edges are learned from training rows. Duplicate edges are collapsed; fewer bins may result. Actual bin count is retained in the fitted transformer diagnostics." : "Explicit boundaries are stateless and include open-ended tails."}</p>}
    {feature.method === "rare" && <><label>Threshold type<select value={feature.min_count === null ? "fraction" : "count"} onChange={e => update({ ...feature, min_count: e.target.value === "count" ? 2 : null, min_frequency: e.target.value === "fraction" ? 0.02 : null })}><option value="fraction">Fraction of training rows</option><option value="count">Absolute training count</option></select></label><label>Minimum frequency<input type="number" step={feature.min_count === null ? "0.01" : "1"} value={feature.min_count ?? feature.min_frequency ?? ""} onChange={e => update({ ...feature, ...(feature.min_count === null ? { min_frequency: Number(e.target.value) } : { min_count: Number(e.target.value) }) })} /></label><label>Rare label<input maxLength={200} value={feature.rare_label} onChange={e => update({ ...feature, rare_label: e.target.value })} /></label><label>Unknown categories<select value={feature.unknown} onChange={e => update({ ...feature, unknown: e.target.value as typeof feature.unknown })}><option value="rare">Map to rare label</option><option value="preserve">Preserve for downstream encoder</option><option value="reject">Reject</option></select></label><p>Missing values remain missing. Retained typed categories become encoder-safe strings; ambiguous label collisions are rejected. Maximum 10,000 training categories.</p></>}
    {feature.method === "ordinal" && <><p>Define typed categories explicitly. Numeric output is not one-hot encoded.</p>{feature.mapping.map((item, i) => <fieldset key={i}><legend>Category {i + 1}</legend><label>Value type<select value={typeof item.value} onChange={e => update({ ...feature, mapping: feature.mapping.map((m, j) => i === j ? { ...m, value: e.target.value === "number" ? 0 : e.target.value === "boolean" ? false : "" } : m) })}><option value="string">Text</option><option value="number">Number</option><option value="boolean">Boolean</option></select></label><label>Category value{typeof item.value === "boolean" ? <select value={String(item.value)} onChange={e => update({ ...feature, mapping: feature.mapping.map((m, j) => i === j ? { ...m, value: e.target.value === "true" } : m) })}><option value="true">True</option><option value="false">False</option></select> : <input type={typeof item.value === "number" ? "number" : "text"} maxLength={1000} value={String(item.value)} onChange={e => update({ ...feature, mapping: feature.mapping.map((m, j) => i === j ? { ...m, value: typeof item.value === "number" ? Number(e.target.value) : e.target.value } : m) })} />}</label><label>Integer code<input type="number" step={1} value={item.code} onChange={e => update({ ...feature, mapping: feature.mapping.map((m, j) => i === j ? { ...m, code: Number(e.target.value) } : m) })} /></label><Button onClick={() => update({ ...feature, mapping: feature.mapping.filter((_, j) => j !== i) })}>Remove category</Button></fieldset>)}<Button disabled={feature.mapping.length >= 1000} onClick={() => update({ ...feature, mapping: [...feature.mapping, { value: "", code: feature.mapping.length }] })}>Add category</Button><label>Unknown categories<select value={feature.unknown} onChange={e => update({ ...feature, unknown: e.target.value as typeof feature.unknown, unknown_code: e.target.value === "code" ? -1 : null })}><option value="reject">Reject</option><option value="code">Use explicit code</option><option value="missing">Mark as missing</option></select></label>{feature.unknown === "code" && <label>Unknown code<input type="number" step={1} value={feature.unknown_code ?? ""} onChange={e => update({ ...feature, unknown_code: Number(e.target.value) })} /></label>}</>}
    <p>{engineeringFitted(feature) ? "Training-only fitting: this preview validates configuration and input domains, without computing learned parameters or transformed values." : "Stateless preview: actual source-derived values; no learned statistics."} Only earlier stateless engineering outputs may feed this stage; fitted-output chains and dependencies on later stages are unsupported. Quick source imputation happens later in its branch; use Advanced Imputation on the input or quick imputation on the output when needed.</p>
    {validation && <Alert>{validation}</Alert>}
    <div className="actions"><Button disabled={!!validation || pending === signature} onClick={() => void load()}>Preview / validate</Button><Button variant="primary" disabled={!!validation || !matched || pending === signature} onClick={() => { if (!validation && matched) { onDirtyChange(false); onApply(candidate); } }}>Apply transformation</Button></div>
    </fieldset><Button onClick={() => { request.current?.abort(); requestId.current++; onDirtyChange(false); onCancel(); }}>Cancel</Button>
    {pending === signature && <p role="status">Validating transformation…</p>}{error && <Alert>{error}</Alert>}{current?.errors.map((message, i) => <Alert key={i}>{message}</Alert>)}
    {diagnostics && <><p>{diagnostics.message}</p><p>Missing: {diagnostics.missing_count}; invalid/unknown: {diagnostics.invalid_count}. Output: {engineeringCategorical(feature) ? "categorical" : "continuous"}.</p>{diagnostics.invalid_count > 0 && <Alert tone="info">Review invalid values and downstream missing handling.</Alert>}</>}
    {current && !engineeringFitted(feature) && <div className="table-scroll"><table><caption>Actual source preview (up to 20 rows)</caption><thead><tr><th>{feature.source}</th><th>{feature.name}</th></tr></thead><tbody>{current.columns.find(c => c.name === feature.name)?.values.map((value, i) => { const raw = current.columns.find(c => c.name === feature.source)?.values[i]; return <tr key={i}><td>{raw === null ? "Missing" : raw === undefined ? "See source grid" : String(raw)}</td><td>{value === null ? "Missing" : String(value)}</td></tr>; })}</tbody></table></div>}
  </div>;
}
