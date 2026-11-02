import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { loadComponent } from "./load-component.mjs";

const { PreviewRequests, currentPreview, previewConfiguration, viewerPreference } = loadComponent("lib/live-code.ts");
const preview = { project_id: "p", ready: true, source: "# generated", issues: [], libraries: {}, source_sha256: "sha256:source", plan_sha256: "sha256:plan" };

test("late generation and previous-project responses cannot replace the latest request", async () => {
  const requests = new PreviewRequests();
  let first, second;
  const accepted = [];
  const a = requests.run(() => new Promise(resolve => { first = resolve; }), v => accepted.push(v), assert.fail);
  const b = requests.run(() => new Promise(resolve => { second = resolve; }), v => accepted.push(v), assert.fail);
  second("new"); await b; first("old"); await a;
  assert.deepEqual(accepted, ["new"]);
  const c = requests.run(() => Promise.resolve("project-A"), v => accepted.push(v), assert.fail);
  requests.cancel(); await c;
  assert.deepEqual(accepted, ["new"]);
});

test("invalid or outdated configuration has no current executable preview; presentation is only UI", () => {
  assert.equal(currentPreview(preview, "new-input", "old-input"), null);
  assert.equal(currentPreview({ ...preview, ready: false }, "same", "same"), null);
  assert.equal(currentPreview(preview, "same", "same"), preview);
  assert.deepEqual(viewerPreference({ presentation: "code-editing", width: -5 }), { presentation: "closed", width: 35 });
  assert.deepEqual(viewerPreference({ presentation: "floating", width: Infinity }), { presentation: "floating", width: 45 });
  const { OpenCodeButton } = loadComponent("components/open-code-button.tsx");
  const previousWindow = globalThis.window, events = [];
  globalThis.window = { dispatchEvent: event => events.push(event.type) };
  try {
    OpenCodeButton({ children: "Inspect current Code" }).props.onClick();
    OpenCodeButton({ history: true, children: "Open Code Run history" }).props.onClick();
    assert.deepEqual(events, ["mlstudio:show-code", "mlstudio:show-code-history"]);
  } finally { globalThis.window = previousWindow; }
});

test("unsaved parameters and split use existing parsers, retain visual IR, and reject intermediate text", () => {
  const state = { revision: 4, ir: { ir_version: "0.2", task: "regression", features: {}, model: { type: "ridge", parameters: { alpha: 1 } }, split: { test_size: .2, random_seed: 7 } }, model_catalogue: [{ id: "ridge", parameter_schema: { properties: { alpha: { type: "number", minimum: 0 } } } }] };
  const original = JSON.stringify(state);
  assert.equal(previewConfiguration(state, "model", { alpha: "2.5" }).model.parameters.alpha, 2.5);
  assert.equal(previewConfiguration(state, "model", { alpha: "-" }), null);
  assert.equal(previewConfiguration(state, "split", { test_size: "30", random_seed: "42" }).split.test_size, .3);
  assert.equal(JSON.stringify(state), original);
});

test("Edit Code protects independent drafts with explicit continue, fresh, and cancel choices", async () => {
  const slots = []; let cursor = 0, resumed = 0, entered = 0, opened = 0;
  const hooks = { ...React, useEffect: () => {}, useRef: value => ({ current: value }), useState: initial => {
    const index = cursor++;
    if (!(index in slots)) slots[index] = index === 0 ? { key: JSON.stringify(["p", undefined, 0]), value: preview } : initial;
    return [slots[index], value => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }];
  } };
  const { LiveCodeViewer } = loadComponent("components/live-code-viewer.tsx", { react: hooks,
    "./live-pipeline": { useLivePipeline: () => ({ input: undefined, epoch: 0, refresh() {}, revalidate() {} }) },
    "@/lib/api/projects": { api: { codeSessions: async () => [{ id: "preserved", status: "archived" }] } },
    "./code-mode-state": { useCodeMode: () => ({ ready: true, busy: false, draft: null, resume: async id => { assert.equal(id, "preserved"); resumed++; return true; }, enter: async () => { entered++; return true; } }) },
  });
  function tree() { cursor = 0; return LiveCodeViewer({ projectId: "p", preference: { presentation: "docked", width: 45 }, onPreference() {}, onEdit() { opened++; } }); }
  function find(node, predicate) {
    if (!React.isValidElement(node)) return null;
    if (predicate(node)) return node;
    for (const child of React.Children.toArray(node.props.children)) { const found = find(child, predicate); if (found) return found; }
    return null;
  }
  assert.equal(entered + resumed, 0); // opening a viewer does not enter Code Mode
  await find(tree(), n => n.props.children === "Edit Code").props.onClick();
  find(tree(), n => n.props.title === "Preserve existing Code draft").props.onClose();
  assert.equal(entered + resumed, 0);
  await find(tree(), n => n.props.children === "Edit Code").props.onClick();
  find(tree(), n => n.props.children === "Continue editing the existing draft").props.onClick();
  await Promise.resolve(); assert.equal(resumed, 1); assert.equal(entered, 0); assert.equal(opened, 1);
  await find(tree(), n => n.props.children === "Edit Code").props.onClick();
  find(tree(), n => n.props.children === "Start a new draft from the current visual pipeline").props.onClick();
  await Promise.resolve(); assert.equal(entered, 1); assert.equal(opened, 2);
});
