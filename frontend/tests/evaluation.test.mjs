import test from "node:test";
import assert from "node:assert/strict";
import { compareContext, comparisonSelection, integrityProblems, metricDelta, metricText } from "../src/lib/api/evaluation-policy.ts";

import { evaluationRun } from "./fixtures/evaluation.mjs";

test("zero is a metric; missing and non-finite values are unavailable", () => {
  assert.equal(metricText(0), "0.0000");
  for (const value of [null, undefined, NaN, Infinity]) assert.equal(metricText(value), "Unavailable");
});

test("selection requires exactly two distinct successful owned Runs", () => {
  const a = evaluationRun(), b = evaluationRun("b");
  assert.equal(comparisonSelection("project", [a, b]), null);
  for (const runs of [[], [a], [a, a], [a, b, evaluationRun("c")], [a, { ...b, project_id: "other" }], [a, { ...b, state: "FAILED" }], [a, { ...b, state: "RUNNING" }], [a, { ...b, result: null }]]) {
    assert.ok(comparisonSelection("project", runs));
    assert.equal(metricDelta("project", runs, "accuracy"), null);
  }
});

test("compatible contexts allow B minus A, not ranking or membership proof", () => {
  const a = evaluationRun(), b = evaluationRun("b");
  b.result.metrics.accuracy = .5;
  b.execution_plan.model.name = "RandomForestClassifier";
  b.execution_plan.features = [{ name: "x", operations: [{ name: "StandardScaler" }] }];
  const policy = compareContext("project", [a, b]);
  assert.equal(policy.compatible, true);
  assert.match(policy.notes.join(" "), /does not independently prove identical held-out row membership/);
  assert.equal(metricDelta("project", [a, b], "accuracy"), -.25);
  assert.equal(metricDelta("project", [a, b], "roc_auc"), null);
  b.dataset_id = "other-identity";
  assert.equal(compareContext("project", [a, b]).compatible, true);
  assert.match(compareContext("project", [a, b]).notes.join(" "), /identities differ/);
});

test("each frozen context mismatch independently suppresses deltas", () => {
  const mutations = [
    b => { b.summary.dataset_fingerprint = "sha256:other"; },
    b => { b.summary.target.column = "another"; },
    b => { b.summary.target.positive_class = { value_type: "integer", value: 1 }; },
    b => { b.result.confusion_matrix.labels.reverse(); },
    b => { b.execution_plan.source.missing_values = "different"; },
    b => { b.execution_plan.target.missing_value_policy = "different"; },
    ...["test_size", "random_seed", "stratify"].map(key => b => { b.execution_plan.split[key] = key === "stratify" ? false : .3; }),
    b => { b.execution_plan.implementation.libraries["scikit-learn"] = "other"; },
    b => { b.execution_plan.implementation.python = "other"; },
    b => { b.provenance.executor = "other"; },
    b => { b.execution_plan.generator = "other"; },
    b => { b.result.population.test = 5; },
    b => { b.result.confusion_matrix.values = [[2, 1], [1, 0]]; },
    b => { b.execution_plan.evaluation.zero_division = 1; },
    b => { b.execution_plan.runtime.result_schema = "other"; },
    b => { b.result.schema_version = "other"; },
    b => { b.execution_plan = null; },
  ];
  for (const mutate of mutations) {
    const a = evaluationRun(), b = evaluationRun("b");
    mutate(b);
    assert.equal(compareContext("project", [a, b]).compatible, false, mutate.toString());
    assert.equal(metricDelta("project", [a, b], "accuracy"), null);
  }
});

test("corrupt, missing or unverifiable artifacts exclude retained results from deltas", () => {
  for (const integrity of ["missing", "unavailable_or_corrupt", "unknown"]) {
    const a = evaluationRun(), b = evaluationRun("b");
    b.artifacts["result.json"].integrity = integrity;
    assert.deepEqual(integrityProblems(b), ["result.json"]);
    assert.equal(b.result.metrics.accuracy, .75);
    assert.equal(metricDelta("project", [a, b], "accuracy"), null);
  }
  const b = evaluationRun("b");
  delete b.artifacts["model.joblib"];
  assert.ok(integrityProblems(b).includes("model.joblib"));
  b.snapshot_error = "Frozen configuration corrupt.";
  assert.ok(integrityProblems(b).includes("frozen configuration"));
});
