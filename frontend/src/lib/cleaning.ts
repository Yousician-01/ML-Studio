import type { CleaningStep, DerivedExpression, PipelineIR } from "./api/pipelines";

export const cleaningLabels: Record<CleaningStep["kind"], string> = { normalize: "Normalize Missing Tokens", convert: "Change Data Type", replace: "Replace Values", datetime_fill: "Fill Missing Datetime", validate: "Validate Column", missing_filter: "Remove Rows Where This Column Is Missing", filter: "Filter Rows", deduplicate: "Remove Duplicate Rows" };
export const selectionStep = (step: CleaningStep) => ["missing_filter", "filter", "deduplicate"].includes(step.kind);
export function cleaningLabel(step: CleaningStep): string {
  if (step.kind === "missing_filter") return `${step.keep === "missing" ? "Keep" : "Remove"} rows: ${step.columns.join(", ")} ${step.mode} missing`;
  return `${cleaningLabels[step.kind]}${"column" in step ? `: ${step.column}` : step.kind === "deduplicate" ? `: ${step.columns.join(", ")}` : ""}`;
}
export function newCleaningStep(kind: CleaningStep["kind"], column: string): CleaningStep {
  const id = crypto.randomUUID(), policy = { format: "ISO8601", naive: "utc" as const, invalid: "reject" as const };
  const condition: DerivedExpression = { kind: "call", operation: "is_not_missing", arguments: [{ kind: "column", name: column }], parameters: {} };
  switch (kind) {
    case "normalize": return { id, kind, column, tokens: [], trim: true, case_sensitive: true };
    case "convert": return { id, kind, column, destination: "continuous", invalid: "reject", policy };
    case "replace": return { id, kind, column, match: "", value: null, condition: null };
    case "datetime_fill": return { id, kind, column, value: "", condition: null, policy };
    case "validate": return { id, kind, column, check: "required", action: "report", minimum: null, maximum: null, values: [], expected: null };
    case "missing_filter": return { id, kind, columns: column ? [column] : [], mode: "any", keep: "present" };
    case "filter": return { id, kind, condition, keep: "matches" };
    case "deduplicate": return { id, kind, columns: column ? [column] : [], keep: "first" };
  }
}
export function cleaningRecipe(ir: PipelineIR, steps: CleaningStep[]): PipelineIR {
  return { ...ir, cleaning: steps.length ? { version: "cleaning-v1", steps: structuredClone(steps) } : null };
}

/** Prevent JSON serialization from silently turning an incomplete numeric field into null. */
export function cleaningInputError(steps: CleaningStep[]): string | null {
  function finite(value: unknown): boolean {
    if (typeof value === "number") return Number.isFinite(value);
    if (Array.isArray(value)) return value.every(finite);
    return value !== null && typeof value === "object" ? Object.values(value).every(finite) : true;
  }
  return finite(steps) ? null : "Enter a finite number in every numeric field before previewing.";
}
