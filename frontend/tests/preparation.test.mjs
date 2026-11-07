import test from "node:test";
import assert from "node:assert/strict";
import { appliedSteps, atStep, removeStep, draftHistory, changeDraft, undoDraft, redoDraft, columnActions, preparationErrors, rememberStudioSession, readStudioSession, clearStudioSession } from "../src/lib/preparation.ts";
import React from "react";
import { loadComponent } from "./load-component.mjs";

const columns = [{ name: "date", source_order: 0, physical_dtype: "str", effective_semantic_type: "datetime" }, { name: "amount", source_order: 1, physical_dtype: "float64", effective_semantic_type: "continuous" }];
function recipe() {
  return { ir_version: "0.1", dataset: { dataset_id: "d", fingerprint: "sha256:a" }, target: { column: "label", positive_class: { value_type: "string", value: "yes" }, missing_value_policy: "exclude_rows" }, features: { date: { included: false, operations: [] }, amount: { included: true, operations: [{ type: "impute", strategy: "median" }, { type: "scale", method: "standard" }] }, month: { included: true, operations: [] } }, model: null, split: null, temporal: { version: "temporal-v1", sources: { date: { format: "ISO8601", naive: "utc", invalid: "reject" } }, features: [{ name: "month", expression: { kind: "call", operation: "month", arguments: [{ kind: "column", name: "date" }], parameters: {} } }] } };
}

test("column menus expose compatible editors and use one action policy for every entry point", () => {
  assert.ok(columnActions(columns[0], false, true).some(action => action.id === "temporal-cycle"));
  assert.ok(!columnActions(columns[0], false, true).some(action => action.id === "scale"));
  assert.ok(columnActions(columns[1], false, true).some(action => action.id === "scale"));
  assert.deepEqual(columnActions(columns[1], true, false).map(action => action.id), ["profile"]);
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
  const next = removeStep(loaded, steps.find(step => step.column === "month" && step.kind === "temporal"));
  assert.equal(next.temporal.features[0].name, "sin");
  assert.equal(appliedSteps(next, columns).find(step => step.kind === "legacy").invalid, true);
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
