import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { loadComponent } from "./load-component.mjs";

test("an unmounted editor's pending save cannot clear a newer editor's recovery text", async () => {
  const buffers = loadComponent("lib/code-draft-buffer.ts");
  const draft = { id: "d", revision: 1, source: "# A", baseline_source: "# generated" };
  const effects = [];
  let index = 0, complete;
  const saving = new Promise(resolve => { complete = resolve; });
  const react = { ...React,
    useState: initial => { const slot = index++; return [slot === 0 ? draft : slot === 1 ? draft.source : slot === 2 ? true : initial, () => {}]; },
    useRef: initial => ({ current: typeof initial === "string" ? draft.source : initial }),
    useEffect: callback => effects.push(callback),
  };
  const { CodeModeProvider } = loadComponent("components/code-mode-state.tsx", {
    react, "@/lib/code-draft-buffer": buffers,
    "@/lib/api/projects": { api: { activeCodeDraft: () => new Promise(() => {}), saveCodeDraft: () => saving } },
  });
  const tree = CodeModeProvider({ projectId: "p", children: null });
  const cleanup = effects[0]();
  buffers.writeCodeBuffer("p", { draftId: "d", revision: 1, source: "# A" });
  const pending = tree.props.value.save();
  cleanup(); // Browser Back unmounts this provider while the HTTP save is pending.
  const newer = { draftId: "d", revision: 1, source: "# B typed after returning" };
  buffers.writeCodeBuffer("p", newer);
  complete({ ...draft, revision: 2 });
  await pending;
  assert.deepEqual(buffers.readCodeBuffer("p"), newer);
});
