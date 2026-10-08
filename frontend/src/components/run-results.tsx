import type { CSSProperties } from "react";
import type { Run, RunResult } from "@/lib/api/runs";
import { classLabel, integrityProblems, metrics, metricText } from "@/lib/api/evaluation-policy";
import { Alert, Panel } from "./ui";

export function IntegrityNotice({ run }: { run: Run }) {
  const problems = integrityProblems(run);
  return problems.length ? <Alert>Artifact integrity warning: {problems.join(", ")}. Metrics shown are retained SQLite results; artifact evidence cannot be verified. This Run is excluded from metric delta comparisons.</Alert> : null;
}

export function RunMetrics({ result }: { result: RunResult }) {
  return <><p className="muted">Held-out test population: {result.population.test} rows</p><dl className="run-metrics">{metrics.map(({ key, label }) => <div key={key}><dt>{label}</dt><dd>{metricText(result.metrics[key])}</dd></div>)}</dl>{result.metrics.roc_auc == null && <p className="muted">ROC-AUC: {result.roc_auc_unavailable_reason || "No availability reason was retained."}</p>}</>;
}

export function ConfusionMatrix({ result }: { result: RunResult }) {
  const matrix = result.confusion_matrix;
  const maximum = Math.max(1, ...matrix.values.flat());
  return <Panel title="Held-out confusion matrix" description="Actual classes by row; predicted classes by column. Negative then positive class order.">
    <div className="table-scroll"><table className="confusion-table"><caption className="sr-only">Frozen held-out counts: actual rows, predicted columns</caption><thead><tr><th scope="col">Actual / predicted</th>{matrix.labels.map((label, i) => <th scope="col" key={i}>{i ? "Positive" : "Negative"}<small>{classLabel(label)}</small></th>)}</tr></thead><tbody>{matrix.values.map((row, i) => <tr key={i}><th scope="row">{i ? "Positive" : "Negative"}<small>{classLabel(matrix.labels[i])}</small></th>{row.map((count, j) => <td key={j} style={{ "--cell-strength": 0.04 + count / maximum * 0.16 } as CSSProperties}><span>{[["TN", "FP"], ["FN", "TP"]][i][j]}</span><strong>{count}</strong></td>)}</tr>)}</tbody></table></div>
    <p className="muted">{result.population.source} source · {result.population.eligible} eligible · {result.population.training} training · {result.population.test} test rows</p>
  </Panel>;
}

export function FrozenRunContext({ run }: { run: Run }) {
  return <Panel title="Frozen experiment" description="Historical Run evidence, independent of current Project configuration.">
    <p className="wrap">Dataset {run.dataset_id}<br /><code>{run.summary.dataset_fingerprint}</code></p>
    <dl className="run-facts"><div><dt>Target</dt><dd>{run.summary.target.column}</dd></div><div><dt>Positive class</dt><dd>{classLabel(run.summary.target.positive_class)}</dd></div><div><dt>Negative class</dt><dd>{classLabel(run.summary.target.negative_class)}</dd></div><div><dt>Split</dt><dd>{run.summary.split.test_size * 100}% test · seed {run.summary.split.random_seed} · {run.summary.split.stratify ? "stratified" : "unstratified"}</dd></div></dl>
    <h3>{run.summary.model.name}</h3><dl className="run-facts">{Object.entries(run.summary.model.parameters).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{JSON.stringify(value)}</dd></div>)}</dl>
    {run.snapshot_error || !run.execution_plan ? <Alert>Frozen configuration unavailable. {run.snapshot_error}</Alert> : <><h3>Included features & preprocessing</h3><div className="table-scroll"><table><caption className="sr-only">Frozen feature configuration</caption><thead><tr><th>Feature</th><th>Semantic type</th><th>Ordered preprocessing</th></tr></thead><tbody>{run.execution_plan.features.map(feature => <tr key={feature.name}><th scope="row">{feature.name}</th><td>{feature.semantic_type}</td><td>{feature.operations.length ? feature.operations.map(operation => `${operation.name} ${JSON.stringify(operation.parameters)}`).join(" → ") : "Passthrough"}</td></tr>)}</tbody></table></div><details><summary>Resolved model parameters and original configured IR</summary><pre className="run-json">{JSON.stringify({ model: run.execution_plan.model, pipeline_ir: run.pipeline_ir }, null, 2)}</pre></details></>}
  </Panel>;
}
