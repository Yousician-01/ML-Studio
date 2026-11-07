"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/projects";
import type { DerivedExpression, DerivedOperation, PipelineIR, TemporalPreview, WorkingPipeline } from "@/lib/api/pipelines";
import { canGuideDerived, derivedArity, derivedCall, derivedOperations, derivedPreviewRecipe, derivedRecipe, derivedReferences } from "@/lib/derived";
import { Alert, Button, Panel } from "./ui";

type ExpressionProps = { value: DerivedExpression; onChange: (value: DerivedExpression) => void; columns: string[]; references: string[]; depth?: number; leafOnly?: boolean };
const emptyInput = (): DerivedExpression => ({ kind: "column", name: "" });

function OperationControls({ value, onChange }: { value: Extract<DerivedExpression, { kind: "call" }>; onChange: (value: DerivedExpression) => void }) {
  return <>
    <label>Operation<select value={value.operation} onChange={event => {
      const operation = event.target.value as DerivedOperation;
      onChange(derivedCall(operation, Array.from({ length: derivedArity(operation) }, (_, index) => value.arguments[index] ?? emptyInput()), operation === "round" ? { precision: 0 } : {}));
    }}>{derivedOperations.map(operation => <option key={operation} value={operation}>{operation.replaceAll("_", " ")}</option>)}</select></label>
    {value.operation === "round" && <label>Decimal precision<input type="number" min={-12} max={12} step={1} value={value.parameters.precision ?? 0} onChange={event => onChange({ ...value, parameters: { precision: Number(event.target.value) } })} /></label>}
    {value.operation === "safe_divide" && <p className="muted">Zero or missing denominators produce missing values.</p>}
    {["sqrt", "log", "log1p", "power"].includes(value.operation) && <p className="muted">Invalid domains and overflow produce missing values. Preview reports invalid results.</p>}
    {value.operation === "replace" && <p className="muted">Inputs: text, literal substring to find, replacement. No regular expressions.</p>}
    {value.operation === "if" && <p className="muted">Inputs: condition, value if true, value if false. Both branches must have compatible types.</p>}
    {value.operation === "coalesce" && <p className="muted">Choose the first nonmissing value in each row. Inputs must have compatible types.</p>}
  </>;
}

function ExpressionInput({ value, onChange, columns, references, depth = 1, leafOnly = false }: ExpressionProps) {
  const literalType = value.kind === "literal" ? value.value === null ? "null" : typeof value.value : "string";
  return <fieldset className="panel" aria-label={`Derived expression level ${depth}`}>
    <label>Input kind<select value={value.kind} onChange={event => {
      const kind = event.target.value;
      onChange(kind === "column" ? emptyInput() : kind === "reference" ? { kind: "reference", name: "" } : kind === "literal" ? { kind: "literal", value: "" } : derivedCall("add", [emptyInput(), emptyInput()]));
    }}><option value="column">Source column</option><option value="reference">Derived feature reference</option><option value="literal">Constant</option>{(!leafOnly && depth < 8 || value.kind === "call") && <option value="call">Nested operation</option>}</select></label>
    {(value.kind === "column" || value.kind === "reference") && <label>{value.kind === "column" ? "Source column" : "Derived reference"}<select value={value.name} onChange={event => onChange({ ...value, name: event.target.value })}><option value="">Choose an input</option>{(value.kind === "column" ? columns : references).map(name => <option key={name} value={name}>{name}</option>)}</select></label>}
    {value.kind === "literal" && <>
      <label>Constant type<select value={literalType} onChange={event => onChange({ kind: "literal", value: event.target.value === "null" ? null : event.target.value === "boolean" ? false : event.target.value === "number" ? 0 : "" })}><option value="string">Text</option><option value="number">Number</option><option value="boolean">Boolean</option><option value="null">Missing / null</option></select></label>
      {typeof value.value === "string" && <label>Text constant<input maxLength={1000} value={value.value} onChange={event => onChange({ ...value, value: event.target.value })} /></label>}
      {typeof value.value === "number" && <label>Numeric constant<input type="number" step="any" value={Number.isFinite(value.value) ? value.value : ""} onChange={event => onChange({ ...value, value: event.target.value === "" ? NaN : Number(event.target.value) })} /></label>}
      {typeof value.value === "boolean" && <label>Boolean constant<select value={String(value.value)} onChange={event => onChange({ ...value, value: event.target.value === "true" })}><option value="true">True</option><option value="false">False</option></select></label>}
    </>}
    {value.kind === "call" && <><OperationControls value={value} onChange={onChange} />{value.arguments.map((argument, index) => <div key={index}><p className="muted">Input {index + 1}</p><ExpressionInput value={argument} onChange={next => onChange({ ...value, arguments: value.arguments.map((old, position) => position === index ? next : old) })} columns={columns} references={references} depth={depth + 1} /></div>)}</>}
  </fieldset>;
}

export function DerivedFeaturesEditor({ projectId, state, disabled, initialColumn, initialFeature, onApply, onCancel, onDirtyChange }: {
  projectId: string; state: WorkingPipeline; disabled: boolean; initialColumn?: string; initialFeature?: string;
  onApply: (ir: PipelineIR) => void; onCancel: () => void; onDirtyChange: (dirty: boolean) => void;
}) {
  const definitions = state.ir.derived?.features ?? [];
  const edited = definitions.find(feature => feature.name === initialFeature);
  const temporalNames = state.ir.temporal?.features.map(feature => feature.name) ?? [];
  const derivedNames = definitions.map(feature => feature.name);
  const columns = state.columns.filter(column => column.name !== state.ir.target?.column && !derivedNames.includes(column.name) && !temporalNames.includes(column.name)).map(column => column.name);
  const initialInput: DerivedExpression = initialColumn && temporalNames.concat(derivedNames).includes(initialColumn) ? { kind: "reference", name: initialColumn } : { kind: "column", name: initialColumn && columns.includes(initialColumn) ? initialColumn : "" };
  const initialExpression = edited?.expression ?? derivedCall("add", [initialInput, emptyInput()]);
  const [name, setName] = useState(edited?.name ?? "");
  const [expression, setExpression] = useState<DerivedExpression>(initialExpression);
  const [mode, setMode] = useState<"guided" | "expression">(canGuideDerived(initialExpression) ? "guided" : "expression");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [pendingSignature, setPendingSignature] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ signature: string; data: TemporalPreview } | null>(null);
  const request = useRef<AbortController | null>(null);
  const requestId = useRef(0);
  const references = [...temporalNames, ...derivedNames].filter(reference => reference !== name && reference !== edited?.name && reference !== state.ir.target?.column);
  let candidate: PipelineIR | null = null, previewCandidate: PipelineIR | null = null, validation = "";
  try { candidate = derivedRecipe(state.ir, name, expression, columns, edited?.name); previewCandidate = derivedPreviewRecipe(candidate, name); }
  catch (err) { validation = err instanceof Error ? err.message : "Review the expression."; }
  const signature = JSON.stringify([projectId, state.revision, candidate, name, expression]);
  const busy = pendingSignature === signature;
  const current = preview?.signature === signature ? preview.data : null;
  const changed = name !== (edited?.name ?? "") || JSON.stringify(expression) !== JSON.stringify(initialExpression);
  const dependents = edited && name !== edited.name ? definitions.filter(feature => derivedReferences(feature.expression).includes(edited.name)).map(feature => feature.name) : [];
  const matched = !!current && current.revision === state.revision && !current.errors.length && current.columns.some(column => column.name === name);

  useEffect(() => { onDirtyChange(changed); }, [changed, onDirtyChange]);
  useEffect(() => () => { request.current?.abort(); requestId.current++; onDirtyChange(false); }, [onDirtyChange]);
  useEffect(() => () => { request.current?.abort(); requestId.current++; }, [signature]);
  function invalidate() { request.current?.abort(); requestId.current++; setPreview(null); setError(""); setNotice(""); setPendingSignature(null); }
  function updateExpression(next: DerivedExpression) { invalidate(); setExpression(next); }
  function cancel() { invalidate(); onDirtyChange(false); onCancel(); }
  async function loadPreview() {
    if (!previewCandidate) { setError(validation); return; }
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    const id = ++requestId.current;
    setPendingSignature(signature); setError(""); setPreview(null);
    try {
      const data = await api.temporalPreview(projectId, state.revision, previewCandidate, controller.signal);
      if (!controller.signal.aborted && requestId.current === id) setPreview({ signature, data });
    } catch (err) {
      if (!controller.signal.aborted && requestId.current === id) setError(err instanceof Error ? err.message : "Derived feature preview unavailable.");
    } finally { if (requestId.current === id) setPendingSignature(null); }
  }

  return <Panel title={edited ? `Edit derived feature: ${edited.name}` : "Create Derived Feature"} description="Compose row-wise features from columns, constants and derived references. Preview uses the same runtime as training and inference.">
    <fieldset disabled={disabled}>
      <label>Output feature name<input maxLength={200} value={name} placeholder="profit_margin" onChange={event => { invalidate(); setName(event.target.value); }} /></label>
      <div className="actions"><Button aria-pressed={mode === "guided"} onClick={() => { if (!canGuideDerived(expression)) { setNotice("This nested expression needs Expression Mode. It has been retained without changes."); return; } setNotice(""); setMode("guided"); }}>Guided Mode</Button><Button aria-pressed={mode === "expression"} onClick={() => { setNotice(""); setMode("expression"); }}>Expression Mode</Button></div>
      {notice && <p role="status">{notice}</p>}
      {mode === "guided" && expression.kind === "call" ? <><OperationControls value={expression} onChange={updateExpression} />{expression.arguments.map((argument, index) => <div key={index}><p>Input {index + 1}</p><ExpressionInput value={argument} onChange={next => updateExpression({ ...expression, arguments: expression.arguments.map((old, position) => position === index ? next : old) })} columns={columns} references={references} depth={2} leafOnly /></div>)}</> : <ExpressionInput value={expression} onChange={updateExpression} columns={columns} references={references} />}
      <p className="muted">Source columns and derived references are separate inputs. The target is excluded. Temporal numeric and binary outputs can be used as derived references. Missing outputs may need downstream imputation.</p>
      <p className="muted">Preview evaluates this feature and its dependencies, including the temporal stage. Apply retains all other feature definitions. Any other invalid definitions keep the pipeline blocked until repaired.</p>
      {!!dependents.length && <Alert>Renaming leaves dependent features unchanged: {dependents.join(", ")}. Their references to {edited!.name} will be invalid until repaired.</Alert>}
      {validation && <p role="status">{validation}</p>}
      <div className="actions"><Button disabled={busy || !previewCandidate} onClick={() => void loadPreview()}>{busy ? "Calculating preview..." : "Preview derived feature"}</Button><Button disabled={busy || !candidate || !matched} onClick={() => { if (candidate && matched) { onDirtyChange(false); onApply(candidate); } }}>Apply derived feature</Button></div>
    </fieldset>
    <Button onClick={cancel}>Cancel</Button>
    {error && <Alert>{error}</Alert>}
    {current && <>
      {current.errors.map((message, index) => <Alert key={index}>{message}</Alert>)}
      {current.warnings.map((message, index) => <p className="muted" key={index}>{message}</p>)}
      {current.revision !== state.revision && <Alert>The project revision changed. Reload the preparation workspace before applying.</Alert>}
      <p>Preview: up to {current.limit} source rows. Counts cover the source, not a test split.</p>
      <div className="table-scroll" role="region" tabIndex={0} aria-label="Derived feature preview"><table><thead><tr><th>Feature</th><th>Output type</th><th>Missing</th><th>Invalid</th><th>Sample values</th></tr></thead><tbody>{current.columns.filter(column => column.name === name).map(column => <tr key={column.name}><th scope="row">{column.name}</th><td>{column.semantic_type}{column.physical_dtype ? ` (${column.physical_dtype})` : ""}</td><td>{column.missing_count}</td><td>{column.invalid_count ?? 0}</td><td>{column.values.map(value => value === null ? "Missing" : String(value)).join(", ")}</td></tr>)}</tbody></table></div>
      {current.columns.some(column => column.name === name && column.missing_count > 0) && <p className="muted">This feature contains missing values. Configure compatible downstream imputation before training.</p>}
      {current.columns.some(column => column.name === name && (column.invalid_count ?? 0) > 0) && <Alert>Invalid or out-of-domain inputs produced missing results. Review the inputs and downstream handling.</Alert>}
    </>}
  </Panel>;
}

