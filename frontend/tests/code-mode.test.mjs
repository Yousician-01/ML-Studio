import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "./load-component.mjs";

const views = loadComponent("components/code-mode-actions.tsx");
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));
function buttons(element) {
  const found = [];
  function walk(node) {
    if (!React.isValidElement(node)) return;
    if (node.props.onClick) found.push(node);
    React.Children.forEach(node.props.children, walk);
  }
  walk(element);
  return found;
}
test("Code Mode confirmation explains preserved visual intent and cancellation makes no draft", () => {
  let entered = 0, cancelled = 0;
  const props = { busy: false, onConfirm: () => entered++, onClose: () => cancelled++ };
  const html = render(views.CodeModeConfirmation, props);
  assert.match(html, /editable/); assert.match(html, /suspended/);
  assert.match(html, /not update/); assert.match(html, /preserved/);
  const actions = buttons(views.CodeModeConfirmation(props));
  actions.find(node => node.props.children === "Cancel").props.onClick();
  assert.equal(cancelled, 1); assert.equal(entered, 0);
  actions.find(node => node.props.children === "Enter Code Mode").props.onClick();
  assert.equal(entered, 1);
});
test("visual reentry requires an explicit snapshot or discard, never silently drops modified code", () => {
  const calls = [];
  const props = { modified: true, dirty: true, busy: false,
    onContinue: () => calls.push("code"), onSnapshot: () => calls.push("snapshot"), onDiscard: () => calls.push("discard") };
  const html = render(views.VisualReentryWarning, props);
  assert.match(html, /Unsaved/); assert.match(html, /Save code snapshot/);
  assert.match(html, /Discard active manual changes/); assert.match(html, /not an execution/);
  assert.match(html, /recorded source and results remain preserved/i);
  assert.deepEqual(calls, []);
  for (const action of buttons(views.VisualReentryWarning(props))) action.props.onClick();
  assert.deepEqual(calls, ["code", "snapshot", "discard"]);
});
test("modified baseline and unsaved persistence are distinct, including an empty Python file", () => {
  const { sourceState } = loadComponent("lib/api/code-drafts.ts");
  const draft = { baseline_source: "# generated\n", source: "# saved manual\n" };
  assert.deepEqual(sourceState(draft, draft.source), { modified: true, dirty: false });
  assert.deepEqual(sourceState(draft, ""), { modified: true, dirty: true });
  assert.deepEqual(sourceState(draft, draft.baseline_source), { modified: false, dirty: true });
});
