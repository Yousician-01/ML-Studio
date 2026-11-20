import test from "node:test";
import assert from "node:assert/strict";

import React from "react";
import { loadComponent } from "./load-component.mjs";
const { appliedSteps, atStep, removeStep, draftHistory, changeDraft, undoDraft, redoDraft, columnActions, preparationErrors, rememberStudioSession, readStudioSession, clearStudioSession } = loadComponent("lib/preparation.ts");

const columns = [{ name: "date", source_order: 0, physical_dtype: "str", effective_semantic_type: "datetime" }, { name: "amount", source_order: 1, physical_dtype: "float64", effective_semantic_type: "continuous" }];
function recipe() {
  return { ir_version: "0.1", dataset: { dataset_id: "d", fingerprint: "sha256:a" }, target: { column: "label", positive_class: { value_type: "string", value: "yes" }, missing_value_policy: "exclude_rows" }, features: { date: { included: false, operations: [] }, amount: { included: true, operations: [{ type: "impute", strategy: "median" }, { type: "scale", method: "standard" }] }, month: { included: true, operations: [] } }, model: null, split: null, temporal: { version: "temporal-v1", sources: { date: { format: "ISO8601", naive: "utc", invalid: "reject" } }, features: [{ name: "month", expression: { kind: "call", operation: "month", arguments: [{ kind: "column", name: "date" }], parameters: {} } }] } };
}

test("column menus expose compatible editors and use one action policy for every entry point", () => {
  assert.ok(columnActions(columns[0], false, true).some(action => action.id === "temporal-cycle"));
  assert.ok(!columnActions(columns[0], false, true).some(action => action.id === "scale"));
  assert.ok(columnActions(columns[1], false, true).some(action => action.id === "scale"));
  assert.deepEqual(columnActions(columns[1], true, false).map(action => action.id), ["profile", "lineage"]);
});

test("column menu groups missing-value actions in a keyboard-accessible submenu", () => {
  let cursor = 0, chosen = null, closed = 0;
  const slots = [];
  const { PreparationMenu } = loadComponent("components/preparation-menu.tsx", { react: {
    ...React, useEffect() {}, useRef: value => ({ current: value }),
    useState: initial => { const index = cursor++; if (!(index in slots)) slots[index] = initial; return [slots[index], value => { slots[index] = value; }]; },
  } });
  const actions = columnActions(columns[1], false, true);
  const props = { column: "amount", actions, position: { x: 10, y: 10 }, onAction: action => { chosen = action; }, onClose: () => { closed++; } };
  function render() { cursor = 0; return PreparationMenu(props); }
  function elements(node) { if (!React.isValidElement(node)) return []; return [node, ...React.Children.toArray(node.props.children).flatMap(elements)]; }
  const item = (tree, name) => elements(tree).find(node => node.props.role === "menuitem" && node.props.children === name);
  let tree = render();
  assert.ok(item(tree, "Handle Missing Values"));
  assert.equal(item(tree, "Configure Imputation"), undefined);
  assert.equal(item(tree, "Remove Rows Where This Column Is Missing"), undefined);
  assert.ok(item(tree, "Replace Values"));
  item(tree, "Handle Missing Values").props.onClick(); tree = render();
  for (const name of ["Configure Imputation", "Advanced Imputation", "Normalize Missing Tokens", "Fill Missing Datetime", "Replace With Missing", "Remove Rows Where This Column Is Missing", "Keep Rows Where This Column Is Missing"]) assert.ok(item(tree, name), name);
  assert.equal(item(tree, "Replace Values"), undefined);
  item(tree, "Advanced Imputation").props.onClick();
  assert.equal(chosen, actions.find(action => action.id === "advanced-imputation"));
  tree.props.onKeyDown({ key: "ArrowLeft", preventDefault() {}, stopPropagation() {} }); tree = render();
  assert.ok(item(tree, "Handle Missing Values")); assert.equal(closed, 0);
  item(tree, "Handle Missing Values").props.onKeyDown({ key: "ArrowRight", preventDefault() {}, stopPropagation() {} }); tree = render();
  assert.ok(item(tree, "Configure Imputation"));
  tree.props.onKeyDown({ key: "Escape", preventDefault() {}, stopPropagation() {} }); tree = render();
  assert.ok(item(tree, "Handle Missing Values")); assert.equal(closed, 0);
  tree.props.onKeyDown({ key: "Escape", preventDefault() {}, stopPropagation() {} }); assert.equal(closed, 1);
  cursor = 0; slots.length = 0;
  assert.equal(item(PreparationMenu({ ...props, actions: actions.filter(action => action.id === "profile") }), "Handle Missing Values"), undefined);
});

test("advanced imputation has a fixed fitted stage; prefixes, restoration and history preserve prior intent", () => {
  const ir = recipe();
  ir.features.amount.operations = [{ type: "scale", method: "standard" }];
  ir.imputation = { version: "imputation-v1", columns: { amount: {
    rules: [{ condition: null, strategy: "median", value: null, group_by: [] }],
    fallback: { strategy: "constant", value: 0 }, indicator: "amount_missing", previous_strategy: "mean",
  } } };
  const steps = appliedSteps(ir, columns), advanced = steps.find(step => step.kind === "advanced");
  assert.ok(advanced);
  assert.ok(steps.indexOf(advanced) > steps.findIndex(step => step.kind === "participation"));
  assert.ok(steps.indexOf(advanced) < steps.findIndex(step => step.kind === "operation"));
  assert.deepEqual(advanced.outputs, ["amount", "amount_missing"]);
  assert.equal(atStep(ir, columns, "source").imputation, null);
  const prefix = atStep(ir, columns, advanced.id);
  assert.deepEqual(prefix.imputation, ir.imputation);
  assert.deepEqual(prefix.features.amount.operations, []);
  const removed = removeStep(ir, advanced);
  assert.deepEqual(removed.features.amount.operations, [{ type: "impute", strategy: "mean" }, { type: "scale", method: "standard" }]);
  assert.equal(removed.imputation, undefined);
  assert.deepEqual(undoDraft(changeDraft(draftHistory(ir), removed)).present, ir);
  assert.deepEqual(appliedSteps(JSON.parse(JSON.stringify(ir)), columns), steps);
});

test("generalized features follow temporal dependencies and retain exact stage prefixes across undo/reload", () => {
  const ir = recipe();
  const ref = name => ({ kind: "reference", name });
  ir.derived = { version: "derived-v1", features: [
    { name: "long_term", expression: { kind: "call", operation: "greater", arguments: [ref("years"), { kind: "literal", value: 1 }], parameters: {} } },
    { name: "years", expression: { kind: "call", operation: "safe_divide", arguments: [ref("month"), { kind: "literal", value: 12 }], parameters: {} } },
  ] };
  ir.features.years = { included: true, operations: [] };
  ir.features.long_term = { included: true, operations: [] };
  const steps = appliedSteps(ir, columns);
  assert.deepEqual(steps.filter(step => step.kind === "derived").map(step => step.column), ["years", "long_term"]);
  const prefix = atStep(ir, columns, "derived:years");
  assert.deepEqual(prefix.derived.features.map(feature => feature.name), ["years"]);
  assert.deepEqual(prefix.temporal, ir.temporal);
  assert.equal(atStep(ir, columns, "source").derived, null);
  assert.throws(() => removeStep(ir, steps.find(step => step.id === "derived:years")), /dependent/);
  const removed = removeStep(ir, steps.find(step => step.id === "derived:long_term"));
  assert.equal(removed.derived.features[0].name, "years");
  const history = changeDraft(draftHistory(ir), removed);
  assert.deepEqual(undoDraft(history).present.derived, ir.derived);
  assert.deepEqual(appliedSteps(JSON.parse(JSON.stringify(ir)), columns), steps);
});

test("applied steps project executable stages; edit/remove/revert and undo/redo preserve unrelated intent", () => {
  const original = recipe(), originalJson = JSON.stringify(original);
  const steps = appliedSteps(original, columns);
  assert.deepEqual(steps.map(step => step.kind), ["source", "parse", "temporal", "participation", "operation", "operation"]);
  const derived = steps.find(step => step.kind === "temporal");
  const prefix = atStep(original, columns, derived.id);
  assert.equal(prefix.temporal.features.length, 1);
  assert.deepEqual(prefix.features.amount.operations, []);
  assert.deepEqual(prefix.model, original.model);
  const removed = removeStep(original, steps.at(-1));
  assert.deepEqual(removed.features.amount.operations, [{ type: "impute", strategy: "median" }]);
  let history = draftHistory(original);
  history = changeDraft(history, removed);
  history = changeDraft(history, atStep(original, columns, "source"));
  assert.equal(history.present.temporal, null);
  history = undoDraft(history);
  assert.deepEqual(history.present, removed);
  assert.deepEqual(redoDraft(history).present.temporal, null);
  assert.equal(JSON.stringify(original), originalJson);
  const missing = recipe(); delete missing.features.amount;
  const missingSteps = appliedSteps(missing, columns);
  assert.equal(missingSteps.find(step => step.kind === "participation").invalid, true);
  assert.equal(atStep(missing, columns, missingSteps.at(-1).id).features.amount, undefined);
  const duplicate = recipe(); duplicate.features.amount.operations.unshift({ type: "impute", strategy: "mean" });
  const group = appliedSteps(duplicate, columns).find(step => step.id.startsWith("legacy-operations:"));
  assert.equal(group.invalid, true);
  assert.deepEqual(removeStep(duplicate, group).features.amount.operations, []);
  assert.deepEqual(removeStep(duplicate, group).temporal, duplicate.temporal);
});

test("saved temporal-v1 intent reconstructs its steps after reload; removal retains dependent definitions", () => {
  const saved = recipe();
  saved.temporal.features.push({ name: "sin", expression: { kind: "call", operation: "cyclic_sin", arguments: [{ kind: "reference", name: "month" }], parameters: {} } });
  saved.features.sin = { included: true, operations: [] };
  const loaded = JSON.parse(JSON.stringify(saved));
  const steps = appliedSteps(loaded, columns);
  assert.deepEqual(steps.filter(step => step.kind === "temporal").map(step => step.column), ["month", "sin"]);
  assert.throws(() => removeStep(loaded, steps.find(step => step.column === "month" && step.kind === "temporal")), /dependent/);
  const next = removeStep(loaded, steps.find(step => step.column === "sin" && step.kind === "temporal"));
  assert.equal(next.temporal.features[0].name, "month");
  assert.deepEqual(preparationErrors([{ severity: "blocking", scope: "train", code: "model_missing", message: "Choose a model" }]), []);
  assert.deepEqual(preparationErrors([{ severity: "blocking", scope: "feature", code: "operation_incompatible", message: "Fix scaling" }]), ["Fix scaling"]);
  const history = changeDraft(draftHistory(saved), next);
  rememberStudioSession("p", "d", { revision: 1, base: JSON.stringify(saved), columns: JSON.stringify(columns), history });
  assert.deepEqual(readStudioSession("p", "d").history, history, "applied edits and undo survive workspace unmount");
  assert.equal(readStudioSession("other", "d"), null);
  clearStudioSession("p", "d"); assert.equal(readStudioSession("p", "d"), null);
});

test("header menu routes to the shared editor; Apply, Save, reload and Continue use the persisted IR", async () => {
  let cursor = 0;
  const slots = [], routes = [];
  const schema = [...columns, { name: "label", source_order: 2, physical_dtype: "str", effective_semantic_type: "binary" }].map(column => ({ ...column, missing_count: 0, unique_count: 2, role: column.name === "label" ? "target" : "feature", inferred_semantic_type: column.effective_semantic_type, semantic_override: null, inference_version: "semantic-v2" }));
  let saved = { revision: 3, ir: recipe(), columns: schema, issues: [{ severity: "blocking", scope: "train", code: "model_missing", message: "Choose model in Train" }], stale: false, target_classes: [] };
  const props = { project: { id: "p", ml_objective: "binary_classification" }, dataset: { id: "d", revision: 3, original_filename: "data.csv", columns: schema, row_count: 2, column_count: 3, preview_limit: 20, preview: [["2026-01-01", 10, "yes"], ["2026-02-01", 20, "no"]] }, onDatasetSaved() {}, onReload() {} };
  const react = { ...React, useEffect() {}, useCallback: callback => callback, useRef: initial => ({ current: initial }), useState: initial => {
    const index = cursor++;
    if (!(index in slots)) slots[index] = index === 0 ? saved : index === 1 ? draftHistory(saved.ir) : typeof initial === "function" ? initial() : initial;
    return [slots[index], value => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }];
  } };
  const { DataPreparationStudio } = loadComponent("components/data-preparation-studio.tsx", { react,
    "next/navigation": { useRouter: () => ({ push: route => routes.push(route) }) },
    "./live-pipeline": { useLivePipeline: () => null },
    "@/lib/api/projects": { ApiError: class extends Error {}, api: {
      savePipeline: async (id, revision, ir) => { assert.equal(id, "p"); assert.equal(revision, saved.revision); saved = { ...saved, revision: revision + 1, ir: JSON.parse(JSON.stringify(ir)) }; return saved; },
      pipeline: async () => saved,
    } },
  });
  function render() { cursor = 0; return DataPreparationStudio(props); }
  function elements(tree) {
    const result = [];
    function visit(node) { if (!React.isValidElement(node)) return; result.push(node); React.Children.forEach(node.props.children, visit); }
    visit(tree); return result;
  }
  const previousWindow = globalThis.window;
  globalThis.window = { innerWidth: 1400, innerHeight: 900 };
  try {
    let tree = render();
    const original = JSON.stringify(slots[1].present);
    elements(tree).find(node => node.props.className === "studio-step-select").props.onClick();
    assert.equal(JSON.stringify(slots[1].present), original, "selecting a stage is non-destructive");
    tree = render();
    elements(tree).find(node => node.props["aria-label"] === "Actions for amount").props.onClick({ currentTarget: { getBoundingClientRect: () => ({ left: 300, bottom: 220 }), focus() {} } });
    tree = render();
    const menu = elements(tree).find(node => node.type.name === "PreparationMenu");
    menu.props.onAction(menu.props.actions.find(action => action.id === "scale"));
    tree = render();
    const editor = elements(tree).find(node => node.type.name === "OperationEditor");
    assert.equal(editor.props.column.name, "amount");
    assert.equal(editor.props.family, "scale");
    editor.props.onApply({ included: true, operations: [{ type: "impute", strategy: "median" }, { type: "scale", method: "robust" }] });
    tree = render();
    elements(tree).find(node => node.props.children === "Save preparation").props.onClick();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(saved.ir.features.amount.operations[1].method, "robust");
    assert.equal(saved.ir.temporal.version, "temporal-v1");
    assert.ok(appliedSteps(JSON.parse(JSON.stringify(saved.ir)), schema).some(step => step.label.includes("robust")));
    tree = render();
    elements(tree).find(node => typeof node.props.children === "string" && node.props.children.startsWith("Continue to Train")).props.onClick();
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(routes, ["/projects/p?view=train"]);
  } finally { globalThis.window = previousWindow; }
});


test("cleaning stage prefixes, selected removal and undo retain executable ordered intent", () => {
  const ir = recipe();
  ir.cleaning = { version: "cleaning-v1", steps: [
    { id: "select", kind: "missing_filter", columns: ["amount"], mode: "any", keep: "present" },
    { id: "raw", kind: "normalize", column: "amount", tokens: ["N/A"], trim: true, case_sensitive: true },
    { id: "duplicates", kind: "deduplicate", columns: ["amount"], keep: "last" },
  ] };
  const steps = appliedSteps(ir, columns);
  assert.ok(steps.findIndex(s => s.id === "cleaning:raw") < steps.findIndex(s => s.kind === "parse"));
  assert.ok(steps.findIndex(s => s.id === "cleaning:select") > steps.findIndex(s => s.kind === "temporal"));
  assert.equal(atStep(ir, columns, "source").cleaning, null);
  assert.deepEqual(atStep(ir, columns, "cleaning:select").cleaning.steps.map(s => s.id), ["raw", "select"]);
  const removed = removeStep(ir, steps.find(s => s.id === "cleaning:select"));
  assert.deepEqual(removed.cleaning.steps.map(s => s.id), ["raw", "duplicates"]);
  assert.deepEqual(undoDraft(changeDraft(draftHistory(ir), removed)).present, ir);
  assert.ok(columnActions(columns[1], false, true).some(a => a.id === "cleaning-normalize"));
  assert.ok(!columnActions(columns[1], false, true, false).some(a => a.id === "cleaning-normalize"));
});
