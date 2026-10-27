import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { loadComponent } from "./load-component.mjs";

test("Edit Code opens confirmation; cancelling never enters; confirmation enters once", async () => {
  const state = [];
  let index = 0, entered = 0;
  const preview = { ready: true, source: "# generated", issues: [], libraries: {}, source_sha256: "sha256:source", plan_sha256: "sha256:plan" };
  const hooks = { ...React, useEffect: () => {}, useRef: () => ({ current: 0 }), useState: initial => {
    const slot = index++;
    if (!(slot in state)) state[slot] = slot === 1 ? preview : initial;
    return [state[slot], value => { state[slot] = typeof value === "function" ? value(state[slot]) : value; }];
  } };
  const { CodeView } = loadComponent("components/code-view.tsx", { react: hooks,
    "./code-mode-state": { useCodeMode: () => ({ ready: true, busy: false, enter: async value => { assert.equal(value, preview); entered++; return true; } }) } });
  function tree() { index = 0; return CodeView({ projectId: "project" }); }
  function find(node, predicate) {
    if (!React.isValidElement(node)) return null;
    if (predicate(node)) return node;
    for (const child of React.Children.toArray(node.props.children)) { const found = find(child, predicate); if (found) return found; }
    return null;
  }
  find(tree(), n => n.props.children === "Edit Code").props.onClick();
  const dialog = find(tree(), n => n.type?.name === "CodeModeConfirmation");
  assert.ok(dialog); assert.equal(entered, 0);
  dialog.props.onClose();
  assert.equal(find(tree(), n => n.type?.name === "CodeModeConfirmation"), null);
  assert.equal(entered, 0);
  find(tree(), n => n.props.children === "Edit Code").props.onClick();
  find(tree(), n => n.type?.name === "CodeModeConfirmation").props.onConfirm();
  await Promise.resolve();
  assert.equal(entered, 1);
});
