import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "./load-component.mjs";

test("workbench navigation keeps canonical destinations, active state and a skip link", () => {
  const { AppShell } = loadComponent("components/app-shell.tsx");
  const html = renderToStaticMarkup(React.createElement(AppShell, { project: { id: "p", name: "Customer outcomes" }, view: "train" }, React.createElement("main", {id:"main-content"}, "Workspace")));
  assert.match(html, /href="#main-content"/);
  assert.match(html, /aria-label="Project workflow"/);
  for (const view of ["data", "explore", "prepare", "train", "evaluate", "runs", "code"]) assert.match(html, new RegExp(`href="/projects/p\\?view=${view}"`));
  assert.match(html, /aria-current="page"[^>]*>.*?Train/s);
  assert.doesNotMatch(html, /Billing|Cloud deployment|Teams|AI Advisor/);
});

test("shared matrix handles fifty typed classes without binary mislabelling", () => {
  const { ConfusionMatrixView } = loadComponent("components/run-results.tsx");
  const labels = Array.from({length:50}, (_, value) => ({value_type:"integer", value}));
  const values = labels.map((_, i) => labels.map((_, j) => i === j ? 2 : 0));
  const html = renderToStaticMarkup(React.createElement(ConfusionMatrixView, {matrix:{labels,values}}));
  assert.match(html, /tabindex="0"/);
  assert.match(html, /role="region"/);
  assert.match(html, /49.*integer/);
  assert.equal((html.match(/scope="row"/g) ?? []).length, 50);
  assert.doesNotMatch(html, /Negative then positive|>Positive<|>Negative<|<span>TN<\/span>/);
});

test("Project creation offers all three real objectives without allowing task changes in settings", () => {
  const { ProjectForm } = loadComponent("components/project-form.tsx");
  const create = renderToStaticMarkup(React.createElement(ProjectForm, {onSave:async()=>{},submitLabel:"Create Project"}));
  for (const task of ["binary_classification", "multiclass_classification", "regression"]) assert.match(create,new RegExp(`name="ml_objective"[^>]*value="${task}"`));
  assert.equal((create.match(/type="radio"/g) ?? []).length,3);
  const settings = renderToStaticMarkup(React.createElement(ProjectForm, {initial:{name:"Classes",ml_objective:"multiclass_classification"},onSave:async()=>{},submitLabel:"Save Project"}));
  assert.match(settings,/Multiclass Classification/);
  assert.doesNotMatch(settings,/name="ml_objective"/);
});
