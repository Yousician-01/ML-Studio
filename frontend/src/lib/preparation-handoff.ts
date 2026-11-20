import type { ColumnProfile, Profile } from "./api/profiles";

export type PreparationAction = "outliers" | "outlier-indicator" | "variance" | "exclude" | "missing" | "numeric" | "rare";
export type PreparationHandoff = { projectId: string; datasetId: string; revision: number; feature: string; action: PreparationAction; multiplier?: number };
export type OnPrepare = (handoff: PreparationHandoff) => void;
export function preparationActions(column: Pick<ColumnProfile, "role" | "semantic_type" | "physical_dtype">): PreparationAction[] {
  if (column.role === "target") return [];
  const numeric = column.semantic_type === "continuous" && /int|float|double|numeric/i.test(column.physical_dtype);
  const category = ["categorical", "binary"].includes(column.semantic_type);
  return [...(numeric ? ["outliers", "outlier-indicator", "variance", "numeric"] as const : []), ...(numeric || category ? ["missing"] as const : []), ...(category ? ["rare"] as const : []), "exclude"];
}
export function validateHandoff(value: PreparationHandoff, projectId: string, datasetId: string, revision: number): string | null {
  if (value.projectId !== projectId || value.datasetId !== datasetId || value.revision !== revision) return "Dataset or revision changed. Reload diagnostics before preparing this feature.";
  if (!["outliers", "outlier-indicator", "variance", "exclude", "missing", "numeric", "rare"].includes(value.action) || !value.feature) return "Unsupported preparation action.";
  if (value.multiplier !== undefined && (!Number.isFinite(value.multiplier) || value.multiplier < .1 || value.multiplier > 10)) return "IQR multiplier must be between 0.1 and 10.";
  return null;
}
export function correlatedPairs(correlation: Pick<Profile["correlation"], "columns" | "values" | "pair_counts">, threshold: number) {
  if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1) return [];
  return correlation.columns.flatMap((left, i) => correlation.columns.slice(i + 1).flatMap((right, j) => {
    const value = correlation.values[i]?.[i + j + 1];
    return typeof value === "number" && Number.isFinite(value) && Math.abs(value) >= threshold ? [{ left, right, value, count: correlation.pair_counts[i]?.[i + j + 1] ?? 0 }] : [];
  }));
}
