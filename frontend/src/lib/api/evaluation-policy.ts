import type { Metric, Run } from "./runs";

export const metrics: { key: Metric; label: string }[] = [
  { key: "accuracy", label: "Accuracy" }, { key: "precision", label: "Precision" },
  { key: "recall", label: "Recall" }, { key: "f1", label: "F1" }, { key: "roc_auc", label: "ROC-AUC" },
];
export const classLabel = (value: { value_type: string; value: unknown }) => `${JSON.stringify(value.value)} (${value.value_type})`;
export const metricText = (value: number | null | undefined) => typeof value === "number" && Number.isFinite(value) ? value.toFixed(4) : "Unavailable";
export const successful = (run: Run) => run.state === "SUCCEEDED" && Boolean(run.result);

export function integrityProblems(run: Run): string[] {
  const artifacts = run.artifacts ?? {};
  const problems = Object.entries(artifacts).filter(([, ref]) => ref.integrity !== "verified").map(([name]) => name);
  if (successful(run)) {
    for (const name of ["pipeline_ir.json", "execution_plan.json", "package.json", "generated_run.py", "result.json", "model.joblib"]) {
      if (!artifacts[name]) problems.push(name);
    }
  }
  if (run.snapshot_error) problems.push("frozen configuration");
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
  check(!integrityProblems(a).length && !integrityProblems(b).length, "Artifact integrity is compromised or unavailable; metric deltas are excluded.");
  check(same(a.summary.dataset_fingerprint, b.summary.dataset_fingerprint), "Dataset fingerprints differ or are unavailable.");
  check(same(a.summary.target, b.summary.target) && same(a.result?.confusion_matrix.labels, b.result?.confusion_matrix.labels), "Target or typed positive/negative class orientation differs.");
  const pa = a.execution_plan, pb = b.execution_plan;
  check(same(pa?.source, pb?.source) && same(pa?.target, pb?.target), "Frozen source/target interpretation differs or is unavailable.");
  check(same(pa?.split, pb?.split), "Frozen test size, seed or stratification differs or is unavailable.");
  const versions = (run: Run) => {
    const plan = run.execution_plan;
    if (!plan?.implementation || !plan.generator || !run.provenance.executor || !run.provenance.mlstudio || !plan.implementation.python || !plan.implementation.version || !plan.runtime?.version || !plan.plan_version || !plan.ir_version) return null;
    const libraries = Object.fromEntries(["pandas", "numpy", "scikit-learn"].map(name => [name, plan.implementation.libraries?.[name]]));
    if (Object.values(libraries).some(value => !value)) return null;
    return { mlstudio: run.provenance.mlstudio, plan: plan.plan_version, ir: plan.ir_version, runtime: plan.runtime.version, generator: plan.generator, executor: run.provenance.executor, implementation: plan.implementation.version, python: plan.implementation.python, libraries };
  };
  check(same(versions(a), versions(b)), "Relevant generation, parsing, splitting or metric implementation versions differ or are unavailable.");
  const support = (run: Run) => run.result?.confusion_matrix.values.map(row => row[0] + row[1]);
  check(same(a.result?.population, b.result?.population) && same(support(a), support(b)), "Held-out population counts or class support differ or are unavailable.");
  check(same(pa?.evaluation, pb?.evaluation) && same(pa?.runtime?.result_schema, pb?.runtime?.result_schema) && same(a.result?.schema_version, b.result?.schema_version), "Metric definitions or result protocols differ or are unavailable.");
  const notes = ["Matching context supports the deterministic split contract; it does not independently prove identical held-out row membership."];
  if (a.dataset_id !== b.dataset_id) notes.push("Dataset identities differ. Matching fingerprints establish identical source bytes, not a shared Dataset identity.");
  return { compatible: reasons.length === 0, reasons, notes };
}

export function metricDelta(projectId: string, runs: Run[], key: Metric): number | null {
  if (!compareContext(projectId, runs).compatible) return null;
  const a = runs[0].result?.metrics[key], b = runs[1].result?.metrics[key];
  return typeof a === "number" && Number.isFinite(a) && typeof b === "number" && Number.isFinite(b) ? b - a : null;
}
