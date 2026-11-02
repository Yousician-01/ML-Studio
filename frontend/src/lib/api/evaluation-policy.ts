import type { Metric, Run, RunResult, FrozenPlan } from "./runs";

export const metrics: { key: Metric; label: string }[] = [
  { key: "accuracy", label: "Accuracy" }, { key: "precision", label: "Precision" },
  { key: "recall", label: "Recall" }, { key: "f1", label: "F1" }, { key: "roc_auc", label: "ROC-AUC" },
];
export const regressionMetrics: { key: Metric; label: string; direction: string }[] = [
 { key: "mae", label: "MAE", direction: "Lower is better" }, { key: "mse", label: "MSE", direction: "Lower is better" },
 { key: "rmse", label: "RMSE", direction: "Lower is better" }, { key: "r2", label: "R²", direction: "Higher is better" },
];
export const multiclassMetrics: { key: Metric; label: string }[] = [
 { key: "accuracy", label: "Accuracy" }, { key: "precision_macro", label: "Macro precision" }, { key: "recall_macro", label: "Macro recall" }, { key: "f1_macro", label: "Macro F1" }, { key: "precision_weighted", label: "Weighted precision" }, { key: "recall_weighted", label: "Weighted recall" }, { key: "f1_weighted", label: "Weighted F1" },
];
export const knownResult = (result: unknown): result is RunResult => {
 if (!result || typeof result !== "object") return false;
 const r = result as Partial<RunResult>;
 return Boolean(r.metrics && r.population && (r.schema_version === "mlstudio-result-v1" || (r.schema_version === "mlstudio-result-v2" && r.task === "regression") || (r.schema_version === "mlstudio-result-v3" && r.task === "multiclass_classification")));
};
export const resultMetrics = (result: RunResult) => result.schema_version === "mlstudio-result-v3" ? multiclassMetrics : result.schema_version === "mlstudio-result-v2" ? regressionMetrics : metrics;
export const metricValue = (result: RunResult | null | undefined, key: Metric) => knownResult(result) ? (result.metrics as Partial<Record<Metric, number | null>>)[key] : null;
export const frozenModelName = (run: Run) => run.summary.model.estimator ?? run.summary.model.name ?? run.summary.model.type ?? "Unsupported model";
export const runTask = (run: Run) => run.summary.task ?? (run.result?.schema_version === "mlstudio-result-v3" ? "multiclass_classification" : run.result?.schema_version === "mlstudio-result-v2" ? "regression" : "binary_classification");
const record = (value: unknown): value is Record<string, unknown> => Boolean(value && typeof value === "object" && !Array.isArray(value));
// UI shape/version boundary only; never reconstruct or upgrade old evidence.
export function supportedPlan(value: unknown): value is FrozenPlan {
  if (!record(value) || !["0.1", "0.2", "0.3"].includes(String(value.plan_version))) return false;
  const regression = value.plan_version === "0.2";
  const multiclass = value.plan_version === "0.3";
  return value.ir_version === value.plan_version
    && value.generator === (multiclass ? "mlstudio-python-v3" : regression ? "mlstudio-python-v2" : "mlstudio-python-v1")
    && (!regression || value.task === "regression")
    && (!multiclass || value.task === "multiclass_classification")
    && record(value.runtime) && value.runtime.result_schema === (multiclass ? "mlstudio-result-v3" : regression ? "mlstudio-result-v2" : "mlstudio-result-v1")
    && record(value.source) && record(value.target) && record(value.split)
    && record(value.implementation) && record(value.implementation.libraries) && record(value.evaluation)
    && Array.isArray(value.features) && value.features.every(feature => record(feature)
      && typeof feature.name === "string" && Array.isArray(feature.operations)
      && feature.operations.every(operation => record(operation) && typeof operation.name === "string"));
}
export const classLabel = (value: { value_type: string; value: unknown }) => `${JSON.stringify(value.value)} (${value.value_type})`;
export const metricText = (value: number | null | undefined) => typeof value === "number" && Number.isFinite(value) ? value.toFixed(4) : "Unavailable";
export const successful = (run: Run) => run.state === "SUCCEEDED" && knownResult(run.result) && !run.result_error;

export function integrityProblems(run: Run): string[] {
  const artifacts = run.artifacts ?? {};
  const problems = Object.entries(artifacts).filter(([, ref]) => ref.integrity !== "verified").map(([name]) => name);
  if (successful(run)) {
    for (const name of ["dataset_source", "pipeline_ir.json", "execution_plan.json", "package.json", "generated_run.py", "result.json", "model.joblib"]) {
      if (!artifacts[name]) problems.push(name);
    }
  }
  if (run.snapshot_error) problems.push("frozen configuration");
  if (run.execution_plan && !supportedPlan(run.execution_plan)) problems.push("unsupported frozen configuration");
  return problems;
}

// Stable data comparison preserves scalar type tags and ignores JSON object key order.
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  return JSON.stringify(value) ?? "undefined";
}
const same = (a: unknown, b: unknown) => a != null && b != null && canonical(a) === canonical(b);

export function comparisonSelection(projectId: string, runs: Run[]): string | null {
  if (runs.length !== 2 || runs[0].id === runs[1].id) return "Select exactly two distinct Runs.";
  if (runs.some(run => run.project_id !== projectId)) return "Both Runs must belong to this Project.";
  if (runs.some(run => !successful(run))) return "Comparison requires two successful Runs with evaluation results.";
  return null;
}

export function compareContext(projectId: string, runs: Run[]) {
  const selection = comparisonSelection(projectId, runs);
  if (selection) return { compatible: false, reasons: [selection], notes: [] as string[] };
  const [a, b] = runs;
  const reasons: string[] = [];
  const check = (ok: boolean, reason: string) => { if (!ok) reasons.push(reason); };
  const coherent = (run: Run) => {
    const plan = run.execution_plan;
    if (!knownResult(run.result) || !supportedPlan(plan)) return false;
    const regression = run.result.schema_version === "mlstudio-result-v2";
    const multiclass = run.result.schema_version === "mlstudio-result-v3";
    return plan.plan_version === (multiclass ? "0.3" : regression ? "0.2" : "0.1")
      && plan.ir_version === plan.plan_version
      && plan.generator === (multiclass ? "mlstudio-python-v3" : regression ? "mlstudio-python-v2" : "mlstudio-python-v1")
      && plan.runtime.result_schema === run.result.schema_version
      && (!regression || (plan.task === "regression" && run.summary.task === "regression"))
      && (!multiclass || (plan.task === "multiclass_classification" && run.summary.task === "multiclass_classification"));
  };
  check(runs.every(coherent), "Frozen task, plan, generator or result protocol is unsupported or inconsistent.");
  check(!integrityProblems(a).length && !integrityProblems(b).length, "Artifact integrity is compromised or unavailable; metric deltas are excluded.");
  check(runTask(a) === runTask(b), "Tasks differ; classification and regression cannot be compared.");
  check(same(a.summary.dataset_fingerprint, b.summary.dataset_fingerprint), "Dataset fingerprints differ or are unavailable.");
  check(same(a.summary.target, b.summary.target) && ((runTask(a) === "regression" && runTask(b) === "regression") || (a.result?.schema_version === "mlstudio-result-v3" && b.result?.schema_version === "mlstudio-result-v3" && same(a.result.confusion_matrix.labels, b.result.confusion_matrix.labels)) || (a.result?.schema_version === "mlstudio-result-v1" && b.result?.schema_version === "mlstudio-result-v1" && same(a.result.confusion_matrix.labels, b.result.confusion_matrix.labels))), "Target or typed positive/negative class orientation differs.");
  const pa = a.execution_plan, pb = b.execution_plan;
  check(same(pa?.source, pb?.source) && same(pa?.target, pb?.target), "Frozen source/target interpretation differs or is unavailable.");
  check(same(pa?.split, pb?.split), "Frozen test size, seed or stratification differs or is unavailable.");
  const versions = (run: Run) => {
    const plan = run.execution_plan;
    if (!plan?.implementation || !plan.generator || !run.provenance.executor || !run.provenance.mlstudio || !plan.implementation.python || !plan.implementation.version || !plan.runtime?.version || !plan.plan_version || !plan.ir_version) return null;
    const libraries = Object.fromEntries(["pandas", "numpy", "scikit-learn", "scipy"].map(name => [name, plan.implementation.libraries?.[name]]));
    if (Object.values(libraries).some(value => !value)) return null;
    return { mlstudio: run.provenance.mlstudio, plan: plan.plan_version, ir: plan.ir_version, runtime: plan.runtime.version, generator: plan.generator, executor: run.provenance.executor, implementation: plan.implementation.version, python: plan.implementation.python, libraries };
  };
  check(same(versions(a), versions(b)), "Relevant generation, parsing, splitting or metric implementation versions differ or are unavailable.");
  const support = (run: Run) => run.result && run.result.schema_version !== "mlstudio-result-v2" ? run.result.confusion_matrix.values.map(row => row.reduce((sum, value) => sum + value, 0)) : "numeric target";
  check(same(a.result?.population, b.result?.population) && same(support(a), support(b)), "Held-out population counts or class support differ or are unavailable.");
  check(same(pa?.evaluation, pb?.evaluation) && same(pa?.runtime?.result_schema, pb?.runtime?.result_schema) && same(a.result?.schema_version, b.result?.schema_version), "Metric definitions or result protocols differ or are unavailable.");
  const notes = ["Matching context supports the deterministic split contract; it does not independently prove identical held-out row membership."];
  if (a.dataset_id !== b.dataset_id) notes.push("Dataset identities differ. Matching fingerprints establish identical source bytes, not a shared Dataset identity.");
  return { compatible: reasons.length === 0, reasons, notes };
}

export function metricDelta(projectId: string, runs: Run[], key: Metric): number | null {
  if (!compareContext(projectId, runs).compatible) return null;
  const a = metricValue(runs[0].result, key), b = metricValue(runs[1].result, key);
  return typeof a === "number" && Number.isFinite(a) && typeof b === "number" && Number.isFinite(b) ? b - a : null;
}
