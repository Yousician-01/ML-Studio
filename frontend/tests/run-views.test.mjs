// Use the existing TypeScript compiler and React server renderer; no DOM/test framework.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { runInThisContext } from "node:vm";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../src");
const cache = new Map();
function load(file) {
  if (cache.has(file)) return cache.get(file).exports;
  const module = { exports: {} };
  cache.set(file, module);
  const source = ts.transpileModule(readFileSync(file, "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true, target: ts.ScriptTarget.ES2022 } }).outputText;
  const localRequire = name => {
    if (!name.startsWith(".") && !name.startsWith("@/")) return require(name);
    const stem = name.startsWith("@/") ? resolve(root, name.slice(2)) : resolve(dirname(file), name);
    const target = [stem + ".ts", stem + ".tsx"].find(existsSync);
    if (!target) throw new Error(`Unresolved test import ${name}`);
    return load(target);
  };
  runInThisContext(`(function(require,module,exports){${source}\n})`, { filename: file })(localRequire, module, module.exports);
  return module.exports;
}
const { RunSummary, Runs } = load(resolve(root, "components/runs.tsx"));
const { api, ApiError } = load(resolve(root, "lib/api/projects.ts"));
const base = { id: "run-one", project_id: "project-one", dataset_id: "dataset-one", sequence: 3, started_at: null, summary: { model: { name: "LogisticRegression" } }, state: "RUNNING", failure: null, result: null };
const render = run => renderToStaticMarkup(React.createElement(RunSummary, { run }));

test("active Run reports real lifecycle without fake progress or cancel controls", () => {
  const html = render(base);
  assert.match(html, /Running experiment/);
  assert.match(html, /Execution continues/);
  assert.match(html, /aria-live="polite"/);
  assert.doesNotMatch(html, /progressbar|Cancel|Retry execution/);
});

test("successful summary shows test population and unavailable AUC honestly", () => {
  const html = render({ ...base, state: "SUCCEEDED", result: { population: { test: 4 }, metrics: { accuracy: 0.75, precision: 1, recall: 0.5, f1: 2 / 3, roc_auc: null }, roc_auc_unavailable_reason: "Held-out target contains only one class." } });
  assert.match(html, /Succeeded/);
  assert.match(html, /0.7500/);
  assert.match(html, /4 rows/);
  assert.match(html, /Unavailable/);
  assert.match(html, /Held-out target contains only one class/);
  assert.match(html, /view=runs&amp;run=run-one/);
});

test("failed summary shows safe stage/code/message and no success metrics", () => {
  const html = render({ ...base, state: "FAILED", failure: { stage: "training", code: "nonzero_exit", message: "Execution did not complete successfully." } });
  assert.match(html, /Failed/);
  assert.match(html, /training/);
  assert.match(html, /nonzero_exit/);
  assert.match(html, /role="alert"/);
  assert.doesNotMatch(html, /Accuracy|Traceback|stderr/);
});

test("Runs list and deep-linked detail have accessible initial loading states", () => {
  const list = renderToStaticMarkup(React.createElement(Runs, { projectId: "project-one", runId: null }));
  const detail = renderToStaticMarkup(React.createElement(Runs, { projectId: "project-one", runId: "run-one" }));
  assert.match(list, /Loading experiment history/);
  assert.match(detail, /Loading frozen Run/);
  assert.match(detail, /Refresh Run/);
  assert.match(list, /role="status"/);
});

test("historical Code and paginated history use dedicated Run endpoints", async context => {
  const urls = [];
  context.mock.method(globalThis, "fetch", async url => {
    urls.push(url);
    return new Response("{}", { status: 200 });
  });
  await api.runCode("project-one", "run-one");
  await api.runs("project-one", 20, undefined, "request-one");
  assert.match(urls[0], /\/projects\/project-one\/runs\/run-one\/code$/);
  assert.match(urls[1], /\/runs\?limit=20&offset=20&request_id=request-one$/);
});

test("stale rejection surfaces without automatic POST retry", async context => {
  let calls = 0;
  context.mock.method(globalThis, "fetch", async () => {
    calls++;
    return new Response(JSON.stringify({ detail: "Project changed. Refresh Code before executing." }), { status: 409 });
  });
  await assert.rejects(api.createRun("project-one", {}), error => error instanceof ApiError && error.status === 409);
  assert.equal(calls, 1);
});

test("uncertain transport failure does not cause an automatic second submission", async context => {
  let calls = 0;
  context.mock.method(globalThis, "fetch", async () => { calls++; throw new Error("Lost response"); });
  await assert.rejects(api.createRun("project-one", {}), error => error instanceof ApiError && error.status === 0);
  assert.equal(calls, 1);
});
