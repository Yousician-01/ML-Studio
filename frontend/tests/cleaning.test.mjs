import test from "node:test";
import assert from "node:assert/strict";
import * as React from "react";
import { loadComponent } from "./load-component.mjs";
const { newCleaningStep, cleaningRecipe, selectionStep, cleaningInputError } = loadComponent("lib/cleaning.ts");
test("guided cleaning defaults preserve selected operands and typed intent", () => {
  const missing = newCleaningStep("missing_filter", "income");
  assert.deepEqual(missing.columns, ["income"]); assert.equal(missing.keep, "present"); assert.equal(missing.mode, "any");
  assert.equal(selectionStep(missing), true);
  const convert = newCleaningStep("convert", "date");
  assert.equal(convert.invalid, "reject"); assert.equal(convert.policy.naive, "utc"); assert.notEqual(convert.id, missing.id);
  assert.equal(newCleaningStep("replace", "age").value, null);
  assert.match(cleaningInputError([{ ...newCleaningStep("replace", "age"), value: NaN }]), /finite/);
  assert.equal(newCleaningStep("filter", "age").condition.arguments[0].name, "age");
  const { CleaningEditor } = loadComponent("components/cleaning-editor.tsx", { react: {
    ...React, useEffect() {}, useRef: current => ({ current }),
    useState: initial => [typeof initial === "function" ? initial() : initial, () => {}],
  } });
  function editorElements(step) {
    const tree = CleaningEditor({ projectId: "p", state: { revision: 1, ir: { features: {}, cleaning: { version: "cleaning-v1", steps: [step] } } }, sourceColumns: [{ name: "date" }], initialStep: step.id, disabled: false, onApply() {}, onCancel() {}, onDirtyChange() {} });
    const elements = [];
    function visit(node) { if (!React.isValidElement(node)) return; elements.push(node); React.Children.forEach(node.props.children, visit); }
    visit(tree); return elements;
  }
  const dateConversion = { ...convert, destination: "datetime", invalid: "reject", policy: { ...convert.policy, invalid: "coerce" } };
  const elements = editorElements(dateConversion);
  const invalidLabels = elements.filter(node => node.type === "label" && React.Children.toArray(node.props.children).some(child => typeof child === "string" && child.startsWith("Invalid")));
  assert.equal(invalidLabels.length, 1, "datetime conversion exposes exactly one active invalid policy");
  assert.equal(invalidLabels[0].props.children[0], "Invalid conversion");
  assert.equal(elements.filter(node => node.type === "input" && node.props.type === "checkbox").length, 0, "hidden date policy does not request conversion coercion confirmation");
  assert.equal(editorElements({ ...dateConversion, invalid: "coerce", policy: { ...convert.policy, invalid: "reject" } }).filter(node => node.type === "input" && node.props.type === "checkbox").length, 1, "effective conversion coercion requires confirmation");

});
test("whole-recipe repairs retain intent; matching preview gates Apply and Cancel aborts pending work", async () => {
  const original = { features: { age: { included: true, operations: [] } }, temporal: { version: "temporal-v1", sources: {}, features: [] } };
  const steps = [newCleaningStep("normalize", "age"), newCleaningStep("validate", "age")];
  const next = cleaningRecipe(original, steps); steps[0].column = "changed";
  assert.equal(next.cleaning.steps[0].column, "age"); assert.equal(original.cleaning, undefined);
  assert.deepEqual(next.features, original.features); assert.deepEqual(next.temporal, original.temporal);
  assert.equal(cleaningRecipe(next, []).cleaning, null);

  let cursor = 0, refCursor = 0, applied = null, canceled = false, resolvePreview, signal;
  const slots = [], refs = [];
  const react = { ...React, useEffect() {}, useRef: initial => {
    const index = refCursor++; return refs[index] ??= { current: initial };
  }, useState: initial => {
    const index = cursor++;
    if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial;
    return [slots[index], value => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }];
  } };
  const normalize = { ...newCleaningStep("normalize", "age"), tokens: ["N/A"] };
  const source = { ...original, cleaning: { version: "cleaning-v1", steps: [normalize, newCleaningStep("missing_filter", "age")] } };
  const originalJson = JSON.stringify(source);
  let expected = source;
  const { CleaningEditor } = loadComponent("components/cleaning-editor.tsx", { react, "@/lib/api/projects": { api: {
    temporalPreview(project, revision, ir, requestSignal) {
      assert.equal(project, "p"); assert.equal(revision, 4); assert.deepEqual(ir, expected);
      signal = requestSignal; return new Promise(resolve => { resolvePreview = resolve; });
    },
  } } });
  const props = { projectId: "p", state: { revision: 4, ir: source }, sourceColumns: [{ name: "age", effective_semantic_type: "continuous" }], initialStep: normalize.id, disabled: false, onApply: ir => { applied = ir; }, onCancel: () => { canceled = true; }, onDirtyChange() {} };
  function render() { cursor = 0; refCursor = 0; return CleaningEditor(props); }
  function elements(tree) {
    const found = [];
    function visit(node) { if (!React.isValidElement(node)) return; found.push(node); React.Children.forEach(node.props.children, visit); }
    visit(tree); return found;
  }
  const button = (tree, text) => elements(tree).find(node => node.props.children === text);
  const payload = { revision: 4, limit: 20, columns: [], warnings: [], errors: [], sources: {}, cleaning: {
    columns: [{ name: "age", physical_dtype: "float64", semantic_type: "continuous", missing_count: 0, unique_count: 1 }], rows: [[10]], row_indices: [1], source_rows: 2, retained_rows: 1, removed_rows: 1, events: [], diagnostics: [],
  } };
  let tree = render();
  assert.equal(button(tree, "Apply cleaning").props.disabled, true);
  elements(tree).find(node => node.type === "textarea").props.onChange({ target: { value: "NA\nunknown" } });
  expected = cleaningRecipe(source, [{ ...normalize, tokens: ["NA", "unknown"] }, source.cleaning.steps[1]]);
  tree = render();
  button(tree, "Preview cleaning").props.onClick();
  resolvePreview({ ...payload, revision: 3 });
  await new Promise(resolve => setImmediate(resolve)); tree = render();
  assert.equal(button(tree, "Apply cleaning").props.disabled, true, "stale preview cannot enable Apply");
  button(tree, "Preview cleaning").props.onClick();
  resolvePreview({ ...payload, errors: ["Repair the retained rule"] });
  await new Promise(resolve => setImmediate(resolve)); tree = render();
  assert.equal(button(tree, "Apply cleaning").props.disabled, true, "preview errors cannot enable Apply");
  button(tree, "Preview cleaning").props.onClick();
  resolvePreview(payload);
  await new Promise(resolve => setImmediate(resolve)); tree = render();
  assert.equal(button(tree, "Apply cleaning").props.disabled, false);
  button(tree, "Apply cleaning").props.onClick();
  assert.deepEqual(applied, expected, "Apply retains the full recipe and untouched selection rule");
  assert.equal(JSON.stringify(source), originalJson, "applying does not mutate the saved source state");
  applied = null;
  button(tree, "Preview cleaning").props.onClick(); tree = render();
  button(tree, "Cancel").props.onClick();
  assert.equal(signal.aborted, true); assert.equal(canceled, true);
  resolvePreview(payload);
  await new Promise(resolve => setImmediate(resolve)); tree = render();
  assert.equal(button(tree, "Apply cleaning").props.disabled, true, "a late canceled response cannot enable Apply");
  assert.equal(applied, null); assert.equal(JSON.stringify(source), originalJson);

});
