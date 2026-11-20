import test from "node:test";
import assert from "node:assert/strict";
import { loadComponent } from "./load-component.mjs";

test("engineering actions and Applied Steps preserve save/reload, history and stage boundaries", () => {
  const { engineeringRecipe, newEngineeringFeature } = loadComponent("lib/feature-engineering.ts");
  const { appliedSteps, atStep, removeStep, columnActions, draftHistory, changeDraft, undoDraft, redoDraft } = loadComponent("lib/preparation.ts");
  const columns = [{ name: "x", source_order: 0, effective_semantic_type: "continuous", physical_dtype: "float64" }];
  const base = { ir_version: "0.2", features: { x: { included: true, operations: [] } } };
  const recipe = engineeringRecipe(base, { ...newEngineeringFeature("quantile", "x"), name: "ranked" }, columns);
  assert.equal(base.feature_engineering, undefined);
  assert.equal(recipe.features.ranked.included, true);
  const history = changeDraft(draftHistory(base), recipe);
  assert.deepEqual(undoDraft(history).present, base);
  assert.deepEqual(redoDraft(undoDraft(history)).present, recipe);
  const restored = JSON.parse(JSON.stringify(recipe));
  const step = appliedSteps(restored, columns).find(s => s.kind === "engineering");
  assert.match(step.stage, /Train-fitted/); assert.deepEqual(step.inputs, ["x"]);
  assert.equal(atStep(restored, columns, "source").feature_engineering, null);
  assert.deepEqual(atStep(restored, columns, step.id).feature_engineering, recipe.feature_engineering);
  assert.equal(removeStep(restored, step).features.ranked, undefined);
  assert.equal(columnActions(columns[0], false, true).some(a => a.id === "engineering-numeric"), true);
  assert.equal(columnActions({ effective_semantic_type: "categorical", physical_dtype: "object" }, false, true).some(a => a.id === "engineering-numeric"), false);
  assert.throws(() => engineeringRecipe(base, { ...newEngineeringFeature("sqrt", "x"), name: "x" }, columns), /name|colli/i);
});

test("guided engineering editor waits for matching diagnostics and preserves cancellation", async () => {
  const React = await import("react");
  let cursor = 0, refsCursor = 0, applied, canceled = false, resolve;
  const slots = [], refs = [];
  const { EngineeringEditor } = loadComponent("components/feature-engineering-editor.tsx", { react: { ...React, useEffect() {}, useRef(value) { return refs[refsCursor++] ??= { current: value }; }, useState(initial) { const i = cursor++; if (!(i in slots)) slots[i] = typeof initial === "function" ? initial() : initial; return [slots[i], value => { slots[i] = typeof value === "function" ? value(slots[i]) : value; }]; } }, "@/lib/api/projects": { api: { temporalPreview() { return new Promise(done => { resolve = done; }); } } } });
  const props = { projectId: "p", state: { revision: 2, ir: { features: { x: { included: true, operations: [] } } }, columns: [{ name: "x", physical_dtype: "float64", effective_semantic_type: "continuous" }] }, initialSource: "x", initialMethod: "quantile", disabled: false, onApply: value => { applied = value; }, onCancel: () => { canceled = true; }, onDirtyChange() {} };
  function nodes() { cursor = refsCursor = 0; const result = []; function visit(node) { if (!React.isValidElement(node)) return; result.push(node); React.Children.forEach(node.props.children, visit); } visit(EngineeringEditor(props)); return result; }
  const button = text => nodes().find(node => node.props.children === text);
  assert.equal(button("Apply transformation").props.disabled, true);
  button("Preview / validate").props.onClick();
  resolve({ revision: 2, columns: [], errors: [], warnings: [], feature_engineering: { x_quantile: { fitted: true, missing_count: 0, invalid_count: 0, message: "Training only" } } });
  await new Promise(done => setImmediate(done));
  assert.equal(button("Apply transformation").props.disabled, false);
  button("Apply transformation").props.onClick();
  assert.equal(applied.feature_engineering.features[0].method, "quantile");
  button("Cancel").props.onClick(); assert.equal(canceled, true);
});
