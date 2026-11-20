"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/projects";
import type { OutlierFeature, PipelineIR, TemporalPreview, WorkingPipeline } from "@/lib/api/pipelines";
import { numericFeature, outlierDefaults, outlierRecipe, selectionRecipe } from "@/lib/outliers";
import { Alert, Button } from "./ui";

type EditorProps = { projectId: string; state: WorkingPipeline; initialSource?: string; disabled: boolean; onApply: (ir: PipelineIR) => void; onCancel: () => void; onDirtyChange: (dirty: boolean) => void };
function useDiagnostics(props: EditorProps, candidate: PipelineIR, validation: string) {
  const { onDirtyChange } = props;
  const [preview, setPreview] = useState<{ signature: string; data: TemporalPreview } | null>(null);
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null), requestId = useRef(0);
  const signature = JSON.stringify([props.projectId, props.state.revision, candidate]);
  const current = preview?.signature === signature ? preview.data : null;
  useEffect(() => () => { request.current?.abort(); requestId.current++; }, [signature]);
  useEffect(() => () => { onDirtyChange(false); }, [onDirtyChange]);
  async function load() {
    if (props.disabled || validation) return;
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    const id = ++requestId.current; setPending(signature); setPreview(null); setError("");
    try { const data = await api.temporalPreview(props.projectId, props.state.revision, candidate, controller.signal); if (!controller.signal.aborted && requestId.current === id) setPreview({ signature, data }); }
    catch (err) { if (!controller.signal.aborted && requestId.current === id) setError(err instanceof Error ? err.message : "Configuration validation unavailable."); }
    finally { if (requestId.current === id) setPending(""); }
  }
  function cancel() { request.current?.abort(); requestId.current++; props.onDirtyChange(false); props.onCancel(); }
  return { current, busy: pending === signature, error, load, cancel, matched: !!current && current.revision === props.state.revision && !current.errors.length };
}
function DiagnosticMessages({ current, error, busy }: { current: TemporalPreview | null; error: string; busy: boolean }) {
  return <>{busy && <p role="status">Validating configuration…</p>}{error && <Alert>{error}</Alert>}{current?.errors.map((message, i) => <Alert key={i}>{message}</Alert>)}</>;
}

export function OutlierEditor(props: EditorProps & { initialFeature?: string; indicatorOnly?: boolean; multiplier?: number }) {
  const { onDirtyChange } = props;
  const saved = props.state.ir.outlier_treatment?.features.find(f => f.name === props.initialFeature);
  const [feature, setFeature] = useState<OutlierFeature>(() => saved ?? { ...outlierDefaults(props.initialSource ?? ""), multiplier: props.multiplier ?? 1.5, ...(props.indicatorOnly ? { indicator: `${props.initialSource}_is_outlier` } : {}) });
  const [included, setIncluded] = useState(saved ? props.state.ir.features[saved.name]?.included ?? false : !props.indicatorOnly);
  const [indicatorIncluded, setIndicatorIncluded] = useState(saved?.indicator ? props.state.ir.features[saved.indicator]?.included ?? false : true);
  const outputs = new Set(props.state.ir.outlier_treatment?.features.flatMap(f => [f.name, ...(f.indicator ? [f.indicator] : [])]));
  const indicators = new Set(Object.values(props.state.ir.imputation?.columns ?? {}).map(c => c.indicator));
  const inputs = props.state.columns.filter(c => c.name !== props.state.ir.target?.column && numericFeature(c) && !outputs.has(c.name) && !indicators.has(c.name));
  let candidate = props.state.ir, validation = "";
  try { if (!inputs.some(c => c.name === feature.source)) throw new Error("Choose a compatible numeric feature available before outlier treatment."); candidate = outlierRecipe(props.state.ir, feature, props.state.columns, props.initialFeature, included, indicatorIncluded); }
  catch (err) { validation = err instanceof Error ? err.message : "Review outlier configuration."; }
  const diagnostics = useDiagnostics(props, candidate, validation);
  const info = diagnostics.current?.outlier_treatment?.[feature.name];
  const allowed = !validation && diagnostics.matched && !!info && !diagnostics.busy;
  const changed = JSON.stringify([candidate, feature]) !== JSON.stringify([props.state.ir, saved]);
  useEffect(() => { onDirtyChange(changed); }, [changed, onDirtyChange]);
  return <div className="studio-editor"><fieldset disabled={props.disabled}><legend>IQR clipping and shared outlier indicator</legend>
    <label>Numeric feature<select value={feature.source} onChange={e => setFeature({ ...feature, source: e.target.value })}><option value="">Choose feature</option>{inputs.map(c => <option key={c.name}>{c.name}</option>)}</select></label>
    <label>IQR multiplier<input type="number" min={.1} max={10} step={.1} value={feature.multiplier} onChange={e => setFeature({ ...feature, multiplier: e.target.value === "" ? NaN : Number(e.target.value) })} /></label>
    <label>Tails<select value={feature.tails} onChange={e => setFeature({ ...feature, tails: e.target.value as OutlierFeature["tails"] })}><option value="both">Both tails</option><option value="lower">Lower tail only</option><option value="upper">Upper tail only</option></select></label>
    <label>Clipped output name<input maxLength={200} value={feature.name} onChange={e => setFeature({ ...feature, name: e.target.value })} /></label>
    <label className="check-label"><input type="checkbox" checked={included} onChange={e => setIncluded(e.target.checked)} />Include clipped output in model input</label>
    <label className="check-label"><input type="checkbox" checked={feature.indicator !== null} onChange={e => setFeature({ ...feature, indicator: e.target.checked ? `${feature.source}_is_outlier` : null })} />Add outlier indicator using the same fitted fences</label>
    {feature.indicator !== null && <><label>Indicator name<input maxLength={200} value={feature.indicator} onChange={e => setFeature({ ...feature, indicator: e.target.value })} /></label><label className="check-label"><input type="checkbox" checked={indicatorIncluded} onChange={e => setIndicatorIncluded(e.target.checked)} />Include indicator in model input</label></>}
    <label>Missing inputs<select value={feature.missing} onChange={e => setFeature({ ...feature, missing: e.target.value as OutlierFeature["missing"] })}><option value="preserve">Preserve missing values</option><option value="reject">Reject missing values</option></select></label>
    <label>Nonfinite inputs<select value={feature.invalid} onChange={e => setFeature({ ...feature, invalid: e.target.value as OutlierFeature["invalid"] })}><option value="reject">Reject</option><option value="coerce">Mark as missing</option></select></label>
    <p>Fences fit training rows only, after feature engineering and before branch encoding/scaling. No exploratory fences are copied. At least two valid training observations are required. Zero IQR gives coincident fences; off-fence values are capped to that value in the selected tails. Missing inputs produce missing outputs/indicators unless rejected. No rows are removed and the source is unchanged.</p>
    <p>Review original feature participation separately. Use earlier Advanced Imputation for direct raw/derived inputs, or a branch imputer on the output; source quick imputation runs later and cannot fill this input.</p>
    {validation && <Alert>{validation}</Alert>}<div className="actions"><Button disabled={!!validation || diagnostics.busy} onClick={() => void diagnostics.load()}>Validate configuration</Button><Button variant="primary" disabled={!allowed} onClick={() => { if (allowed) { props.onDirtyChange(false); props.onApply(candidate); } }}>Apply outlier treatment</Button></div>
    </fieldset><Button onClick={diagnostics.cancel}>Cancel</Button><DiagnosticMessages {...diagnostics} />{info && <p>{info.message} Input missingness: {info.missing_count}. No fitted fence values are available before training.</p>}
  </div>;
}

export function FeatureSelectionEditor(props: EditorProps) {
  const { onDirtyChange } = props;
  const saved = props.state.ir.feature_selection;
  const [names, setNames] = useState(saved?.features ?? (props.initialSource && props.state.ir.features[props.initialSource]?.included ? [props.initialSource] : []));
  const [threshold, setThreshold] = useState(saved?.threshold ?? 0);
  const inputs = props.state.columns.filter(c => c.name !== props.state.ir.target?.column && numericFeature(c) && props.state.ir.features[c.name]?.included && !props.state.ir.features[c.name].operations.some(op => op.type === "encode"));
  let candidate = props.state.ir, validation = "";
  try { if (names.some(name => !inputs.some(c => c.name === name))) throw new Error("Remove unavailable/excluded eligibility entries or restore their feature definitions and participation."); candidate = selectionRecipe(props.state.ir, names, threshold); }
  catch (err) { validation = err instanceof Error ? err.message : "Review variance selection."; }
  const diagnostics = useDiagnostics(props, candidate, validation);
  const allowed = !validation && diagnostics.matched && !!diagnostics.current?.feature_selection && !diagnostics.busy;
  const changed = JSON.stringify([names, threshold]) !== JSON.stringify([saved?.features ?? [], saved?.threshold ?? 0]);
  useEffect(() => { onDirtyChange(changed); }, [changed, onDirtyChange]);
  const scaled = inputs.filter(c => names.includes(c.name) && props.state.ir.features[c.name].operations.some(op => op.type === "scale"));
  return <div className="studio-editor"><fieldset disabled={props.disabled}><legend>Variance threshold selection</legend><p>Population variance (ddof=0) is learned on training rows <strong>after each selected feature&apos;s configured imputation and scaling</strong>. Values must be finite and nonmissing. Keep variance strictly greater than the threshold. Categorical encoded outputs and other numeric features are unchanged.</p>
    <label>Variance threshold<input type="number" min={0} max={1e12} step="any" value={threshold} onChange={e => setThreshold(e.target.value === "" ? NaN : Number(e.target.value))} /></label>
    {!!scaled.length && <Alert tone="info">Scaled eligible features: {scaled.map(c => c.name).join(", ")}. Threshold units are their configured scaled units. Standard scaling typically gives nonconstant features variance near 1; this is not raw-source variance.</Alert>}
    <p>Eligible continuous model features (maximum 128). To exclude manually, use Feature Participation instead.</p>
    <div className="studio-participation">{inputs.map(c => <label key={c.name} className="check-label"><input type="checkbox" checked={names.includes(c.name)} onChange={e => setNames(e.target.checked ? [...names, c.name] : names.filter(n => n !== c.name))} />{c.name}</label>)}{names.filter(name => !inputs.some(c => c.name === name)).map(name => <Button key={name} onClick={() => setNames(names.filter(n => n !== name))}>Remove unavailable eligibility: {name}</Button>)}</div>
    <p>No mask or variance is fitted for this preview. Training fails explicitly if no eligible numeric feature survives. Saved inference reuses the fitted mask and preserves prediction row count.</p>
    {validation && <Alert>{validation}</Alert>}<div className="actions"><Button disabled={!!validation || diagnostics.busy} onClick={() => void diagnostics.load()}>Validate configuration</Button><Button variant="primary" disabled={!allowed} onClick={() => { if (allowed) { props.onDirtyChange(false); props.onApply(candidate); } }}>Apply feature selection</Button></div>
    </fieldset><Button onClick={diagnostics.cancel}>Cancel</Button><DiagnosticMessages {...diagnostics} />
  </div>;
}
