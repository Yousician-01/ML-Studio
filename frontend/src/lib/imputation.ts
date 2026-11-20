import type { ColumnImputation, DerivedExpression, ImputationRule, ImputationStrategy, PipelineIR } from "./api/pipelines";
import type { Column } from "./api/projects";
import { derivedExpressionError } from "./derived";

export function imputationStrategies(column: Column): ImputationStrategy[] {
  return column.effective_semantic_type === "continuous" && /int|float|double|decimal|numeric/i.test(column.physical_dtype)
    ? ["constant", "mean", "median", "most_frequent"] : ["constant", "most_frequent"];
}

export function imputationInputs(ir: PipelineIR, columns: Column[]) {
  const indicators = new Set(Object.values(ir.imputation?.columns ?? {}).map(config => config.indicator).filter(Boolean));
  const references = [...(ir.temporal?.features ?? []), ...(ir.derived?.features ?? [])].map(feature => feature.name).filter(name => name !== ir.target?.column && !indicators.has(name));
  const source = columns.map(column => column.name).filter(name => name !== ir.target?.column && !indicators.has(name) && !references.includes(name));
  return { columns: source, references, all: [...source, ...references] };
}

/** Structural checks only; the backend owns expression typing and dataset validation. */
export function imputationRecipe(ir: PipelineIR, name: string, config: ColumnImputation, columns: Column[]): PipelineIR {
  const column = columns.find(column => column.name === name);
  if (name === ir.target?.column) throw new Error("The supervised target cannot be imputed.");
  if (!column || !["continuous", "categorical", "binary"].includes(column.effective_semantic_type)) throw new Error("Choose a compatible imputation target.");
  if (!ir.features[name]) throw new Error("The imputation target must have a feature configuration.");
  const previous = ir.imputation?.columns[name];
  if (!previous && Object.keys(ir.imputation?.columns ?? {}).length >= 64) throw new Error("A recipe can have at most 64 advanced imputation targets.");
  if (!config.rules.length || config.rules.length > 16) throw new Error("Configure between 1 and 16 ordered rules.");
  const available = imputationInputs(ir, columns), strategies = imputationStrategies(column);
  function checkStrategy(strategy: string, value: ImputationRule["value"]) {
    if (strategy === "leave_missing") return;
    if (!strategies.includes(strategy as ImputationStrategy)) throw new Error("Choose a compatible strategy for this target type.");
    if (strategy === "constant" && (value === null || typeof value === "number" && !Number.isFinite(value))) throw new Error("Enter a nonmissing, finite constant.");
    if (typeof value === "string" && value.length > 1000) throw new Error("Text constants can have at most 1000 characters.");
  }
  function checkInputs(expression: DerivedExpression) {
    if (expression.kind === "column" || expression.kind === "reference") {
      const names = expression.kind === "column" ? available.columns : available.references;
      if (!names.includes(expression.name)) throw new Error(`Unavailable ${expression.kind} input: ${expression.name}. The supervised target and indicators cannot be inputs.`);
    } else if (expression.kind === "call") expression.arguments.forEach(checkInputs);
  }
  for (const rule of config.rules) {
    checkStrategy(rule.strategy, rule.value);
    if (rule.group_by.length > 4 || new Set(rule.group_by).size !== rule.group_by.length) throw new Error("Choose at most 4 distinct grouping columns.");
    if (rule.group_by.some(group => group === name || !available.all.includes(group))) throw new Error("Grouping columns must exist before imputation and cannot include the imputation target.");
    if (rule.strategy === "constant" && rule.group_by.length) throw new Error("Constant rules do not use grouping columns.");
    if (rule.condition) {
      const error = derivedExpressionError(rule.condition);
      if (error) throw new Error(error);
      checkInputs(rule.condition);
    }
  }
  checkStrategy(config.fallback.strategy, config.fallback.value);
  if (config.indicator !== null) {
    if (config.indicator.length > 200 || !/^[A-Za-z][A-Za-z0-9_]*$/.test(config.indicator)) throw new Error("Indicator names must start with a letter and contain at most 200 letters, numbers or underscores.");
    const names = new Set([...columns.map(column => column.name), ...Object.keys(ir.features), ...(ir.temporal?.features ?? []).map(feature => feature.name), ...(ir.derived?.features ?? []).map(feature => feature.name), ir.target?.column]);
    if (previous?.indicator) names.delete(previous.indicator);
    // A stored indicator may appear in the materialized schema, but may never hide a real definition.
    if (columns.some(column => column.name === config.indicator && column.name !== previous?.indicator) || (ir.temporal?.features ?? []).some(feature => feature.name === config.indicator) || (ir.derived?.features ?? []).some(feature => feature.name === config.indicator)) names.add(config.indicator);
    if (names.has(config.indicator) || Object.entries(ir.imputation?.columns ?? {}).some(([target, other]) => target !== name && other.indicator === config.indicator)) throw new Error("A source, derived feature or indicator already uses this name.");
  }
  const features = { ...ir.features };
  const legacy = features[name].operations.find(operation => operation.type === "impute");
  features[name] = { ...features[name], operations: features[name].operations.filter(operation => operation.type !== "impute") };
  if (previous?.indicator) delete features[previous.indicator];
  return { ...ir, features, imputation: { version: "imputation-v1", columns: { ...ir.imputation?.columns, [name]: { ...config, previous_strategy: previous ? previous.previous_strategy : legacy?.type === "impute" ? legacy.strategy : null } } } };
}

/** Remove this stage only. Downstream references remain visible for repair. */
export function removeAdvancedImputation(ir: PipelineIR, name: string): PipelineIR {
  const previous = ir.imputation?.columns[name];
  if (!previous) return ir;
  const columns = { ...ir.imputation!.columns }, features = { ...ir.features };
  delete columns[name];
  if (previous.indicator) delete features[previous.indicator];
  const feature = features[name];
  if (feature && previous.previous_strategy && !feature.operations.some(operation => operation.type === "impute")) features[name] = { ...feature, operations: [{ type: "impute", strategy: previous.previous_strategy }, ...feature.operations] };
  const result = { ...ir, features };
  if (Object.keys(columns).length) result.imputation = { version: "imputation-v1", columns };
  else delete result.imputation;
  return result;
}

/** Shared stage remains active for direct inputs consumed by engineering. */
export const imputationActive = (ir: PipelineIR, name: string) => Boolean(ir.features[name]?.included || ir.feature_engineering?.features.some(feature => feature.source === name) || ir.outlier_treatment?.features.some(feature => feature.source === name));
