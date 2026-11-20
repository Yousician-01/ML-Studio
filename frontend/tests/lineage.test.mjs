import test from "node:test";
import assert from "node:assert/strict";
import { loadComponent } from "./load-component.mjs";
const { removalError, editDependencyError, featureLineage } = loadComponent("lib/lineage.ts");
const steps = [
  { id: "source", kind: "source", inputs: [], outputs: ["x"], label: "Source" },
  { id: "derived:a", kind: "derived", inputs: ["x"], outputs: ["a"], label: "Create a" },
  { id: "engineering:b", kind: "engineering", inputs: ["a"], outputs: ["b"], label: "Log b" },
  { id: "outlier:c", kind: "outlier", inputs: ["b"], outputs: ["c"], label: "Cap c" },
];
test("removal blocks direct/transitive dependents without mutating history", () => {
  assert.match(removalError(steps, "derived:a"), /Log b.*Cap c/);
  assert.equal(removalError(steps, "outlier:c"), null);
  const { draftHistory, changeDraft, undoDraft } = loadComponent("lib/preparation.ts");
  const before = { features: {}, derived: { features: [{ name: "a" }] } }, history = draftHistory(before);
  assert.deepEqual(undoDraft(changeDraft(history, { features: {} })).present, before);
});
test("lineage exposes ancestors and editing cannot strand retained dependencies", () => {
  assert.deepEqual(featureLineage(steps, "c").ancestors, ["b", "a", "x"]);
  assert.match(editDependencyError(steps, steps.filter(s => s.id !== "derived:a")), /Remove or repair/);
  assert.equal(editDependencyError(steps, [steps[0]], true), null);
});
test("guided engineering allows prior stateless sources and rejects fitted/forward ones", () => {
  const { engineeringRecipe, newEngineeringFeature } = loadComponent("lib/feature-engineering.ts");
  const columns = [{ name: "x" }, { name: "a" }];
  const ir = { features: { x: { included: false, operations: [] }, a: { included: true, operations: [] } }, feature_engineering: { version: "feature-engineering-v1", features: [{ ...newEngineeringFeature("log1p", "x"), name: "a" }] } };
  const chained = engineeringRecipe(ir, { ...newEngineeringFeature("sqrt", "a"), name: "b" }, columns);
  assert.equal(chained.feature_engineering.features[1].source, "a");
  assert.throws(() => engineeringRecipe({ ...ir, feature_engineering: { ...ir.feature_engineering, features: [{ ...newEngineeringFeature("quantile", "x"), name: "a" }] } }, { ...newEngineeringFeature("sqrt", "a"), name: "b" }, columns), /stateless/);
});
