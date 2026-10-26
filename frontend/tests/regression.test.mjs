import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "./load-component.mjs";
import { evaluationRun as makeRun } from "./fixtures/evaluation.mjs";

const policy = loadComponent("lib/api/evaluation-policy.ts");
const views = loadComponent("components/run-results.tsx");
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
function regression(id = "reg-one") {
  const run = makeRun(id);
  run.summary = { ...run.summary, task: "regression", result_schema: "mlstudio-result-v2", model: { type: "ridge", estimator: "Ridge", parameters: { alpha: 1, fit_intercept: true } }, target: { column: "amount", value_type: "numeric", missing_value_policy: "exclude_rows" } };
  run.result = { schema_version: "mlstudio-result-v2", task: "regression", metrics: { mae: 0, mse: 0, rmse: 0, r2: -0.5 }, r2_unavailable_reason: null, population: { source: 20, eligible: 20, training: 16, test: 4 } };
  run.execution_plan = { ...run.execution_plan, plan_version: "0.2", ir_version: "0.2", generator: "mlstudio-python-v2", task: "regression", target: run.summary.target, split: { test_size: 0.2, random_seed: 42, shuffle: true }, evaluation: { metrics: ["mae", "mse", "rmse", "r2"], definitions: "sklearn-regression-v1" }, runtime: { version: "cli-v1", result_schema: "mlstudio-result-v2" } };
  return run;
}
test("regression metrics preserve zero and negative R2 without binary evidence", () => {
  const html = render(views.RunMetrics, { result: regression().result });
  assert.match(html, /MAE/); assert.match(html, /0\.0000/); assert.match(html, /-0\.5000/);
  assert.doesNotMatch(html, /Accuracy|ROC-AUC|Precision|Recall/);
});
test("unavailable R2 carries reason, never zero", () => {
  const result = regression().result; result.metrics.r2 = null; result.r2_unavailable_reason = "constant_test_target";
  const html = render(views.RunMetrics, { result });
  assert.match(html, /Unavailable/); assert.match(html, /constant/i);
});
test("regression comparison uses numeric context, rejects cross task/protocol/integrity", () => {
  const a = regression("a"), b = regression("b"); b.result.metrics.mae = 2;
  assert.equal(policy.compareContext(a.project_id, [a,b]).compatible, true);
  assert.equal(policy.metricDelta(a.project_id, [a,b], "mae"), 2);
  assert.equal(policy.compareContext(a.project_id, [a,makeRun("binary")]).compatible, false);
  b.execution_plan.split.random_seed++; assert.equal(policy.metricDelta(a.project_id,[a,b],"mae"),null);
});
test("unknown result protocols are unavailable safely", () => {
  const run = regression(); run.result.schema_version = "future";
  assert.equal(policy.successful(run), false);
  const html = render(views.RunMetrics, { result: run.result });
  assert.match(html, /unsupported/i);
});
test("regression frozen context has no class orientation", () => {
  const html = render(views.FrozenRunContext, { run: regression() });
  assert.match(html, /Ridge/); assert.doesNotMatch(html, /Positive class|Negative class/);
});

test("catalogue parameter parsing uses schema types, supports fractional Ridge alpha and booleans", () => {
  const { parseParameters } = loadComponent("lib/api/task-policy.ts");
  const schema = { alpha: { type: "number", minimum: 0 }, fit_intercept: { type: "boolean" } };
  assert.deepEqual(parseParameters({ alpha: "0.25", fit_intercept: "false" }, schema), { alpha: .25, fit_intercept: false });
  assert.throws(() => parseParameters({ alpha: "", fit_intercept: "true" }, schema), /alpha/);
  assert.throws(() => parseParameters({ alpha: "Infinity", fit_intercept: "true" }, schema), /alpha/);
});
test("numeric target hints allow constants/two values but exclude bool/object dtypes", () => {
  const { numericTargetCandidate } = loadComponent("lib/api/task-policy.ts");
  assert.equal(numericTargetCandidate({ physical_dtype: "float64", unique_count: 1 }), true);
  assert.equal(numericTargetCandidate({ physical_dtype: "int64", unique_count: 2 }), true);
  assert.equal(numericTargetCandidate({ physical_dtype: "bool" }), false);
  assert.equal(numericTargetCandidate({ physical_dtype: "object" }), false);
});
test("Project creation offers immutable task selection, settings do not switch task", () => {
  const { ProjectForm } = loadComponent("components/project-form.tsx");
  const html = render(ProjectForm, { onSave: async () => {}, submitLabel: "Create" });
  assert.match(html, /Regression/); assert.match(html, /immutable|cannot be changed/i);
  const settings = render(ProjectForm, { initial: { name: "Reg", ml_objective: "regression" }, onSave: async () => {}, submitLabel: "Save" });
  assert.match(settings, /Regression/); assert.doesNotMatch(settings, /<select/);
});

test("Train drafts retain raw input and revision; navigation can stay or leave, saves block leaving", () => {
  const drafts = loadComponent("lib/train-drafts.ts");
  const draft = { revision: 7, section: "model", values: { alpha: "0.", fit_intercept: "false" } };
  drafts.writeDraft("p", draft);
  assert.deepEqual(drafts.readDraft("p"), draft);
  assert.equal(drafts.canLeaveDraft(true, false, () => false), false);
  assert.equal(drafts.canLeaveDraft(true, false, () => true), true);
  assert.equal(drafts.canLeaveDraft(false, true, () => true), false);
  drafts.clearDraft("p"); assert.equal(drafts.readDraft("p"), null);
});

test("regression controls render catalogue schema parameters without binary split controls", () => {
  const { ConfigurationForm } = loadComponent("components/train.tsx");
  const state = { revision: 3, issues: [], model_catalogue: [{ id: "ridge", name: "Ridge", contextual_constraints: {}, parameter_schema: { properties: { alpha: { type: "number", minimum: 0 }, fit_intercept: { type: "boolean" } } } }], ir: { ir_version: "0.2", model: { type: "ridge", parameters: { alpha: .25, fit_intercept: false } }, split: { test_size: .2, random_seed: 42 } } };
  const props = { state, disabled: false, projectId: "render-reg", onSave: async () => {}, onDirty: () => {}, onReset: () => {} };
  const model = render(ConfigurationForm, { ...props, kind: "model" });
  assert.match(model, /alpha/); assert.match(model, /0.25/); assert.match(model, /Fit intercept/);
  assert.match(model, /value="false" selected/); assert.match(model, /Minimum: 0/);
  const split = render(ConfigurationForm, { ...props, kind: "split" });
  assert.doesNotMatch(split, /Stratify|positive class/i);
  assert.match(split, /Test size/); assert.match(split, /Experiment seed/);
});
test("Data and regression Explore empty state show numeric target policy", () => {
  const { DataView } = loadComponent("components/data-view.tsx");
  const column = { name: "y", source_order: 0, physical_dtype: "float64", missing_count: 1, unique_count: 1, inferred_semantic_type: "continuous", effective_semantic_type: "continuous", semantic_override: null, role: "target", inference_version: "semantic-v2" };
  const dataset = { id: "data", original_filename: "synthetic.csv", row_count: 4, column_count: 1, missing_cells: 1, duplicate_rows: 0, size_bytes: 20, columns: [column], target_column: "y", target_classes: [], preview: [[1]], preview_limit: 20, fingerprint: "sha256:test" };
  const html = render(DataView, { project: { id: "p", ml_objective: "regression" }, dataset, onSaved: () => {}, onReload: () => {} });
  assert.match(html, /numeric candidate/); assert.match(html, /Constant and two-valued/);
  assert.match(html, /3 observed/); assert.match(html, /1 missing/);
  assert.doesNotMatch(html, /Choose the positive class|not a binary target/);
  const { Explore } = loadComponent("components/explore.tsx");
  const limited = render(Explore, { projectId: "p", task: "regression", dataset: null, onReload: () => {} });
  assert.match(limited, /No Dataset/); assert.doesNotMatch(limited, /<svg|<table/);
});
test("each regression context mismatch suppresses deltas; unavailable R2 has no delta", () => {
  const mutations = [
    b => { b.summary.dataset_fingerprint = "other"; },
    b => { b.summary.target.column = "other"; },
    b => { b.execution_plan.source.encoding = "other"; },
    b => { b.execution_plan.split.test_size = .3; },
    b => { b.execution_plan.implementation.libraries.numpy = "other"; },
    b => { b.execution_plan.evaluation.definitions = "other"; },
    b => { b.result.population.test = 9; },
    b => { b.artifacts["dataset_source"].integrity = "missing"; },
    b => { b.result_error = "Unsupported protocol"; },
    b => { b.execution_plan.plan_version = "0.1"; },
  ];
  for (const mutate of mutations) { const a = regression("a"), b = regression("b"); mutate(b); assert.equal(policy.metricDelta(a.project_id, [a,b], "mae"), null); }
  const a = regression("a"), b = regression("b"); b.result.metrics.r2 = null;
  assert.equal(policy.metricDelta(a.project_id, [a,b], "r2"), null);
  const { EvaluationComparison } = loadComponent("components/evaluate.tsx");
  const html = render(EvaluationComparison, { projectId: a.project_id, runs: [a,b] });
  assert.match(html, /Lower is better/); assert.match(html, /Higher is better/);
  assert.doesNotMatch(html, /confusion matrix|winner is [AB]/i);
});
test("two equally mismatched frozen protocol contexts do not become comparable", () => {
  const a = regression("a"), b = regression("b");
  a.execution_plan.plan_version = b.execution_plan.plan_version = "0.1";
  assert.equal(policy.compareContext(a.project_id, [a,b]).compatible, false);
});
test("editing binary stratification persists false; regression never gains stratification", () => {
  const { editedSplit } = loadComponent("lib/api/task-policy.ts");
  assert.deepEqual(editedSplit({ stratify: true }, { test_size: 20, random_seed: 42, stratify: false }), { test_size: .2, random_seed: 42, stratify: false });
  assert.deepEqual(editedSplit({}, { test_size: 20, random_seed: 42 }), { test_size: .2, random_seed: 42 });
});
test("Workspace passes regression task to Explore and avoids classification profiling", () => {
  let index = 0;
  const project = { id: "p", name: "Regression", ml_objective: "regression", active_dataset_id: "d", revision: 1 };
  const react = { ...React, useEffect: () => {}, useState: initial => [index++ === 0 ? project : index === 3 ? false : initial, () => {}] };
  const { Workspace } = loadComponent("components/workspace.tsx", {
    react, "next/navigation": { useRouter: () => ({}), useSearchParams: () => new URLSearchParams("view=explore") },
  });
  const html = render(Workspace, { projectId: "p" });
  assert.match(html, /Regression Explore/);
  assert.doesNotMatch(html, /Profiling source observations/);
});
test("Train readiness displays target-scoped training blockers and constant R2 warnings", () => {
  const { readinessGroups } = loadComponent("lib/api/task-policy.ts");
  const issues = [{ code: "eligible_observations", scope: "train", field: "target.column", severity: "blocking", column: null, message: "Too few rows" }, { code: "r2_constant_target", scope: "train", field: "target.column", severity: "non_blocking", column: null, message: "Constant target" }, { code: "library_context", scope: "train", field: null, column: null, severity: "blocking", message: "Environment mismatch" }];
  const groups = readinessGroups(issues, true);
  assert.equal(groups.find(([label]) => label === "Numeric target")[1].length, 2);
  assert.equal(new Set(groups.flatMap(([, values]) => values)).size, 3);
});
test("unknown or malformed frozen plans warn rather than crash result rendering or comparison", () => {
  for (const execution_plan of [{ plan_version: "future" }, { plan_version: "0.2", features: [{}] }]) {
    const a = regression("a"), b = regression("b"); a.execution_plan = execution_plan; b.execution_plan = structuredClone(execution_plan);
    const html = render(views.FrozenRunContext, { run: a });
    assert.match(html, /unsupported|unavailable/i);
    assert.equal(policy.compareContext(a.project_id, [a,b]).compatible, false);
  }
});
