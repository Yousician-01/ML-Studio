import test from "node:test";
import assert from "node:assert/strict";
import { loadComponent } from "./load-component.mjs";
test("unsaved Code survives workspace unmount through a revision-bound tab buffer", () => {
  const buffers = loadComponent("lib/code-draft-buffer.ts");
  const buffer = { draftId: "d", revision: 3, source: "# unsaved\n" };
  buffers.writeCodeBuffer("p", buffer);
  assert.deepEqual(buffers.readCodeBuffer("p"), buffer);
  const restored = buffers.resolveCodeBuffer(buffers.readCodeBuffer("p"), { id: "d", revision: 3, source: "# saved" });
  assert.equal(restored.source, buffer.source); assert.equal(restored.conflict, null);
  buffers.clearCodeBuffer("p"); assert.equal(buffers.readCodeBuffer("p"), null);
});
test("a stale or ended Code session retains text for inspection and never rebases it", () => {
  const { resolveCodeBuffer } = loadComponent("lib/code-draft-buffer.ts");
  const old = { draftId: "old", revision: 1, source: "# valuable unsaved changes" };
  for (const draft of [null, { id: "new", revision: 1, source: "# current" }, { id: "old", revision: 2, source: "# current" }]) {
    const restored = resolveCodeBuffer(old, draft);
    assert.equal(restored.source, draft?.source ?? ""); assert.equal(restored.conflict, old);
  }
});
