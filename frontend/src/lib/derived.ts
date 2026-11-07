import type { DerivedExpression, DerivedOperation, PipelineIR } from "./api/pipelines";

export const derivedOperations: DerivedOperation[] = ["add", "subtract", "multiply", "safe_divide", "modulo", "abs", "negate", "power", "sqrt", "log", "log1p", "round", "floor", "ceil", "minimum", "maximum", "equal", "not_equal", "greater", "greater_equal", "less", "less_equal", "and", "or", "not", "is_missing", "is_not_missing", "if", "trim", "lower", "upper", "length", "starts_with", "ends_with", "contains", "concat", "replace", "coalesce"];
const unary = new Set<DerivedOperation>(["abs", "negate", "sqrt", "log", "log1p", "round", "floor", "ceil", "not", "is_missing", "is_not_missing", "trim", "lower", "upper", "length"]);
export const derivedArity = (operation: DerivedOperation) => unary.has(operation) ? 1 : operation === "if" || operation === "replace" ? 3 : 2;
export const derivedCall = (operation: DerivedOperation, args: DerivedExpression[], parameters: { precision?: number } = {}): DerivedExpression => ({ kind: "call", operation, arguments: args, parameters });
export const canGuideDerived = (expression: DerivedExpression) => expression.kind === "call" && expression.arguments.every(argument => argument.kind !== "call") && expression.arguments.length === derivedArity(expression.operation);

export function derivedReferences(expression: DerivedExpression): string[] {
  return expression.kind === "reference" ? [expression.name] : expression.kind === "call" ? expression.arguments.flatMap(derivedReferences) : [];
}

/** Structural checks only. Dataset typing and all computation belong to the backend preview. */
export function derivedExpressionError(expression: DerivedExpression): string | null {
  let nodes = 0;
  function visit(value: DerivedExpression, depth: number): string | null {
    if (depth > 8) return "Expressions can have at most 8 levels.";
    if (++nodes > 256) return "Expressions can have at most 256 nodes.";
    if (value.kind === "column" || value.kind === "reference") return value.name ? null : "Choose every input column or derived reference.";
    if (value.kind === "literal") {
      if (typeof value.value === "string" && value.value.length > 1000) return "Text constants can have at most 1000 characters.";
      if (typeof value.value === "number" && !Number.isFinite(value.value)) return "Enter a finite numeric constant.";
      return null;
    }
    if (value.kind !== "call") return "Choose a supported expression input.";
    if (!derivedOperations.includes(value.operation)) return "Choose a supported operation.";
    const variable = value.operation === "concat" || value.operation === "coalesce";
    if (variable ? value.arguments.length < 2 || value.arguments.length > 16 : value.arguments.length !== derivedArity(value.operation)) return "This operation has an invalid number of inputs.";
    if (value.operation === "round" && value.parameters.precision != null && (!Number.isInteger(value.parameters.precision) || Math.abs(value.parameters.precision) > 12)) return "Rounding precision must be an integer from -12 to 12.";
    for (const argument of value.arguments) { const error = visit(argument, depth + 1); if (error) return error; }
    return null;
  }
  return visit(expression, 1);
}

export function derivedRecipe(ir: PipelineIR, name: string, expression: DerivedExpression, sourceNames: string[], editing?: string): PipelineIR {
  if (!name.trim() || name.length > 200) throw new Error("Enter an output name with 1 to 200 characters.");
  if (name !== name.trim()) throw new Error("Remove leading or trailing spaces from the output name.");
  if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(name)) throw new Error("Start the output name with a letter and use only letters, numbers and underscores.");
  const retained = (ir.derived?.features ?? []).filter(feature => feature.name !== editing);
  if (sourceNames.includes(name) || name === ir.target?.column || ir.temporal?.features.some(feature => feature.name === name) || retained.some(feature => feature.name === name)) throw new Error("A source or derived feature already uses this name.");
  if (retained.length >= 128) throw new Error("A recipe can have at most 128 derived features.");
  const error = derivedExpressionError(expression);
  if (error) throw new Error(error);
  if (derivedReferences(expression).includes(name)) throw new Error("A derived feature cannot reference itself.");
  function usesTarget(value: DerivedExpression): boolean { return value.kind === "column" ? value.name === ir.target?.column : value.kind === "call" && value.arguments.some(usesTarget); }
  if (usesTarget(expression)) throw new Error("The target column cannot be used as an input feature.");
  const features = { ...ir.features };
  if (editing && editing !== name) delete features[editing];
  if (!Object.hasOwn(features, name)) features[name] = { included: true, operations: [] };
  return { ...ir, derived: { version: "derived-v1", features: [...retained, { name, expression }] }, features };
}

/** Evaluate one repair in isolation while retaining all definitions in the applied candidate. */
export function derivedPreviewRecipe(ir: PipelineIR, name: string): PipelineIR {
  const definitions = ir.derived?.features ?? [];
  const byName = new Map(definitions.map(feature => [feature.name, feature]));
  const temporalNames = new Set(ir.temporal?.features.map(feature => feature.name) ?? []);
  const selected = new Set<string>(), visiting = new Set<string>();
  function visit(reference: string) {
    if (selected.has(reference)) return;
    if (visiting.has(reference)) throw new Error(`Circular derived reference involving ${reference}. Repair this dependency before previewing.`);
    const feature = byName.get(reference);
    if (!feature) {
      if (temporalNames.has(reference)) return;
      throw new Error(`Missing derived reference: ${reference}. Repair this input before previewing.`);
    }
    visiting.add(reference);
    for (const dependency of derivedReferences(feature.expression)) visit(dependency);
    visiting.delete(reference); selected.add(reference);
  }
  visit(name);
  const features = { ...ir.features };
  for (const feature of definitions) if (!selected.has(feature.name)) delete features[feature.name];
  return { ...ir, features, derived: { version: "derived-v1", features: definitions.filter(feature => selected.has(feature.name)) } };
}

