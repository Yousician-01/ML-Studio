import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { loadComponent } from "./load-component.mjs";

const rule = (value = 7) => ({ condition: null, strategy: "constant", value, group_by: [] });
const config = () => ({ rules: [rule(), rule(9)], fallback: { strategy: "leave_missing", value: null }, indicator: "income_was_missing", previous_strategy: null });
function recipe() { return { ir_version: "0.1", target: { column: "label" }, features: { income: { included: true, operations: [{ type: "impute", strategy: "median" }, { type: "scale", method: "standard" }] }, city: { included: false, operations: [] } }, derived: { version: "derived-v1", features: [{ name: "dependent", expression: { kind: "reference", name: "income_was_missing" } }] }, dataset: null, model: null, split: null }; }
const columns = [{ name: "income", physical_dtype: "float64", effective_semantic_type: "continuous", missing_count: 3 }, { name: "city", physical_dtype: "object", effective_semantic_type: "categorical", missing_count: 0 }, { name: "label", effective_semantic_type: "binary" }];

test("advanced recipes persist rules, replace and restore legacy imputation without deleting dependent references", () => {
  const { imputationRecipe, removeAdvancedImputation } = loadComponent("lib/imputation.ts");
  const ir = recipe(), before = JSON.stringify(ir);
  const next = imputationRecipe(ir, "income", config(), columns);
  assert.deepEqual(next.features.income.operations, [{ type: "scale", method: "standard" }]);
  assert.equal(next.imputation.columns.income.previous_strategy, "median");
  const saved = JSON.parse(JSON.stringify(next));
  const edited = imputationRecipe(saved, "income", { ...config(), rules: [rule(11)] }, columns);
  assert.equal(edited.imputation.columns.income.previous_strategy, "median");
  const removed = removeAdvancedImputation(edited, "income");
  assert.equal(removed.imputation, undefined);
  assert.deepEqual(removed.features.income.operations, [{ type: "impute", strategy: "median" }, { type: "scale", method: "standard" }]);
  assert.equal(removed.derived.features[0].expression.name, "income_was_missing");
  assert.equal(JSON.stringify(ir), before);
  assert.throws(() => imputationRecipe(ir, "income", { ...config(), indicator: "city" }, columns), /name|uses|collision/i);
  assert.equal(imputationRecipe(ir, "city", { ...config(), indicator: null }, columns).features.city.included, false, "excluded targets retain dormant editable configurations");
  assert.throws(() => imputationRecipe(ir, "income", { ...config(), rules: [{ ...rule(), group_by: ["income"] }] }, columns), /group/i);
  const conflict = structuredClone(edited); conflict.features.income.operations.push({ type: "impute", strategy: "mean" });
  assert.deepEqual(removeAdvancedImputation(conflict, "income").features.income.operations.filter(op => op.type === "impute"), [{ type: "impute", strategy: "mean" }]);
});

test("ordered editor invalidates previews on edits, requires a matching revision, and aborts Cancel", async () => {
  let cursor = 0, refCursor = 0, applied = null, canceled = false, resolvePreview, signal, submitted;
  const slots = [], refs = [];
  const react = { ...React, useEffect() {}, useRef: initial => refs[refCursor++] ??= { current: initial }, useState: initial => { const index = cursor++; if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial; return [slots[index], value => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }]; } };
  const { AdvancedImputationEditor } = loadComponent("components/advanced-imputation.tsx", { react, "@/lib/api/projects": { api: { temporalPreview: (_project, revision, ir, requestSignal) => { assert.equal(revision, 4); signal = requestSignal; submitted = ir; return new Promise(resolve => { resolvePreview = resolve; }); } } } });
  const state = { revision: 4, ir: { ...recipe(), imputation: { version: "imputation-v1", columns: { income: config() } } }, columns };
  const props = { projectId: "p", state, column: columns[0], disabled: false, onApply: ir => { applied = ir; }, onCancel: () => { canceled = true; }, onDirtyChange() {} };
  const render = () => { cursor = 0; refCursor = 0; return AdvancedImputationEditor(props); };
  function elements(tree) { const result = []; function visit(node) { if (!React.isValidElement(node)) return; result.push(node); React.Children.forEach(node.props.children, visit); } visit(tree); return result; }
  const button = (tree, text) => elements(tree).find(node => node.props.children === text);
  let tree = render(); assert.equal(button(tree, "Apply imputation").props.disabled, true);
  elements(tree).find(node => node.props["aria-label"] === "Move rule 2 up").props.onClick();
  tree = render(); button(tree, "Preview imputation").props.onClick();
  assert.equal(submitted.imputation.columns.income.rules[0].value, 9);
  const response = revision => ({ revision, limit: 20, columns: [], sources: {}, errors: [], warnings: [], imputation: { income: { missing_count: 3, rule_matches: [3, 3], indicator_values: [0, 1] } } });
  resolvePreview(response(3)); await new Promise(resolve => setImmediate(resolve)); tree = render();
  assert.equal(button(tree, "Apply imputation").props.disabled, true);
  button(tree, "Preview imputation").props.onClick(); resolvePreview(response(4));
  await new Promise(resolve => setImmediate(resolve)); tree = render();
  assert.equal(button(tree, "Apply imputation").props.disabled, false);
  button(tree, "Apply imputation").props.onClick(); assert.equal(applied.imputation.columns.income.rules[0].value, 9);
  button(tree, "Add Rule").props.onClick(); tree = render();
  assert.equal(button(tree, "Apply imputation").props.disabled, true);
  button(tree, "Preview imputation").props.onClick(); tree = render(); button(tree, "Cancel").props.onClick();
  assert.equal(signal.aborted, true); assert.equal(canceled, true);
  resolvePreview(response(4)); await new Promise(resolve => setImmediate(resolve));
  assert.equal(state.ir.imputation.columns.income.rules.length, 2);
});
