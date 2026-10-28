import type { CSSProperties } from "react";
import type { BinaryResult, MulticlassResult, Run, RunResult } from "@/lib/api/runs";
import type { ProjectTask } from "@/lib/api/projects";
import { classLabel, integrityProblems, metrics as binaryMetrics, regressionMetrics, multiclassMetrics, metricText, knownResult, frozenModelName, runTask, supportedPlan } from "@/lib/api/evaluation-policy";
import { Alert, Panel } from "./ui";

export function IntegrityNotice({ run }: { run: Run }) {
  const problems = integrityProblems(run);
  return problems.length ? <Alert>Artifact integrity warning: {problems.join(", ")}. Metrics shown are retained SQLite results; artifact evidence cannot be verified. This Run is excluded from metric delta comparisons.</Alert> : null;
}

export function RunMetrics({ result }: { result: RunResult }) {
  if (!knownResult(result)) return <Alert>Historical result protocol is unsupported.</Alert>;
  return <EvaluationMetrics task={result.schema_version === "mlstudio-result-v3" ? "multiclass_classification" : result.schema_version === "mlstudio-result-v2" ? "regression" : "binary_classification"} values={result.metrics} population={result.population} reason={result.schema_version === "mlstudio-result-v2" ? result.r2_unavailable_reason : result.schema_version === "mlstudio-result-v1" ? result.roc_auc_unavailable_reason : null} />;
}

export function EvaluationMetrics({ task, values, population, reason }: { task: ProjectTask; values: Partial<Record<string, number | null>>; population: { test: number; training?: number }; reason: string | null }) {
  const regression = task === "regression";
  return <><p className="muted">Held-out test population: {population.test} rows</p><dl className="run-metrics">{(task === "multiclass_classification" ? multiclassMetrics : regression ? regressionMetrics : binaryMetrics).map(({ key, label }) => <div key={key}><dt>{label}</dt><dd>{metricText(values[key])}</dd></div>)}</dl>{task === "binary_classification" && values.roc_auc == null && <p className="muted">ROC-AUC: {reason || "No availability reason was retained."}</p>}{regression && values.r2 == null && <p className="muted">R² unavailable: {reason === "constant_test_target" ? "The held-out target is constant." : reason === "test_population_too_small" ? "Fewer than two held-out rows." : reason || "No reason was retained."}</p>}{regression && <p className="muted">Lower MAE, MSE and RMSE are better; higher R² is better. {population.training !== undefined && `${population.training} training rows. `}R² may be negative.</p>}</>;
}

export function ConfusionMatrix({ result }: { result: RunResult }) {
  if (knownResult(result) && result.schema_version === "mlstudio-result-v3") return <MulticlassDetails result={result} />;
  if (!knownResult(result) || result.schema_version !== "mlstudio-result-v1") return null;
  return <ConfusionMatrixView matrix={result.confusion_matrix} population={result.population} />;
}

export function ConfusionMatrixView({ matrix, population, multiclass = false }: { matrix: { labels: BinaryResult["confusion_matrix"]["labels"][number][]; values: number[][] }; population?: BinaryResult["population"]; multiclass?: boolean }) {
  const maximum = Math.max(1, ...matrix.values.flat());
  return <Panel title="Held-out confusion matrix" description={multiclass ? "Actual classes by row; predicted classes by column. Deterministic typed class order." : "Actual classes by row; predicted classes by column. Negative then positive class order."}>
    <div className="table-scroll"><table className="confusion-table"><caption className="sr-only">Frozen held-out counts: actual rows, predicted columns</caption><thead><tr><th scope="col">Actual / predicted</th>{matrix.labels.map((label, i) => <th scope="col" key={i}>{multiclass ? `Class ${i + 1}` : i ? "Positive" : "Negative"}<small>{classLabel(label)}</small></th>)}</tr></thead><tbody>{matrix.values.map((row, i) => <tr key={i}><th scope="row">{multiclass ? `Class ${i + 1}` : i ? "Positive" : "Negative"}<small>{classLabel(matrix.labels[i])}</small></th>{row.map((count, j) => <td key={j} style={{ "--cell-strength": 0.04 + count / maximum * 0.16 } as CSSProperties}>{!multiclass && <span>{[["TN", "FP"], ["FN", "TP"]][i][j]}</span>}<strong>{count}</strong></td>)}</tr>)}</tbody></table></div>
    {population && <p className="muted">{population.source} source · {population.eligible} eligible · {population.training} training · {population.test} test rows</p>}
  </Panel>;
}

export function MulticlassDetails({ result }: { result: Pick<MulticlassResult, "confusion_matrix" | "per_class"> }) {
  return <><ConfusionMatrixView matrix={result.confusion_matrix} multiclass /><Panel title="Per-class metrics" description="Zero-division convention: undefined precision, recall and F1 are reported as 0. Support is the actual held-out count."><div className="table-scroll"><table><caption className="sr-only">Per-class metrics in frozen class order</caption><thead><tr><th>Class</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th></tr></thead><tbody>{result.per_class.map((row, i) => <tr key={i}><th scope="row">{classLabel(row.label)}</th><td>{metricText(row.precision)}</td><td>{metricText(row.recall)}</td><td>{metricText(row.f1)}</td><td>{row.support}</td></tr>)}</tbody></table></div></Panel></>;
}

export function FrozenRunContext({ run }: { run: Run }) {
  return <Panel title="Frozen experiment" description="Historical Run evidence, independent of current Project configuration.">
    <p className="wrap">Dataset {run.dataset_id}<br /><code>{run.summary.dataset_fingerprint}</code></p>
    <dl className="run-facts"><div><dt>Target</dt><dd>{run.summary.target.column}</dd></div>{runTask(run) !== "regression" && run.summary.target.positive_class && run.summary.target.negative_class && <><div><dt>Positive class</dt><dd>{classLabel(run.summary.target.positive_class)}</dd></div><div><dt>Negative class</dt><dd>{classLabel(run.summary.target.negative_class)}</dd></div></>}<div><dt>Split</dt><dd>{run.summary.split.test_size * 100}% test · seed {run.summary.split.random_seed} · {run.summary.split.stratify ? "stratified" : "unstratified"}</dd></div></dl>
    <h3>{frozenModelName(run)}</h3><dl className="run-facts">{Object.entries(run.summary.model.parameters ?? {}).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{JSON.stringify(value)}</dd></div>)}</dl>
    {run.snapshot_error || !supportedPlan(run.execution_plan) ? <Alert>Frozen configuration unavailable or unsupported. {run.snapshot_error}</Alert> : <><h3>Included features & preprocessing</h3><div className="table-scroll"><table><caption className="sr-only">Frozen feature configuration</caption><thead><tr><th>Feature</th><th>Semantic type</th><th>Ordered preprocessing</th></tr></thead><tbody>{run.execution_plan.features.map(feature => <tr key={feature.name}><th scope="row">{feature.name}</th><td>{feature.semantic_type}</td><td>{feature.operations.length ? feature.operations.map(operation => `${operation.name} ${JSON.stringify(operation.parameters)}`).join(" → ") : "Passthrough"}</td></tr>)}</tbody></table></div><details><summary>Resolved model parameters and original configured IR</summary><pre className="run-json">{JSON.stringify({ model: run.execution_plan.model, pipeline_ir: run.pipeline_ir }, null, 2)}</pre></details></>}
  </Panel>;
}
