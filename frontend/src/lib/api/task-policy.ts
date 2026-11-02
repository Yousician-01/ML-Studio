import type { Column, ProjectTask } from "./projects";
import type { ParameterSchema, SplitIntent, PipelineIssue } from "./pipelines";
export const taskLabel = (task?: ProjectTask) => task === "regression" ? "Regression" : task === "multiclass_classification" ? "Multiclass Classification" : "Binary Classification";
// A hint only: the backend validates finite observed values and lossless conversion.
export const numericTargetCandidate = (column: Pick<Column, "physical_dtype">) => /^(u?int|float)\d+$/i.test(column.physical_dtype);
export function editedSplit(source: SplitIntent, parsed: Record<string, number | string | boolean | null>): SplitIntent {
  return {
    test_size: parsed.test_size === null ? null : Number(parsed.test_size) / 100,
    random_seed: parsed.random_seed as number | null,
    ...(Object.hasOwn(source, "stratify") ? { stratify: parsed.stratify as boolean | null } : {}),
  };
}
export function readinessGroups(issues: PipelineIssue[], regression: boolean, multiclass = false): [string, PipelineIssue[]][] {
  const groups: [string, PipelineIssue[]][] = [
    ["Dataset binding", issues.filter(i => i.scope === "pipeline" && i.code.startsWith("dataset"))],
    [regression ? "Numeric target" : multiclass ? "Target & class universe" : "Target & positive class", issues.filter(i => i.scope === "target" || i.field?.startsWith("target."))],
    ["Features & preparation", issues.filter(i => i.scope === "feature" || i.column !== null || i.code === "features_empty")],
    ["Data split", issues.filter(i => i.field?.startsWith("split"))],
    ["Model", issues.filter(i => i.field?.startsWith("model"))],
  ];
  const assigned = new Set(groups.flatMap(([, values]) => values));
  const remaining = issues.filter(i => !assigned.has(i));
  if (remaining.length) groups.push(["Other configuration & compatibility", remaining]);
  return groups;
}
export function parameterType(schema: ParameterSchema) {
  return schema.type ?? schema.anyOf?.find(item => item.type !== "null")?.type;
}
export function parseParameters(values: Record<string, string>, schemas: Record<string, ParameterSchema>) {
  const parsed: Record<string, number | boolean | string | null> = {};
  for (const [key, raw] of Object.entries(values)) {
    const schema = schemas[key];
    if (!schema) throw new Error(`${key}: unsupported parameter; reload configuration.`);
    if (!raw.trim()) {
      if (schema.anyOf?.some(item => item.type === "null")) { parsed[key] = null; continue; }
      throw new Error(`${key}: a value is required.`);
    }
    const type = parameterType(schema);
    if (type === "boolean") {
      if (raw !== "true" && raw !== "false") throw new Error(`${key}: choose true or false.`);
      parsed[key] = raw === "true";
    } else if (type === "string") parsed[key] = raw;
    else {
      const value = Number(raw);
      if (!Number.isFinite(value) || (type === "integer" && !Number.isSafeInteger(value))) throw new Error(`${key}: enter a finite ${type === "integer" ? "integer" : "number"}.`);
      if (schema.minimum !== undefined && value < schema.minimum) throw new Error(`${key}: minimum ${schema.minimum}.`);
      if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum) throw new Error(`${key}: must be greater than ${schema.exclusiveMinimum}.`);
      parsed[key] = value;
    }
  }
  return parsed;
}
