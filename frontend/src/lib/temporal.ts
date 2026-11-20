import type { PipelineIR, TemporalConfig, TemporalExpression, TemporalOperation } from "./api/pipelines";

export const temporalOperations: TemporalOperation[] = ["year", "quarter", "month", "day", "day_of_week", "iso_week", "iso_year", "day_of_year", "hour", "minute", "second", "is_weekend", "is_leap_year", "is_month_start", "is_month_end", "is_quarter_start", "is_quarter_end", "is_year_start", "is_year_end", "date_diff", "calendar_age", "cyclic_sin", "cyclic_cos"];
export const periodicComponents = new Set(["quarter", "month", "day_of_week", "hour", "minute", "second"]);
export const temporalCall = (operation: TemporalOperation, args: TemporalExpression[], parameters = {}): TemporalExpression => ({ kind: "call", operation, arguments: args, parameters });

export function componentFeatures(name: string, operation: TemporalOperation, source: string, encoding: "raw" | "cyclical" | "both") {
  if (encoding !== "raw" && !periodicComponents.has(operation)) throw new Error("This calendar component has no supported fixed cyclical period.");
  const expression = temporalCall(operation, [{ kind: "column", name: source }]);
  return [
    ...(encoding !== "cyclical" ? [{ name, expression }] : []),
    ...(encoding !== "raw" ? [{ name: `${name}_sin`, expression: temporalCall("cyclic_sin", [expression]) }, { name: `${name}_cos`, expression: temporalCall("cyclic_cos", [expression]) }] : []),
  ];
}

export function temporalRecipe(ir: PipelineIR, temporal: TemporalConfig, excludeSources: boolean): PipelineIR {
  const names = temporal.features.map(feature => feature.name);
  if (new Set(names).size !== names.length) throw new Error("Derived feature names must be unique.");
  const features = { ...ir.features };
  for (const previous of ir.temporal?.features ?? []) if (!names.includes(previous.name)) delete features[previous.name];
  for (const feature of temporal.features) features[feature.name] ??= { included: true, operations: [] };
  if (excludeSources) for (const name of Object.keys(temporal.sources)) if (features[name]) features[name] = { ...features[name], included: false };
  return { ...ir, temporal: temporal.features.length || Object.keys(temporal.sources).length ? temporal : null, features };
}
