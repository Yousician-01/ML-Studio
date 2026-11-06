import test from "node:test";
import assert from "node:assert/strict";
import { componentFeatures, temporalRecipe } from "../src/lib/temporal.ts";
import { compareContext } from "../src/lib/api/evaluation-policy.ts";
import { evaluationRun } from "./fixtures/evaluation.mjs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "./load-component.mjs";

test("guided cyclic components use explicit expressions and deterministic names", () => {
  const features = componentFeatures("signup_month", "month", "signup", "both");
  assert.deepEqual(features.map(f => f.name), ["signup_month", "signup_month_sin", "signup_month_cos"]);
  assert.equal(features[1].expression.arguments[0].operation, "month");
  assert.throws(() => componentFeatures("week", "iso_week", "signup", "cyclical"));
});

test("temporal recipe preserves visual intent and explicitly controls raw inclusion", () => {
  const ir = { ir_version: "0.1", features: { date: { included: true, operations: [] } }, model: null, split: null, target: null, dataset: null };
  const temporal = { version: "temporal-v1", sources: { date: { format: "ISO8601", naive: "utc", invalid: "reject" } }, features: componentFeatures("month", "month", "date", "raw") };
  assert.equal(temporalRecipe(ir, temporal, false).features.date.included, true);
  const updated = temporalRecipe(ir, temporal, true);
  assert.equal(updated.features.date.included, false);
  assert.equal(updated.features.month.included, true);
  assert.equal(ir.features.date.included, true);
  const cleared = temporalRecipe(updated, { version: "temporal-v1", sources: {}, features: [] }, false);
  assert.equal(cleared.temporal, null);
  assert.equal(cleared.features.month, undefined);
  assert.throws(() => temporalRecipe(ir, { ...temporal, features: [...temporal.features, ...temporal.features] }, true));
});

test("frozen comparison does not claim matching temporal interpretation when parsing differs", () => {
  const a = evaluationRun("a"), b = evaluationRun("b");
  assert.equal(compareContext("project", [a, b]).compatible, true);
  a.execution_plan.temporal = { version: "temporal-v1", sources: { date: { naive: "utc", invalid: "reject" } }, features: [] };
  b.execution_plan.temporal = structuredClone(a.execution_plan.temporal);
  assert.equal(compareContext("project", [a, b]).compatible, true);
  b.execution_plan.temporal.sources.date.invalid = "coerce";
  assert.equal(compareContext("project", [a, b]).compatible, false);
});

test("Prepare temporal workspace exposes guided, expression, parsing and explicit preview/save controls", () => {
  const { TemporalFeaturesEditor } = loadComponent("components/temporal-features.tsx");
  const ir = { ir_version: "0.1", features: { date: { included: false, operations: [] } }, dataset: null, model: null, split: null, target: null };
  const html = renderToStaticMarkup(React.createElement(TemporalFeaturesEditor, { projectId: "p", state: { revision: 1, ir, columns: [{ name: "date", effective_semantic_type: "datetime" }] }, disabled: false, onSave: async () => {}, onDirtyChange: () => {} }));
  for (const text of ["Guided Mode", "Expression Mode", "Reject without timezone", "Coerce to missing", "Preview temporal features", "Save temporal configuration"]) assert.ok(html.includes(text), text);
  assert.match(html, /disabled=""[^>]*>Save temporal configuration/);
});
