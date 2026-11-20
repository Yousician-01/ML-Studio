import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { loadComponent } from "./load-component.mjs";
import { canGuideDerived, derivedCall, derivedExpressionError, derivedPreviewRecipe, derivedRecipe } from "../src/lib/derived.ts";

const expression = derivedCall("subtract", [{ kind: "column", name: "revenue" }, { kind: "column", name: "cost" }]);
function recipe() { return { ir_version: "0.1", dataset: null, target: { column: "label" }, features: { revenue: { included: true, operations: [] }, cost: { included: true, operations: [] }, profit: { included: true, operations: [{ type: "scale", method: "standard" }] }, margin: { included: true, operations: [] } }, model: null, split: null, derived: { version: "derived-v1", features: [{ name: "profit", expression }, { name: "margin", expression: derivedCall("safe_divide", [{ kind: "reference", name: "profit" }, { kind: "column", name: "revenue" }]) }] } }; }

test("derived recipes retain dependent definitions and preparation; expression safety bounds are enforced", () => {
  const ir = recipe(), original = JSON.stringify(ir);
  const same = derivedRecipe(ir, "profit", expression, ["revenue", "cost", "label"], "profit");
  assert.deepEqual(same.features.profit.operations, ir.features.profit.operations);
  const renamed = derivedRecipe(ir, "net_profit", expression, ["revenue", "cost", "label"], "profit");
  assert.equal(renamed.features.profit, undefined);
  assert.deepEqual(renamed.features.net_profit, { included: true, operations: [] });
  assert.deepEqual(renamed.derived.features[0], ir.derived.features[1]);
  assert.equal(JSON.stringify(ir), original);
  assert.throws(() => derivedRecipe(ir, "cost", expression, ["revenue", "cost"], "profit"), /already uses/);
  assert.throws(() => derivedRecipe(ir, "new", { kind: "column", name: "label" }, ["revenue", "cost"], "profit"), /target/);
  let deep = { kind: "literal", value: 1 };
  for (let i = 0; i < 8; i++) deep = derivedCall("abs", [deep]);
  assert.match(derivedExpressionError(deep), /8 levels/);
  assert.match(derivedExpressionError({ kind: "literal", value: "x".repeat(1001) }), /1000/);
  assert.equal(derivedExpressionError({ ...derivedCall("round", [{ kind: "literal", value: 2 }]), parameters: { precision: null } }), null, "saved default precision remains editable");
  assert.equal(canGuideDerived(expression), true);
  assert.equal(canGuideDerived(derivedCall("abs", [expression])), false);
  const repair = recipe();
  repair.derived.features.push({ name: "unrelated_invalid", expression: { kind: "reference", name: "deleted" } });
  repair.features.unrelated_invalid = { included: true, operations: [] };
  const preview = derivedPreviewRecipe(repair, "margin");
  assert.deepEqual(preview.derived.features.map(feature => feature.name), ["profit", "margin"]);
  assert.equal(preview.features.unrelated_invalid, undefined);
  assert.equal(repair.derived.features.length, 3, "full Apply candidate retains unrelated invalid definitions");
  assert.throws(() => derivedPreviewRecipe(repair, "unrelated_invalid"), /Missing derived reference/);
  const cycle = recipe(); cycle.derived.features[0].expression = { kind: "reference", name: "margin" };
  assert.throws(() => derivedPreviewRecipe(cycle, "margin"), /Circular derived reference/);
});

test("visual modes preserve nested AST; only a matching runtime preview enables Apply and Cancel aborts pending work", async () => {
  let cursor = 0, applied = null, canceled = false, resolvePreview, signal;
  const slots = [], refs = [];
  let refCursor = 0;
  const react = { ...React, useEffect() {}, useRef: initial => { const index = refCursor++; return refs[index] ??= { current: initial }; }, useState: initial => { const index = cursor++; if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial; return [slots[index], value => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }]; } };
  const { DerivedFeaturesEditor } = loadComponent("components/derived-features.tsx", { react, "@/lib/api/projects": { api: { temporalPreview: (_project, revision, ir, requestSignal) => {
    assert.equal(revision, 4); assert.deepEqual(ir.derived.features.map(feature => feature.name), ["profit"]); signal = requestSignal;
    return new Promise(resolve => { resolvePreview = resolve; });
  } } } });
  const state = { revision: 4, ir: recipe(), columns: ["revenue", "cost", "label"].map(name => ({ name, effective_semantic_type: "continuous" })) };
  const props = { projectId: "p", state, disabled: false, initialFeature: "profit", onApply: ir => { applied = ir; }, onCancel: () => { canceled = true; }, onDirtyChange() {} };
  function render() { cursor = 0; refCursor = 0; return DerivedFeaturesEditor(props); }
  function elements(tree) { const found = []; function visit(node) { if (!React.isValidElement(node)) return; found.push(node); React.Children.forEach(node.props.children, visit); } visit(tree); return found; }
  const button = (tree, text) => elements(tree).find(node => node.props.children === text);
  let tree = render();
  assert.equal(button(tree, "Apply derived feature").props.disabled, true);
  button(tree, "Expression Mode").props.onClick(); tree = render();
  const nested = derivedCall("abs", [expression]);
  elements(tree).find(node => node.type.name === "ExpressionInput").props.onChange(nested);
  tree = render(); button(tree, "Guided Mode").props.onClick(); tree = render();
  assert.equal(button(tree, "Expression Mode").props["aria-pressed"], true);
  assert.deepEqual(elements(tree).find(node => node.type.name === "ExpressionInput").props.value, nested);
  button(tree, "Preview derived feature").props.onClick();
  resolvePreview({ revision: 4, limit: 20, columns: [{ name: "profit", semantic_type: "continuous", missing_count: 0, invalid_count: 0, values: [2] }], warnings: [], errors: [], sources: {} });
  await new Promise(resolve => setImmediate(resolve)); tree = render();
  assert.equal(button(tree, "Apply derived feature").props.disabled, false);
  button(tree, "Apply derived feature").props.onClick();
  assert.deepEqual(applied.derived.features.find(feature => feature.name === "profit").expression, nested);
  assert.ok(applied.derived.features.some(feature => feature.name === "margin"), "Apply retains definitions omitted from the focused preview");
  applied = null;
  button(tree, "Preview derived feature").props.onClick(); tree = render();
  button(tree, "Cancel").props.onClick();
  assert.equal(signal.aborted, true); assert.equal(canceled, true);
  resolvePreview({ revision: 4, limit: 20, columns: [], warnings: [], errors: [], sources: {} });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(applied, null); assert.deepEqual(state.ir.derived.features[0].expression, expression);
});
