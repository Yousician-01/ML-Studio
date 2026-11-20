import type { OutlierFeature, PipelineIR } from "./api/pipelines";
import type { Column } from "./api/projects";

export const outlierDefaults = (source: string): OutlierFeature => ({ source, name: `${source}_capped`.replace(/[^A-Za-z0-9_]/g, "_"), multiplier: 1.5, tails: "both", indicator: null, missing: "preserve", invalid: "reject" });
export const numericFeature = (c: Pick<Column, "effective_semantic_type" | "physical_dtype">) => c.effective_semantic_type === "continuous" && /int|float|numeric|double/i.test(c.physical_dtype);
export function outlierRecipe(ir: PipelineIR, feature: OutlierFeature, columns: Pick<Column, "name">[], previous?: string, included = true, indicatorIncluded = true): PipelineIR {
  const existing = ir.outlier_treatment?.features ?? [];
  const old = existing.find(f => f.name === previous);
  const outputs = new Set(existing.flatMap(f => [f.name, ...(f.indicator ? [f.indicator] : [])]));
  const indicators = new Set(Object.values(ir.imputation?.columns ?? {}).map(c => c.indicator));
  if (feature.source === ir.target?.column || outputs.has(feature.source) || indicators.has(feature.source) || !columns.some(c => c.name === feature.source)) throw new Error("Choose an existing non-target numeric source, temporal, generalized or engineered feature; outlier chaining is unsupported.");
  if (!Number.isFinite(feature.multiplier) || feature.multiplier < .1 || feature.multiplier > 10) throw new Error("IQR multiplier must be between 0.1 and 10.");
  const occupied = new Set([...columns.map(c => c.name), ...Object.keys(ir.features), ...outputs, ...indicators]);
  if (old) { occupied.delete(old.name); if (old.indicator) occupied.delete(old.indicator); }
  const names = [feature.name, ...(feature.indicator ? [feature.indicator] : [])];
  if (new Set(names).size !== names.length || names.some(name => !/^[A-Za-z][A-Za-z0-9_]{0,199}$/.test(name) || occupied.has(name))) throw new Error("Output and indicator names must be valid, distinct and collision-free.");
  if (!previous && existing.length >= 64) throw new Error("At most 64 outlier treatments are supported.");
  const features = { ...ir.features };
  if (old && old.name !== feature.name) delete features[old.name];
  if (old?.indicator && old.indicator !== feature.indicator) delete features[old.indicator];
  features[feature.name] = { included, operations: old ? ir.features[old.name]?.operations ?? [] : [] };
  if (feature.indicator) features[feature.indicator] = { included: indicatorIncluded, operations: old?.indicator ? ir.features[old.indicator]?.operations ?? [] : [] };
  const removed = [old?.name !== feature.name ? old?.name : undefined, old?.indicator !== feature.indicator ? old?.indicator : undefined].filter(Boolean) as string[];
  const result: PipelineIR = { ...ir, features, outlier_treatment: { version: "outlier-treatment-v1", features: previous ? existing.map(f => f.name === previous ? structuredClone(feature) : f) : [...existing, structuredClone(feature)] } };
  return repairEligibility(result, removed);
}
function repairEligibility(ir: PipelineIR, removed: string[]): PipelineIR {
  if (!ir.feature_selection) return ir;
  const features = ir.feature_selection.features.filter(name => !removed.includes(name));
  return { ...ir, feature_selection: features.length ? { ...ir.feature_selection, features } : null };
}
/** Remove only new-stage dependents of deleted outputs; older definitions retain their repair flow. */
export function repairNewStages(ir: PipelineIR, removed: string[]): PipelineIR {
  let result = ir;
  for (const feature of ir.outlier_treatment?.features ?? []) if (removed.includes(feature.source)) result = removeOutlier(result, feature.name);
  return repairEligibility(result, removed);
}
export function removeOutlier(ir: PipelineIR, name: string): PipelineIR {
  const old = ir.outlier_treatment?.features.find(f => f.name === name);
  if (!old) return ir;
  const features = { ...ir.features }, remaining = ir.outlier_treatment!.features.filter(f => f.name !== name);
  delete features[name]; if (old.indicator) delete features[old.indicator];
  return repairEligibility({ ...ir, features, outlier_treatment: remaining.length ? { version: "outlier-treatment-v1", features: remaining } : null }, [name, ...(old.indicator ? [old.indicator] : [])]);
}
export function selectionRecipe(ir: PipelineIR, names: string[], threshold: number): PipelineIR {
  if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1e12) throw new Error("Variance threshold must be finite and between 0 and 1e12.");
  if (!names.length || names.length > 128 || new Set(names).size !== names.length || names.some(name => name === ir.target?.column || !ir.features[name]?.included)) throw new Error("Choose 1–128 distinct included numeric features.");
  return { ...ir, feature_selection: { version: "feature-selection-v1", method: "variance_threshold", stage: "post_preprocessing", features: [...names], threshold } };
}
