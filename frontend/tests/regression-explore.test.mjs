import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "./load-component.mjs";
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
const numeric = { count: 3, minimum: 2, maximum: 6, mean: 4, median: 4, standard_deviation: 2, q1: 3, q3: 5, unavailable_reason: null, histogram: [{ lower: 2, upper: 4, count: 1 }, { lower: 4, upper: 6, count: 2 }] };
const profile = () => ({ task: "regression", profile_version: "regression-source-profile-v1", dataset_id: "d", revision: 4, fingerprint: "sha256:test", source_integrity: "verified", original_filename: "synthetic.csv", row_count: 4, column_count: 2, target: { name: "y", physical_dtype: "float64", semantic_type: "continuous", observed_count: 3, missing_count: 1, distinct_count: 3, constant: false, numeric }, numeric_feature_count: 1, feature_offset: 0, feature_limit: 20, feature_options: [{ name: "x", physical_dtype: "int64", semantic_type: "continuous", role: "feature" }], relationship: { feature: "x", target: "y", paired_rows: 3, missing_pair_rows: 1, missing_feature_rows: 0, missing_target_rows: 1, pearson: 1, correlation_unavailable_reason: null, point_limit: 200, points: [{ x: 1, y: 2 }, { x: 2, y: 4 }, { x: 3, y: 6 }], sampling: "evenly-spaced-source-order-v1", scatter_unavailable_reason: null } });

test("regression source summary renders actual target statistics and bounded charts", () => {
  const { RegressionProfileView } = loadComponent("components/regression-explore.tsx");
  const html = render(RegressionProfileView, { profile: profile(), projectId: "p", onFeature: () => {}, onPage: () => {} });
  assert.match(html, /Observed target/); assert.match(html, /Standard deviation/); assert.match(html, /Quartile|Q1/);
  assert.match(html, /Histogram of y/); assert.match(html, /Target versus feature/); assert.match(html, /Pearson/);
  assert.match(html, /Numeric feature/); assert.match(html, /value="x"/);
  assert.doesNotMatch(html, /Class proportions|Positive class|held-out test|not yet available/);
});
test("no-target, constant and insufficient-pair states are explicit", () => {
  const { RegressionProfileView } = loadComponent("components/regression-explore.tsx");
  const data = profile(); data.target = null; data.relationship = null;
  assert.match(render(RegressionProfileView, { profile: data, projectId: "p", onFeature: () => {}, onPage: () => {} }), /Select a numeric target/);
  data.target = { ...profile().target, constant: true }; data.relationship = { ...profile().relationship, pearson: null, correlation_unavailable_reason: "Constant target; correlation unavailable." };
  const html = render(RegressionProfileView, { profile: data, projectId: "p", onFeature: () => {}, onPage: () => {} });
  assert.match(html, /Constant target/); assert.match(html, /correlation unavailable/);
});
test("scatter uses supplied points and exposes textual data without inventing samples", () => {
  const { TargetScatter } = loadComponent("components/regression-explore.tsx");
  const html = render(TargetScatter, { relationship: profile().relationship });
  assert.equal((html.match(/<circle/g) || []).length, 3);
  assert.match(html, /Source pair values/); assert.match(html, /evenly|source order/i);
});
test("numeric Train parse errors mark the exact input and reference the alert", () => {
  let index = 0;
  const react = { ...React, useState: initial => [index++ === 1 ? "alpha: a value is required." : initial, () => {}] };
  const { ConfigurationForm } = loadComponent("components/train.tsx", { react });
  const state = { revision: 1, ir: { model: { type: "ridge", parameters: { alpha: 1, fit_intercept: true } } }, model_catalogue: [{ id: "ridge", contextual_constraints: {}, parameter_schema: { properties: { alpha: { type: "number" }, fit_intercept: { type: "boolean" } } } }], issues: [] };
  const html = render(ConfigurationForm, { state, projectId: "p", kind: "model", disabled: false, onSave: async () => {}, onDirty: () => {}, onReset: () => {} });
  assert.match(html, /<input[^>]*id="train-alpha"[^>]*aria-invalid="true"[^>]*aria-describedby="help-alpha train-local-error"/);
});
test("feature selection forwards the selected name and profile client encodes it", async context => {
  const { RegressionProfileView } = loadComponent("components/regression-explore.tsx");
  let selected;
  const tree = RegressionProfileView({ profile: profile(), projectId: "p", onFeature: value => { selected = value; }, onPage: () => {} });
  function find(node) {
    if (!node || typeof node !== "object") return null;
    if (node.type === "select") return node;
    for (const child of React.Children.toArray(node.props?.children)) { const found = find(child); if (found) return found; }
    return null;
  }
  find(tree).props.onChange({ target: { value: "long feature / name" } });
  assert.equal(selected, "long feature / name");
  const { api } = loadComponent("lib/api/projects.ts");
  let url;
  context.mock.method(globalThis, "fetch", async next => { url = next; return new Response("{}", { status: 200 }); });
  await api.profile("p", { id: "d", revision: 4 }, 20, undefined, undefined, selected);
  assert.match(url, /offset=20/); assert.match(url, /feature=long%20feature%20%2F%20name/);
});
test("regression profile loading, source errors and insufficient pairs stay contextual", () => {
  const { RegressionExplore, RegressionProfileView } = loadComponent("components/regression-explore.tsx");
  assert.match(render(RegressionExplore, { projectId: "p", dataset: { id: "d", revision: 4 }, onReload: () => {} }), /Profiling verified regression source/);
  let index = 0;
  const react = { ...React, useState: initial => [index++ === 3 ? "Managed source integrity failed." : initial, () => {}] };
  const component = loadComponent("components/regression-explore.tsx", { react }).RegressionExplore;
  const error = render(component, { projectId: "p", dataset: { id: "d", revision: 4 }, onReload: () => {} });
  assert.match(error, /integrity failed/); assert.match(error, /Reload current Dataset/);
  const data = profile(); data.relationship.pearson = null; data.relationship.correlation_unavailable_reason = "At least two complete pairs required.";
  assert.match(render(RegressionProfileView, { profile: data, projectId: "p", onFeature: () => {}, onPage: () => {} }), /two complete pairs required/);
});
test("changing feature preserves selection control but hides previous relationship evidence", () => {
  const { RegressionProfileView } = loadComponent("components/regression-explore.tsx");
  const html = render(RegressionProfileView, { profile: profile(), projectId: "p", pending: true, selectedFeature: "x", onFeature: () => {}, onPage: () => {} });
  assert.match(html, /aria-label="Numeric feature"/);
  assert.match(html, /Loading selected feature relationship/);
  assert.doesNotMatch(html, /<circle|<dt>Pearson correlation/);
});
test("page transitions disable stale feature options; same-page requests keep selection available", () => {
  const { RegressionProfileView } = loadComponent("components/regression-explore.tsx");
  const props = { profile: profile(), projectId: "p", pending: true, onFeature: () => {}, onPage: () => {} };
  const page = render(RegressionProfileView, { ...props, pagePending: true });
  assert.match(page, /<select[^>]*disabled/);
  const samePage = render(RegressionProfileView, { ...props, pagePending: false });
  assert.doesNotMatch(samePage, /<select[^>]*disabled/);
});
