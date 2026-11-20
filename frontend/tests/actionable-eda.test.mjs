import test from "node:test";
import assert from "node:assert/strict";
import { loadComponent } from "./load-component.mjs";

test("EDA handoff is typed, revision-bound, compatible and never carries learned fences", () => {
  const { preparationActions, validateHandoff, correlatedPairs } = loadComponent("lib/preparation-handoff.ts");
  const numeric = { name: "income", semantic_type: "continuous", physical_dtype: "float64", role: "feature" };
  assert.ok(preparationActions(numeric).includes("outliers"));
  assert.ok(!preparationActions({ ...numeric, role: "target" }).length);
  assert.ok(!preparationActions({ ...numeric, semantic_type: "categorical" }).includes("outliers"));
  const body = { projectId: "p", datasetId: "d", revision: 3, feature: "income", action: "outliers", multiplier: 1.5 };
  assert.equal(validateHandoff(body, "p", "d", 3), null);
  assert.match(validateHandoff({ ...body, revision: 2 }, "p", "d", 3), /changed/);
  assert.equal(body.lower_fence, undefined);
  assert.equal(correlatedPairs({ columns: ["a", "b"], values: [[1, -.95], [-.95, 1]], pair_counts: [[3, 3], [3, 3]] }, .9).length, 1);
});

test("outlier and variance Applied Steps survive history, save/reload and explicit repair", () => {
  const { outlierRecipe, selectionRecipe, removeOutlier, outlierDefaults } = loadComponent("lib/outliers.ts");
  const { appliedSteps, atStep, removeStep, draftHistory, changeDraft, undoDraft, redoDraft } = loadComponent("lib/preparation.ts");
  const columns = [{ name: "x", source_order: 0, effective_semantic_type: "continuous", physical_dtype: "float64" }];
  const base = { ir_version: "0.2", features: { x: { included: true, operations: [] } } };
  const first = outlierRecipe(base, { ...outlierDefaults("x"), name: "capped", indicator: "flag" }, columns, undefined, false, true);
  assert.equal(first.features.capped.included, false); assert.equal(first.features.flag.included, true);
  const active = { ...first, features: { ...first.features, capped: { included: true, operations: [] } } };
  const selected = selectionRecipe(active, ["capped"], .01);
  const stored = JSON.parse(JSON.stringify(selected));
  const steps = appliedSteps(stored, columns), outlier = steps.find(s => s.kind === "outlier"), selection = steps.find(s => s.kind === "variance");
  assert.ok(steps.indexOf(outlier) < steps.indexOf(selection));
  assert.equal(atStep(stored, columns, "source").outlier_treatment, null);
  assert.equal(atStep(stored, columns, outlier.id).feature_selection, null);
  assert.deepEqual(removeStep(stored, selection).outlier_treatment, stored.outlier_treatment);
  assert.equal(removeOutlier(stored, "capped").feature_selection, null, "removing output repairs its eligibility without another exclusion list");
  const history = changeDraft(draftHistory(base), stored);
  assert.deepEqual(undoDraft(history).present, base); assert.deepEqual(redoDraft(undoDraft(history)).present, stored);
  const upstream = { ...stored, derived: { version: "derived-v1", features: [{ name: "derived_x", expression: { kind: "column", name: "x" } }] }, features: { ...stored.features, derived_x: { included: true, operations: [] } }, outlier_treatment: { ...stored.outlier_treatment, features: [{ ...stored.outlier_treatment.features[0], source: "derived_x" }] } };
  const producer = appliedSteps(upstream, columns).find(s => s.kind === "derived");
  assert.throws(() => removeStep(upstream, producer), /dependent/);
  const removed = removeOutlier({ ...upstream, feature_selection: null }, "capped");
  assert.equal(removed.outlier_treatment, null);
  assert.equal(removed.feature_selection, null);
  assert.equal(removed.features.capped, undefined);
});

test("outlier editor requires matching unfitted diagnostics before Apply and supports Cancel", async () => {
  const React = await import("react");
  let cursor = 0, refsCursor = 0, resolve, applied, canceled = false;
  const slots = [], refs = [];
  const { OutlierEditor } = loadComponent("components/outlier-editors.tsx", { react: { ...React, useEffect() {}, useRef(value) { return refs[refsCursor++] ??= { current: value }; }, useState(initial) { const i = cursor++; if (!(i in slots)) slots[i] = typeof initial === "function" ? initial() : initial; return [slots[i], value => { slots[i] = typeof value === "function" ? value(slots[i]) : value; }]; } }, "@/lib/api/projects": { api: { temporalPreview() { return new Promise(done => { resolve = done; }); } } } });
  const props = { projectId: "p", state: { revision: 3, ir: { features: { x: { included: true, operations: [] } } }, columns: [{ name: "x", physical_dtype: "float64", effective_semantic_type: "continuous" }] }, initialSource: "x", disabled: false, onApply: value => { applied = value; }, onCancel: () => { canceled = true; }, onDirtyChange() {} };
  function elements() { cursor = refsCursor = 0; const result = []; function visit(node) { if (!React.isValidElement(node)) return; result.push(node); React.Children.forEach(node.props.children, visit); } visit(OutlierEditor(props)); return result; }
  const button = text => elements().find(node => node.props.children === text);
  assert.equal(button("Apply outlier treatment").props.disabled, true);
  button("Validate configuration").props.onClick();
  resolve({ revision: 3, errors: [], outlier_treatment: { x_capped: { fitted: true, missing_count: 0, multiplier: 1.5, message: "Training only" } } });
  await new Promise(done => setImmediate(done));
  assert.equal(button("Apply outlier treatment").props.disabled, false);
  button("Apply outlier treatment").props.onClick(); assert.equal(applied.outlier_treatment.version, "outlier-treatment-v1");
  button("Cancel").props.onClick(); assert.equal(canceled, true);
});

test("EDA opens the Studio editor while preserving unsaved preparation and rejecting stale handoffs", async () => {
  const React = await import("react");
  const { draftHistory, changeDraft } = loadComponent("lib/preparation.ts");
  const column = { name: "income", source_order: 0, physical_dtype: "float64", effective_semantic_type: "continuous", inferred_semantic_type: "continuous", semantic_override: null, role: "feature", missing_count: 0, unique_count: 4 };
  const ir = { ir_version: "0.2", features: { income: { included: true, operations: [] } } };
  const snapshot = { revision: 3, ir, columns: [column], issues: [], target_classes: [], stale: false };
  const draft = { ...ir, features: { income: { included: true, operations: [{ type: "scale", method: "robust" }] } } };
  const history = changeDraft(draftHistory(ir), draft);
  let cursor = 0;
  const slots = [];
  const react = { ...React, useEffect() {}, useCallback: fn => fn, useRef: initial => ({ current: initial }), useState(initial) { const i = cursor++; if (!(i in slots)) slots[i] = i === 0 ? snapshot : i === 1 ? history : typeof initial === "function" ? initial() : initial; return [slots[i], value => { slots[i] = typeof value === "function" ? value(slots[i]) : value; }]; } };
  const { DataPreparationStudio } = loadComponent("components/data-preparation-studio.tsx", { react, "next/navigation": { useRouter: () => ({ push() {} }) }, "./live-pipeline": { useLivePipeline: () => null } });
  const props = { project: { id: "p", ml_objective: "regression" }, dataset: { id: "d", revision: 3, columns: [column], preview: [[1], [2]], preview_limit: 20, row_count: 2, column_count: 1 }, initialDiagnostics: true, onDatasetSaved() {}, onReload() {} };
  function elements() { cursor = 0; const found = []; function visit(node) { if (!React.isValidElement(node)) return; found.push(node); React.Children.forEach(node.props.children, visit); } visit(DataPreparationStudio(props)); return found; }
  const explore = elements().find(node => node.type.name === "Explore");
  assert.equal(typeof explore.props.onPrepare, "function");
  explore.props.onPrepare({ projectId: "p", datasetId: "d", revision: 3, feature: "income", action: "outliers", multiplier: 2 });
  const editor = elements().find(node => node.type.name === "OutlierEditor");
  assert.equal(editor.props.initialSource, "income"); assert.equal(editor.props.multiplier, 2);
  assert.deepEqual(editor.props.state.ir, draft);
  assert.deepEqual(slots[1].past, history.past);
  explore.props.onPrepare({ projectId: "p", datasetId: "d", revision: 2, feature: "income", action: "missing" });
  assert.ok(elements().some(node => React.Children.toArray(node.props.children).some(child => typeof child === "string" && child.includes("revision changed"))));
  assert.deepEqual(slots[1].present, draft);
});
