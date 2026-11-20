import { removalError } from "./lineage";
import { removeOutlier, repairNewStages } from "./outliers";
import { engineeringFitted, engineeringLabel, engineeringCategorical } from "./feature-engineering";
import { cleaningLabel, selectionStep } from "./cleaning";
import { imputationActive, removeAdvancedImputation } from "./imputation";
import type { Column } from "./api/projects";
import type { FeatureIntent, Operation, PipelineIR, PipelineIssue, TemporalExpression, DerivedExpression } from "./api/pipelines";

export type PrepStep = { id: string; cleaningId?: string; kind: "outlier" | "variance" | "engineering" | "cleaning" | "selection" | "source" | "parse" | "temporal" | "derived" | "advanced" | "participation" | "operation" | "legacy" | "dormant"; label: string; stage: string; column?: string; index?: number; inputs: string[]; outputs: string[]; invalid?: boolean };
export type ColumnAction = { id: "lineage" | "outliers" | "outlier-indicator" | "variance" | "engineering-numeric" | "engineering-bin" | "engineering-rare" | "engineering-ordinal" | "cleaning-normalize" | "cleaning-convert" | "cleaning-replace" | "cleaning-replace-missing" | "cleaning-datetime_fill" | "cleaning-validate" | "cleaning-missing_filter" | "cleaning-keep-missing" | "cleaning-filter" | "advanced-imputation" | "derived-create" | "profile" | "impute" | "scale" | "encode" | "participation" | "temporal-extract" | "temporal-cycle" | "temporal-difference" | "temporal-age" | "temporal-expression"; label: string };
const clone = <T,>(value: T): T => structuredClone(value);

export function references(expression: TemporalExpression | DerivedExpression, kind: "reference" | "column" = "reference"): string[] {
  if (expression.kind === kind) return [expression.name];
  return expression.kind === "call" ? expression.arguments.flatMap(arg => references(arg, kind)) : [];
}

export function columnActions(column: Pick<Column, "effective_semantic_type" | "physical_dtype">, target: boolean, included: boolean, raw = true): ColumnAction[] {
  const actions: ColumnAction[] = [{ id: "profile", label: "View Column Profile" }, { id: "lineage", label: "Inspect Feature Lineage" }];
  if (target) return actions;
  if (raw) actions.push(
    { id: "cleaning-missing_filter", label: "Remove Rows Where This Column Is Missing" }, { id: "cleaning-keep-missing", label: "Keep Rows Where This Column Is Missing" },
    { id: "cleaning-replace", label: "Replace Values" }, { id: "cleaning-replace-missing", label: "Replace With Missing" },
    { id: "cleaning-normalize", label: "Normalize Missing Tokens" }, { id: "cleaning-convert", label: "Change Data Type" },
    { id: "cleaning-datetime_fill", label: "Fill Missing Datetime" }, { id: "cleaning-validate", label: "Validate Column" });
  actions.push({ id: "cleaning-filter", label: "Filter Rows" });
  const type = column.effective_semantic_type;
  if (type !== "datetime") actions.push({ id: "derived-create", label: "Create Derived Feature" });
  if (type === "datetime") actions.push(
    { id: "temporal-extract", label: "Extract Date Components" }, { id: "temporal-cycle", label: "Cyclical Encoding" },
    { id: "temporal-difference", label: "Create Date Difference / Tenure" }, { id: "temporal-age", label: "Calculate Calendar Age" }, { id: "temporal-expression", label: "Open Temporal Expression Builder" },
  );
  const numeric = type === "continuous" && /^(u?int|float)\d+$/i.test(column.physical_dtype);
  const categorical = type === "categorical" || type === "binary";
  if (numeric || categorical) actions.push({ id: "impute", label: "Configure Imputation" }, { id: "advanced-imputation", label: "Advanced Imputation" });
  if (numeric) actions.push({ id: "outliers", label: "Treat Outliers" }, { id: "outlier-indicator", label: "Add Outlier Indicator" }, { id: "variance", label: "Review Feature Selection" });
  if (numeric) actions.push({ id: "engineering-numeric", label: "Transform Numeric" }, { id: "engineering-bin", label: "Bin Numeric" });
  if (categorical) actions.push({ id: "engineering-rare", label: "Group Rare Categories" }, { id: "engineering-ordinal", label: "Encode Ordinal" });
  if (numeric) actions.push({ id: "scale", label: "Configure Scaling" });
  if (categorical) actions.push({ id: "encode", label: "Configure One-hot Encoding" });
  if (numeric || categorical || included) actions.push({ id: "participation", label: included ? "Exclude from Model Input" : "Include as Model Feature" });
  return actions;
}

export function appliedSteps(ir: PipelineIR, columns: Pick<Column, "name" | "source_order">[]): PrepStep[] {
  const steps: PrepStep[] = [{ id: "source", kind: "source", label: "Source Dataset", stage: "Immutable source", inputs: [], outputs: columns.map(c => c.name) }];
  const cleaningSteps: PrepStep[] = (ir.cleaning?.steps ?? []).map(step => ({ id: `cleaning:${step.id}`, cleaningId: step.id, kind: selectionStep(step) ? "selection" : "cleaning", label: cleaningLabel(step), stage: selectionStep(step) ? "Dataset selection - before split; inference retains rows" : "Stateless source cleaning - before derivation", column: "column" in step ? step.column : undefined, inputs: "column" in step ? [step.column] : "columns" in step ? step.columns : [...references(step.condition, "column"), ...references(step.condition)], outputs: "column" in step ? [step.column] : [] }));
  steps.push(...cleaningSteps.filter(step => step.kind === "cleaning"));
  const temporal = ir.temporal;
  for (const name of Object.keys(temporal?.sources ?? {}).sort()) steps.push({ id: `parse:${encodeURIComponent(name)}`, kind: "parse", label: `Parse ${name}`, stage: "Stateless parsing · UTC", column: name, inputs: [name], outputs: [] });
  const definitions = new Map(temporal?.features.map(feature => [feature.name, feature]) ?? []);
  const ordered: string[] = [], visited = new Set<string>(), visiting = new Set<string>();
  function visit(name: string) {
    if (visited.has(name)) return;
    if (visiting.has(name) || !definitions.has(name)) throw new Error("Invalid temporal dependencies");
    visiting.add(name);
    for (const ref of references(definitions.get(name)!.expression)) visit(ref);
    visiting.delete(name); visited.add(name); ordered.push(name);
  }
  try {
    for (const name of definitions.keys()) visit(name);
    for (const name of ordered) {
      const expression = definitions.get(name)!.expression;
      steps.push({ id: `temporal:${name}`, kind: "temporal", label: `${expression.kind === "call" ? expression.operation.replaceAll("_", " ") : "Derived"}: ${name}`, stage: "Stateless derivation", column: name, inputs: [...references(expression, "column"), ...references(expression)], outputs: [name] });
    }
  } catch {
    steps.push({ id: "temporal-invalid", kind: "legacy", label: "Invalid temporal dependency group", stage: "Blocked · review existing definitions", inputs: Object.keys(temporal?.sources ?? {}), outputs: [...definitions.keys()], invalid: true });
  }
  const general = new Map(ir.derived?.features.map(feature => [feature.name, feature]) ?? []);
  const generalOrdered: string[] = [], generalVisited = new Set<string>(), generalVisiting = new Set<string>();
  function visitGeneral(name: string) {
    if (generalVisited.has(name)) return;
    if (generalVisiting.has(name) || !general.has(name)) throw new Error("Invalid derived dependencies");
    generalVisiting.add(name);
    const expression = general.get(name)!.expression;
    for (const ref of references(expression)) {
      if (general.has(ref)) visitGeneral(ref);
      else if (!definitions.has(ref)) throw new Error("Absent derived reference");
    }
    for (const ref of references(expression, "column")) if (!columns.some(column => column.name === ref) || ref === ir.target?.column) throw new Error("Invalid source reference");
    generalVisiting.delete(name); generalVisited.add(name); generalOrdered.push(name);
  }
  try {
    for (const name of general.keys()) visitGeneral(name);
    for (const name of generalOrdered) steps.push({ id: `derived:${name}`, kind: "derived", label: `Create ${name}`, stage: "Stateless derived-v1", column: name, inputs: [...references(general.get(name)!.expression, "column"), ...references(general.get(name)!.expression)], outputs: [name] });
  } catch {
    steps.push({ id: "derived-invalid", kind: "legacy", label: "Invalid derived dependency group", stage: "Blocked ? repair retained definitions", inputs: [], outputs: [...general.keys()], invalid: true });
  }
  steps.push(...cleaningSteps.filter(step => step.kind === "selection"));
  const names = [...columns.filter(c => c.name !== ir.target?.column).sort((a, b) => a.source_order - b.source_order).map(c => c.name), ...definitions.keys(), ...general.keys(), ...(ir.feature_engineering?.features ?? []).map(f => f.name), ...(ir.outlier_treatment?.features ?? []).flatMap(f => [f.name, ...(f.indicator ? [f.indicator] : [])])];
  if (Object.values(ir.features).some(feature => !feature.included) || names.some(name => !ir.features[name])) steps.push({ id: "participation", kind: "participation", label: "Feature Participation", stage: "Model input selection", inputs: [...new Set([...names, ...Object.keys(ir.features)])], outputs: Object.keys(ir.features).filter(name => ir.features[name].included), invalid: names.some(name => !ir.features[name]) });
  const usableNames = new Set(names);
  for (const [name, config] of Object.entries(ir.imputation?.columns ?? {})) {
    const groups = [...new Set(config.rules.flatMap(rule => rule.group_by))];
    const strategies = [...new Set(config.rules.map(rule => rule.strategy))].join(", ");
    steps.push({ id: `advanced:${encodeURIComponent(name)}`, kind: "advanced", label: `Advanced Imputation: ${name}`, stage: `${imputationActive(ir, name) ? "Train-fitted shared stage" : "Dormant; not executed"} - ${config.rules.length} rules (${strategies}); groups: ${groups.join(", ") || "global"}; indicator: ${config.indicator || "off"}`, column: name, inputs: [name, ...groups, ...config.rules.flatMap(rule => rule.condition ? [...references(rule.condition), ...references(rule.condition, "column")] : [])], outputs: [name, ...(config.indicator ? [config.indicator] : [])], invalid: !usableNames.has(name) });
  }

  for (const feature of ir.feature_engineering?.features ?? []) steps.push({ id: `engineering:${feature.name}`, kind: "engineering", label: engineeringLabel(feature), stage: `${engineeringFitted(feature) ? "Train-fitted" : "Stateless"} feature engineering - ${engineeringCategorical(feature) ? "categorical" : "numeric"} output; ${"bins" in feature ? `${feature.bins} requested bins` : "quantiles" in feature ? `${feature.quantiles} quantiles (${feature.distribution})` : "boundaries" in feature ? `boundaries: ${feature.boundaries.join(", ")}` : "invalid" in feature ? `invalid: ${feature.invalid}` : feature.method === "rare" ? `threshold: ${feature.min_count ?? feature.min_frequency}; unknown: ${feature.unknown}` : feature.method === "ordinal" ? `${feature.mapping.length} mappings; unknown: ${feature.unknown}` : "training parameters"}`, column: feature.name, inputs: [feature.source], outputs: [feature.name] });

  for (const feature of ir.outlier_treatment?.features ?? []) steps.push({ id: `outlier:${feature.name}`, kind: "outlier", label: `IQR clipping: ${feature.source} -> ${feature.name}${feature.indicator ? ` + indicator ${feature.indicator}` : ""}`, stage: `Train-fitted; multiplier ${feature.multiplier}; ${feature.tails} tails; missing: ${feature.missing}; invalid: ${feature.invalid}`, column: feature.name, inputs: [feature.source], outputs: [feature.name, ...(feature.indicator ? [feature.indicator] : [])] });
  const orphaned = Object.keys(ir.features).filter(name => !usableNames.has(name));
  for (const name of [...new Set([...names, ...Object.keys(ir.features)])]) {
    const feature = ir.features[name];
    if (!feature?.included || !usableNames.has(name)) continue;
    if (new Set(feature.operations.map(operation => operation.type)).size !== feature.operations.length) {
      steps.push({ id: `legacy-operations:${encodeURIComponent(name)}`, kind: "legacy", label: `Grouped invalid preparation: ${name}`, stage: "Blocked · duplicate operation families", column: name, inputs: [name], outputs: [], invalid: true });
      continue;
    }
    feature.operations.forEach((operation, index) => steps.push({ id: `operation:${encodeURIComponent(name)}:${index}`, kind: "operation", label: `${operation.type === "impute" ? `Impute (${operation.strategy})` : `${operation.type} (${operation.method})`}: ${name}`, stage: `Training-fitted branch · ${name}`, column: name, index, inputs: [name], outputs: operation.type === "encode" ? [] : [name] }));
  }
  const dormant = Object.keys(ir.features).filter(name => usableNames.has(name) && !ir.features[name].included && ir.features[name].operations.length);
  if (dormant.length) steps.push({ id: "dormant", kind: "dormant", label: "Stored Dormant Preparation", stage: "Not executed · excluded features", inputs: dormant, outputs: [] });
  if (orphaned.length) steps.push({ id: "legacy-features", kind: "legacy", label: "Absent or Invalid Feature Entries", stage: "Blocked · review legacy intent", inputs: orphaned, outputs: [], invalid: true });
  if (ir.feature_selection) steps.push({ id: "variance", kind: "variance", label: "Variance threshold selection", stage: `Train-fitted after branch imputation/scaling; variance > ${ir.feature_selection.threshold}`, inputs: [...ir.feature_selection.features], outputs: [] });
  return steps;
}

export function atStep(ir: PipelineIR, columns: Pick<Column, "name" | "source_order">[], id: string): PipelineIR {
  const steps = appliedSteps(ir, columns), end = steps.findIndex(step => step.id === id);
  if (end < 0) throw new Error("This step no longer exists.");
  const result = clone(ir);
  result.cleaning = null;
  result.feature_engineering = null;
  result.outlier_treatment = null;
  result.feature_selection = null;
  result.features = Object.fromEntries(columns.filter(c => c.name !== ir.target?.column).map(c => [c.name, { included: true, operations: [] }]));
  result.imputation = ir.imputation ? { version: "imputation-v1", columns: {} } : null;
  result.derived = ir.derived ? { ...clone(ir.derived), features: [] } : null;
  result.temporal = ir.temporal ? { ...clone(ir.temporal), sources: {}, features: [] } : null;
  for (const step of steps.slice(1, end + 1)) {
    if (step.kind === "legacy") throw new Error("An invalid configuration group has no reproducible stage preview. Edit its definitions first.");
    if (step.kind === "cleaning" || step.kind === "selection") {
      result.cleaning ??= { version: "cleaning-v1", steps: [] };
      result.cleaning.steps.push(clone(ir.cleaning!.steps.find(rule => rule.id === step.cleaningId)!));
    }
    if (step.kind === "parse") result.temporal!.sources[step.column!] = clone(ir.temporal!.sources[step.column!]);
    if (step.kind === "temporal") {
      result.temporal!.features.push(clone(ir.temporal!.features.find(feature => feature.name === step.column)!));
      result.features[step.column!] = { included: true, operations: [] };
    }
    if (step.kind === "derived") {
      result.derived!.features.push(clone(ir.derived!.features.find(feature => feature.name === step.column)!));
      result.features[step.column!] = { included: true, operations: [] };
    }
    if (step.kind === "participation") for (const name of Object.keys(result.features)) {
      if (ir.features[name]) result.features[name].included = ir.features[name].included;
      else delete result.features[name];
    }
    if (step.kind === "advanced") result.imputation!.columns[step.column!] = clone(ir.imputation!.columns[step.column!]);
    if (step.kind === "engineering") {
      result.feature_engineering ??= { version: "feature-engineering-v1", features: [] };
      result.feature_engineering.features.push(clone(ir.feature_engineering!.features.find(f => f.name === step.column)!));
      result.features[step.column!] = { included: ir.features[step.column!]?.included ?? true, operations: [] };
    }
    if (step.kind === "outlier") {
      const feature = clone(ir.outlier_treatment!.features.find(f => f.name === step.column)!);
      result.outlier_treatment ??= { version: "outlier-treatment-v1", features: [] };
      result.outlier_treatment.features.push(feature);
      for (const name of step.outputs) result.features[name] = { included: ir.features[name]?.included ?? false, operations: [] };
    }
    if (step.kind === "variance") result.feature_selection = clone(ir.feature_selection);
    if (step.kind === "operation") result.features[step.column!].operations.push(clone(ir.features[step.column!].operations[step.index!]));
    if (step.kind === "dormant") for (const name of step.inputs) result.features[name].operations = clone(ir.features[name].operations);
  }
  if (!result.temporal?.features.length && !Object.keys(result.temporal?.sources ?? {}).length) result.temporal = null;
  if (!result.derived?.features.length) result.derived = null;
  if (!Object.keys(result.imputation?.columns ?? {}).length) result.imputation = null;
  return result;
}

export function removeStep(ir: PipelineIR, step: PrepStep): PipelineIR {
  if (step.kind === "source") throw new Error("The Source step is immutable.");
  const produced = new Set([...(ir.temporal?.features ?? []), ...(ir.derived?.features ?? []), ...(ir.feature_engineering?.features ?? []), ...(ir.outlier_treatment?.features ?? [])].map(f => f.name));
  for (const f of ir.outlier_treatment?.features ?? []) if (f.indicator) produced.add(f.indicator);
  const raw = [...new Set([...Object.keys(ir.features).filter(name => !produced.has(name)), ...Object.keys(ir.temporal?.sources ?? {})])].map((name, source_order) => ({ name, source_order }));
  const blocked = removalError(appliedSteps(ir, raw), step.id);
  if (blocked) throw new Error(blocked);
  if (step.kind === "outlier") return removeOutlier(ir, step.column!);
  if (step.kind === "variance") return { ...ir, feature_selection: null };
  if (step.kind === "advanced") return removeAdvancedImputation(ir, step.column!);
  const next = clone(ir);
  if (step.kind === "cleaning" || step.kind === "selection") {
    const steps = next.cleaning!.steps.filter(rule => rule.id !== step.cleaningId);
    next.cleaning = steps.length ? { version: "cleaning-v1", steps } : null;
  }
  if (step.kind === "engineering") {
    const features = next.feature_engineering!.features.filter(f => f.name !== step.column);
    next.feature_engineering = features.length ? { version: "feature-engineering-v1", features } : null;
    delete next.features[step.column!];
  }
  if (step.kind === "parse") delete next.temporal!.sources[step.column!];
  if (step.kind === "temporal") {
    next.temporal!.features = next.temporal!.features.filter(feature => feature.name !== step.column);
    delete next.features[step.column!];
  }
  if (step.kind === "derived") {
    next.derived!.features = next.derived!.features.filter(feature => feature.name !== step.column);
    delete next.features[step.column!];
  }
  if (step.kind === "operation") next.features[step.column!].operations.splice(step.index!, 1);
  if (step.kind === "participation") for (const name of step.inputs) {
    if (name === next.target?.column) continue;
    next.features[name] ??= { included: true, operations: [] };
    next.features[name].included = true;
  }
  if (step.kind === "dormant") for (const name of step.inputs) next.features[name].operations = [];
  if (step.id === "legacy-features") for (const name of step.inputs) delete next.features[name];
  else if (step.id.startsWith("legacy-operations:") && step.column) next.features[step.column].operations = [];
  else if (step.id === "derived-invalid") {
    for (const feature of next.derived?.features ?? []) delete next.features[feature.name];
    next.derived = null;
  }
  else if (step.kind === "legacy") {
    for (const feature of next.temporal?.features ?? []) delete next.features[feature.name];
    next.temporal = null;
  }
  return repairNewStages(next, Object.keys(ir.features).filter(name => !(name in next.features)));
}

export function setOperation(feature: FeatureIntent, family: Operation["type"], value: string): FeatureIntent {
  const operations = feature.operations.filter(operation => operation.type !== family);
  if (value) {
    const operation = (family === "impute" ? { type: family, strategy: value } : { type: family, method: value }) as Operation;
    if (family === "impute") operations.unshift(operation); else operations.push(operation);
  }
  return { ...feature, operations };
}

export function preparationErrors(issues: PipelineIssue[]): string[] {
  return issues.filter(issue => issue.severity === "blocking" && (issue.scope !== "train" || issue.column || issue.code.startsWith("feature_"))).map(issue => issue.message);
}

export type DraftHistory = { past: PipelineIR[]; present: PipelineIR; future: PipelineIR[] };
export const draftHistory = (ir: PipelineIR): DraftHistory => ({ past: [], present: clone(ir), future: [] });
export const changeDraft = (history: DraftHistory, next: PipelineIR): DraftHistory => JSON.stringify(next) === JSON.stringify(history.present) ? history : ({ past: [...history.past, clone(history.present)].slice(-30), present: clone(next), future: [] });
export const undoDraft = (history: DraftHistory): DraftHistory => history.past.length ? ({ past: history.past.slice(0, -1), present: clone(history.past.at(-1)!), future: [clone(history.present), ...history.future].slice(0, 30) }) : history;
export const redoDraft = (history: DraftHistory): DraftHistory => history.future.length ? ({ past: [...history.past, clone(history.present)].slice(-30), present: clone(history.future[0]), future: history.future.slice(1) }) : history;

// Tab-memory recovery only: backend IR remains authoritative and must match the base.
type StudioSession = { revision: number; base: string; columns: string; history: DraftHistory };
const sessions = new Map<string, StudioSession>();
const sessionKey = (project: string, dataset: string) => JSON.stringify([project, dataset]);
export function rememberStudioSession(project: string, dataset: string, value: StudioSession) {
  const key = sessionKey(project, dataset);
  if (!sessions.has(key) && sessions.size >= 5) sessions.delete(sessions.keys().next().value!);
  sessions.set(key, clone(value));
}
export const readStudioSession = (project: string, dataset: string) => {
  const value = sessions.get(sessionKey(project, dataset));
  return value ? clone(value) : null;
};
export const clearStudioSession = (project: string, dataset: string) => sessions.delete(sessionKey(project, dataset));
