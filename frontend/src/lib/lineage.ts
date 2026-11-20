type Step = { id: string; kind: string; column?: string; inputs: string[]; outputs: string[]; label: string; stage: string };
const producers = new Set(["temporal", "derived", "engineering", "outlier", "advanced", "parse"]);
export function stepOutputs(step: Step): string[] {
  return step.kind === "parse" ? [step.column!] : step.kind === "advanced" ? step.outputs.filter(name => name !== step.column) : producers.has(step.kind) ? step.outputs : [];
}
export function dependentSteps(steps: Step[], id: string): Step[] {
  const index = steps.findIndex(step => step.id === id);
  if (index < 0) return [];
  const names = new Set(stepOutputs(steps[index])), found: Step[] = [];
  for (const step of steps.slice(index + 1)) {
    if (["participation", "source", "dormant"].includes(step.kind) || step.kind === "operation" && step.column && names.has(step.column)) continue;
    if (step.inputs.some(name => names.has(name))) { found.push(step); stepOutputs(step).forEach(name => names.add(name)); }
  }
  return found;
}
export function removalError(steps: Step[], id: string): string | null {
  const dependents = dependentSteps(steps, id);
  return dependents.length ? `Cannot remove this transformation. Remove dependent steps first: ${dependents.map(step => step.label).join(", ")}.` : null;
}
export function editDependencyError(before: Step[], after: Step[], explicitBulkRemoval = false): string | null {
  if (explicitBulkRemoval) return null;
  const available = new Set(after.flatMap(stepOutputs));
  for (const step of before) {
    const lost = stepOutputs(step).filter(name => !available.has(name));
    if (!lost.length) continue;
    const retained = dependentSteps(before, step.id);
    if (retained.length) return `Edit would remove inputs still used by ${retained.map(step => step.label).join(", ")}. Remove or repair those dependents first.`;
  }
  return null;
}
export function featureLineage(steps: Step[], name: string) {
  const producer = steps.find(step => step.kind === "advanced" && step.column === name) ?? steps.find(step => stepOutputs(step).includes(name));
  const direct = producer?.inputs.filter(input => input !== name) ?? [];
  const seen = new Set<string>();
  function visit(value: string) { if (seen.has(value) || value === name) return; seen.add(value); const step = steps.find(s => stepOutputs(s).includes(value)); step?.inputs.filter(input => input !== value).forEach(visit); }
  direct.forEach(visit);
  return { producer, direct, ancestors: [...seen], dependents: producer ? dependentSteps(steps, producer.id).map(step => step.label) : steps.filter(step => step.inputs.includes(name)).map(step => step.label) };
}
