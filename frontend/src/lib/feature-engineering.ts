import type { EngineeringFeature, PipelineIR } from "./api/pipelines";
import type { Column } from "./api/projects";

export const engineeringFitted = (feature: EngineeringFeature) => ["yeo_johnson", "box_cox", "quantile", "width", "quantile_bins", "rare"].includes(feature.method);
export const engineeringCategorical = (feature: EngineeringFeature) => ["boundaries", "width", "quantile_bins", "rare"].includes(feature.method);
export const engineeringLabel = (feature: EngineeringFeature) => `${feature.method.replaceAll("_", " ")}: ${feature.source} → ${feature.name}`;

export function newEngineeringFeature(method: EngineeringFeature["method"], source: string): EngineeringFeature {
  const base = { source, name: `${source}_${method}`.replace(/[^A-Za-z0-9_]/g, "_") };
  if (["log", "log1p", "sqrt", "reciprocal"].includes(method)) return { ...base, method: method as "log", invalid: "reject" };
  if (method === "quantile") return { ...base, method, quantiles: 100, distribution: "uniform" };
  if (method === "boundaries") return { ...base, method, boundaries: [0, 10] };
  if (method === "width" || method === "quantile_bins") return { ...base, method, bins: 5 };
  if (method === "rare") return { ...base, method, min_count: null, min_frequency: 0.02, rare_label: "Other", unknown: "rare" };
  if (method === "ordinal") return { ...base, method, mapping: [{ value: "", code: 0 }], unknown: "reject", unknown_code: null };
  return { ...base, method: method as "yeo_johnson" | "box_cox" };
}

export function engineeringRecipe(ir: PipelineIR, feature: EngineeringFeature, columns: Pick<Column, "name">[], previous?: string): PipelineIR {
  if (!/^[A-Za-z][A-Za-z0-9_]{0,199}$/.test(feature.name)) throw new Error("Output name must start with a letter and contain letters, numbers or underscores (200 maximum).");
  const existing = ir.feature_engineering?.features ?? [];
  const outputNames = new Set(existing.map(f => f.name));
  if (feature.source === ir.target?.column || outputNames.has(feature.source) || !columns.some(c => c.name === feature.source) || Object.values(ir.imputation?.columns ?? {}).some(c => c.indicator === feature.source)) throw new Error("Choose an existing non-target source, temporal or generalized feature. Engineering outputs and missingness indicators cannot be inputs.");
  if ((columns.some(c => c.name === feature.name) || feature.name in ir.features || outputNames.has(feature.name)) && feature.name !== previous) throw new Error("Output name collides with an existing column or feature.");
  if (!previous && existing.length >= 64) throw new Error("At most 64 advanced features are supported.");
  if ("boundaries" in feature && (!feature.boundaries.length || feature.boundaries.length > 99 || feature.boundaries.some((v, i, values) => !Number.isFinite(v) || i > 0 && values[i - 1] >= v))) throw new Error("Provide 1–99 finite, strictly increasing boundaries.");
  if ("bins" in feature && (!Number.isInteger(feature.bins) || feature.bins < 2 || feature.bins > 100)) throw new Error("Choose 2–100 bins.");
  if ("quantiles" in feature && (!Number.isInteger(feature.quantiles) || feature.quantiles < 2 || feature.quantiles > 1000)) throw new Error("Choose 2–1000 quantiles.");
  if (feature.method === "rare" && (!feature.rare_label.trim() || feature.rare_label.length > 200 || (feature.min_count === null ? feature.min_frequency === null || !Number.isFinite(feature.min_frequency) || feature.min_frequency <= 0 || feature.min_frequency > 1 : !Number.isInteger(feature.min_count) || feature.min_count < 1 || feature.min_count > 1000000 || feature.min_frequency !== null))) throw new Error("Choose one valid count or fraction threshold and a distinct rare label.");
  if (feature.method === "ordinal") {
    if (!feature.mapping.length || feature.mapping.length > 1000 || new Set(feature.mapping.map(m => JSON.stringify([typeof m.value, m.value]))).size !== feature.mapping.length || new Set(feature.mapping.map(m => m.code)).size !== feature.mapping.length || feature.mapping.some(m => typeof m.value === "number" && !Number.isFinite(m.value) || typeof m.value === "string" && m.value.length > 1000 || !Number.isInteger(m.code) || Math.abs(m.code) > 2147483647)) throw new Error("Provide 1–1000 distinct typed category values and unique integer codes.");
    if (feature.unknown === "code" && (feature.unknown_code === null || !Number.isInteger(feature.unknown_code) || Math.abs(feature.unknown_code) > 2147483647 || feature.mapping.some(m => m.code === feature.unknown_code))) throw new Error("Use a distinct bounded integer for unknown categories.");
  }
  const features = { ...ir.features };
  const prior = previous ? features[previous] : undefined;
  if (previous && previous !== feature.name) delete features[previous];
  const was = existing.find(f => f.name === previous);
  const sameType = was && engineeringCategorical(was) === engineeringCategorical(feature);
  features[feature.name] = prior && sameType ? prior : { included: prior?.included ?? true, operations: engineeringCategorical(feature) ? [{ type: "encode", method: "one_hot" }] : [] };
  return { ...ir, features, feature_engineering: { version: "feature-engineering-v1", features: previous ? existing.map(f => f.name === previous ? structuredClone(feature) : f) : [...existing, structuredClone(feature)] } };
}
