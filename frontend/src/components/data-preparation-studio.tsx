"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, type Column, type Dataset, type Project } from "@/lib/api/projects";
import type { ColumnProfile } from "@/lib/api/profiles";
import type { CleaningStep, FeatureIntent, Operation, PipelineIR, TemporalPreview, WorkingPipeline } from "@/lib/api/pipelines";
import { displayScalar } from "@/lib/api/scalars";
import { appliedSteps, atStep, changeDraft, clearStudioSession, columnActions, draftHistory, preparationErrors, readStudioSession, redoDraft, references, rememberStudioSession, removeStep, undoDraft, type ColumnAction, type DraftHistory, type PrepStep } from "@/lib/preparation";
import { registerTrainGuard } from "@/lib/train-drafts";
import { Alert, Button, Dialog, Loading } from "./ui";
import { DataView } from "./data-view";
import { Explore } from "./explore";
import { useLivePipeline } from "./live-pipeline";
import { OperationSelect } from "./operation-select";
import { PreparationMenu } from "./preparation-menu";
import { PreparationProfile } from "./preparation-profile";
import { imputationActive, removeAdvancedImputation } from "@/lib/imputation";
import { AdvancedImputationEditor } from "./advanced-imputation";
import { DerivedFeaturesEditor } from "./derived-features";
import { TemporalFeaturesEditor } from "./temporal-features";

import { EngineeringEditor } from "./feature-engineering-editor";
import { engineeringFitted, engineeringCategorical } from "@/lib/feature-engineering";
import { CleaningEditor } from "./cleaning-editor";

type StudioColumn = Column & { derived: boolean; available: boolean };
type Editor = { engineeringMethod?: import("@/lib/api/pipelines").EngineeringFeature["method"]; cleaningKind?: CleaningStep["kind"]; cleaningId?: string; keepMissing?: boolean; kind: "engineering" | "cleaning" | "source" | "diagnostics" | "add" | "profile" | "operation" | "temporal" | "derived" | "advanced" | "participation" | "target"; column?: string; action?: ColumnAction["id"]; family?: Operation["type"]; feature?: string };

function OperationEditor({ column, feature, family, onApply, onCancel, onDirtyChange, advanced = false }: { advanced?: boolean; column: Column; feature: FeatureIntent; family: Operation["type"]; onApply: (feature: FeatureIntent) => void; onCancel: () => void; onDirtyChange: (dirty: boolean) => void }) {
  const [draft, setDraft] = useState(feature);
  const changed = JSON.stringify(draft) !== JSON.stringify(feature);
  useEffect(() => { onDirtyChange(changed); return () => onDirtyChange(false); }, [changed, onDirtyChange]);
  return <div className="studio-editor"><p>Configure {family} for <strong>{column.name}</strong>. Apply updates the studio draft; Save persists it.</p>
    {advanced && family === "impute" && <Alert tone="info">Applying this quick setting replaces Advanced Imputation and removes its indicator for this column. It does not run both imputers.</Alert>}
    <details><summary>Stored operation sequence</summary><pre>{JSON.stringify(feature.operations, null, 2)}</pre><p>Reconfiguring a family replaces its duplicate instances. Unsupported legacy sequences can be cleared explicitly.</p></details>
    <label>{family === "impute" ? "Missing-value strategy" : family === "scale" ? "Numeric scaling" : "Categorical encoding"}<OperationSelect name={column.name} feature={draft} family={family} numeric={column.effective_semantic_type === "continuous"} onChange={setDraft} /></label>
    <p className="muted">Learned transformations fit training rows only. No full-source fitted preview is calculated.</p><div className="actions"><Button onClick={() => setDraft({ ...draft, operations: [] })}>Clear stored operations</Button><Button variant="primary" onClick={() => onApply(draft)}>Apply</Button><Button onClick={onCancel}>Cancel</Button></div></div>;
}

function ParticipationEditor({ features, column, invalidNames, onApply, onCancel, onDirtyChange }: { features: PipelineIR["features"]; column?: string; invalidNames: string[]; onApply: (features: PipelineIR["features"]) => void; onCancel: () => void; onDirtyChange: (dirty: boolean) => void }) {
  const [draft, setDraft] = useState(column && !features[column] ? { ...features, [column]: { included: false, operations: [] } } : features);
  const [query, setQuery] = useState("");
  const changed = JSON.stringify(draft) !== JSON.stringify(features);
  useEffect(() => { onDirtyChange(changed); return () => onDirtyChange(false); }, [changed, onDirtyChange]);
  const names = Object.keys(draft).filter(name => (!column || name === column) && name.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  return <div className="studio-editor"><p>Exclude from estimator input without deleting source values. Raw datetime needs derived features; unsupported raw types still block training. Missing recipe entries start excluded until explicitly selected.</p><label>Find feature<input type="search" value={query} onChange={event => setQuery(event.target.value)} /></label><div className="studio-participation">{names.slice(0, 100).map(name => <div key={name}><label className="check-label"><input type="checkbox" checked={draft[name].included} onChange={event => setDraft({ ...draft, [name]: { ...draft[name], included: event.target.checked } })} />{name}</label>{invalidNames.includes(name) && <Button onClick={() => { const next = { ...draft }; delete next[name]; setDraft(next); }}>Remove invalid recipe entry: {name}</Button>}</div>)}</div>{names.length > 100 && <p>Showing 100 matches; search to narrow the list.</p>}<div className="actions"><Button variant="primary" onClick={() => onApply(draft)}>Apply feature participation</Button><Button onClick={onCancel}>Cancel</Button></div></div>;
}

export function DataPreparationStudio({ project, dataset, onDatasetSaved, onReload, initialDiagnostics = false, readOnly = false }: {
  project: Project; dataset: Dataset | null; onDatasetSaved: (dataset: Dataset) => void; onReload: () => void; initialDiagnostics?: boolean; readOnly?: boolean;
}) {
  const router = useRouter();
  const publish = useLivePipeline()?.publish;
  const [snapshot, setSnapshot] = useState<WorkingPipeline | null>(null);
  const [history, setHistory] = useState<DraftHistory | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState("");
  const [previewStep, setPreviewStep] = useState("latest");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [collapsed, setCollapsed] = useState(false);
  const [sourceOnly, setSourceOnly] = useState(false);
  const [originalSource, setOriginalSource] = useState(false);
  const [editor, setEditor] = useState<Editor | null>(initialDiagnostics ? { kind: "diagnostics" } : null);
  const [editorDirty, setEditorDirty] = useState(false);
  const [actionSearch, setActionSearch] = useState("");
  const [menu, setMenu] = useState<{ column: string; x: number; y: number } | null>(null);
  const menuFocus = useRef<HTMLElement | null>(null);
  const leaving = useRef(false);
  const [confirmation, setConfirmation] = useState<{ kind: "remove" | "revert" | "reset" | "discard"; step?: PrepStep } | null>(null);
  const [preview, setPreview] = useState<{ key: string; value?: TemporalPreview; error?: string } | null>(null);
  const previews = useRef(new Map<string, TemporalPreview>());
  const [profiles] = useState(() => new Map<string, ColumnProfile>());
  const current = useRef<{ snapshot: WorkingPipeline | null; history: DraftHistory | null }>({ snapshot: null, history: null });
  const ir = history?.present ?? snapshot?.ir;
  const signature = JSON.stringify(ir ?? null);
  const dirty = Boolean(snapshot && ir && signature !== JSON.stringify(snapshot.ir));
  const revision = snapshot?.revision ?? 0;
  const steps = ir && dataset ? appliedSteps(ir, dataset.columns) : [];
  const chosenStep = steps.find(step => step.id === previewStep);
  let displayed = ir, stageError = "";
  if (ir && dataset && previewStep !== "latest") {
    try { displayed = atStep(ir, dataset.columns, previewStep); }
    catch (err) { stageError = err instanceof Error ? err.message : "Stage unavailable."; }
  }
  const chosenIndex = steps.findIndex(step => step.id === previewStep);
  const fittedStage = chosenIndex >= 0 && steps.slice(0, chosenIndex + 1).some(step => step.kind === "operation" || step.kind === "engineering" && ir?.feature_engineering?.features.some(f => f.name === step.column && engineeringFitted(f)) || step.kind === "advanced" && (ir && imputationActive(ir, step.column!)));
  const previewSignature = JSON.stringify(displayed ?? null);
  const previewKey = JSON.stringify([project.id, snapshot?.revision, previewSignature]);
  const needsPreview = Boolean(dataset && (displayed?.cleaning || displayed?.temporal || displayed?.derived || displayed?.imputation || displayed?.feature_engineering) && !fittedStage && !stageError && !snapshot?.stale);
  const currentPreview = preview?.key === previewKey ? preview : null;
  const previewPending = needsPreview && !currentPreview;
  const profileDataset = dataset && snapshot ? { ...dataset, revision: snapshot.revision } : dataset;

  useEffect(() => { current.current = { snapshot, history }; }, [snapshot, history]);
  useEffect(() => {
    if (!dataset) return;
    const controller = new AbortController();
    async function load() {
      try {
        const next = await api.pipeline(project.id, controller.signal);
        if (controller.signal.aborted) return;
        const previous = current.current;
        const pending = previous.snapshot && previous.history && JSON.stringify(previous.snapshot.ir) !== JSON.stringify(previous.history.present);
        if (pending) {
          if (JSON.stringify(next.ir) !== JSON.stringify(previous.snapshot!.ir) || JSON.stringify(next.columns) !== JSON.stringify(previous.snapshot!.columns)) { setConflict(true); setError("Saved preparation changed. Your draft is retained. Discard and reload to review the new state."); return; }
          setSnapshot(next); return;
        }
        const recovered = readStudioSession(project.id, dataset!.id);
        if (recovered) {
          setSnapshot(next); setHistory(recovered.history);
          if (recovered.base !== JSON.stringify(next.ir) || recovered.columns !== JSON.stringify(next.columns)) { setConflict(true); setError("A session draft from an older saved context is retained. Discard and reload before applying it to changed data."); }
          else { setConflict(false); setError(""); setNotice("Restored unsaved preparation and undo history from this tab."); }
          return;
        }
        setSnapshot(next); setHistory(draftHistory(next.ir)); setConflict(false); setError("");
      } catch (err) { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Preparation unavailable."); }
    }
    void load(); window.addEventListener("mlstudio:visual-refresh", load);
    return () => { controller.abort(); window.removeEventListener("mlstudio:visual-refresh", load); };
  }, [project.id, dataset?.id, dataset?.revision, dataset]);
  useEffect(() => {
    if (!dataset || !snapshot || !history || conflict) return;
    if (dirty) rememberStudioSession(project.id, dataset.id, { revision: snapshot.revision, base: JSON.stringify(snapshot.ir), columns: JSON.stringify(snapshot.columns), history });
    else clearStudioSession(project.id, dataset.id);
  }, [project.id, dataset, snapshot, history, dirty, conflict]);
  useEffect(() => {
    if (readOnly) return;
    publish?.(signature === "null" ? null : dirty ? { revision, ir: JSON.parse(signature) as PipelineIR } : undefined);
    return () => publish?.(undefined);
  }, [signature, dirty, revision, publish, readOnly]);
  useEffect(() => {
    if (readOnly) return;
    const leave = () => leaving.current || !busy && (!(dirty || editorDirty) || window.confirm("Leave Data Preparation with unsaved changes? Applied draft edits are retained in this tab; unapplied form input may be lost. Save for durable persistence."));
    const unregister = registerTrainGuard(leave);
    const unload = (event: BeforeUnloadEvent) => { if (dirty || busy || editorDirty) { event.preventDefault(); event.returnValue = ""; } };
    const navigate = (event: MouseEvent) => {
      const anchor = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!anchor || event.defaultPrevented || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("#") || new URL(href, window.location.href).href === window.location.href) return;
      if (!leave()) { event.preventDefault(); event.stopImmediatePropagation(); }
    };
    const traverse = (event: Event) => { if ((event as Event & { navigationType?: string }).navigationType === "traverse" && event.cancelable && !leave()) event.preventDefault(); };
    const navigation = (window as Window & { navigation?: EventTarget }).navigation;
    window.addEventListener("beforeunload", unload); document.addEventListener("click", navigate, true);
    navigation?.addEventListener("navigate", traverse);
    return () => { unregister(); window.removeEventListener("beforeunload", unload); document.removeEventListener("click", navigate, true); navigation?.removeEventListener("navigate", traverse); };
  }, [dirty, busy, editorDirty, readOnly]);
  useEffect(() => {
    if (!needsPreview || !snapshot) return;
    const found = previews.current.get(previewKey);
    const controller = new AbortController();
    const request = found ? Promise.resolve(found) : api.temporalPreview(project.id, snapshot.revision, JSON.parse(previewSignature), controller.signal);
    request.then(value => {
      if (controller.signal.aborted) return;
      if (previews.current.size >= 8) previews.current.delete(previews.current.keys().next().value!);
      previews.current.set(previewKey, value); setPreview({ key: previewKey, value });
    }).catch(err => { if (!controller.signal.aborted) setPreview({ key: previewKey, error: err instanceof Error ? err.message : "Preview unavailable." }); });
    return () => controller.abort();
  }, [needsPreview, project.id, snapshot?.revision, snapshot, previewSignature, previewKey]);
  const closeMenu = useCallback(() => { setMenu(null); menuFocus.current?.focus(); }, []);

  if (!dataset) return <DataView project={project} dataset={null} onSaved={onDatasetSaved} onReload={onReload} />;
  if (!snapshot || !ir || !history) return error ? <Alert>{error}<Button onClick={onReload}>Reload workspace</Button></Alert> : <Loading>Loading saved preparation...</Loading>;
  const derivedNames = new Set([...(ir.temporal?.features.map(feature => feature.name) ?? []), ...(ir.derived?.features.map(feature => feature.name) ?? [])]);
  const savedColumns = new Map(snapshot.columns.map(column => [column.name, column]));
  const sourceColumns: StudioColumn[] = dataset.columns.map(column => {
    const fresh = !originalSource ? currentPreview?.value?.cleaning?.columns.find(item => item.name === column.name) : undefined;
    const stored = !originalSource && JSON.stringify(displayed?.cleaning ?? null) === JSON.stringify(snapshot.ir.cleaning ?? null) ? savedColumns.get(column.name) : undefined;
    return { ...column, ...(stored ?? {}), ...(fresh ? { physical_dtype: fresh.physical_dtype, effective_semantic_type: fresh.semantic_type as Column["effective_semantic_type"], missing_count: fresh.missing_count, unique_count: fresh.unique_count } : {}), derived: false, available: originalSource || !displayed?.cleaning || Boolean(fresh) };
  });
  const draftDefinitions = [...(ir.temporal?.features ?? []), ...(ir.derived?.features ?? [])];
  const draftDerivedColumns: StudioColumn[] = draftDefinitions.map((feature, index) => {
    const fresh = currentPreview?.value?.columns.find(column => column.name === feature.name);
    const unchanged = JSON.stringify(snapshot.ir.derived ?? null) === JSON.stringify(ir.derived ?? null) && JSON.stringify([...(snapshot.ir.temporal?.features ?? []), ...(snapshot.ir.derived?.features ?? [])].find(old => old.name === feature.name)) === JSON.stringify(feature) && JSON.stringify(snapshot.ir.temporal?.sources) === JSON.stringify(ir.temporal?.sources);
    const stored = unchanged ? snapshot.columns.find(column => column.name === feature.name) : undefined;
    return { name: feature.name, source_order: dataset.columns.length + index, physical_dtype: fresh?.physical_dtype ?? stored?.physical_dtype ?? "float64", effective_semantic_type: fresh?.semantic_type as Column["effective_semantic_type"] ?? stored?.effective_semantic_type ?? "unknown", inferred_semantic_type: "unknown", semantic_override: null, missing_count: fresh?.missing_count ?? stored?.missing_count ?? 0, unique_count: stored?.unique_count ?? 0, role: "feature", inference_version: ir.derived?.features.some(item => item.name === feature.name) ? "derived-v1" : "temporal-v1", derived: true, available: Boolean(fresh || stored) };
  });
  const indicators = Object.entries(ir.imputation?.columns ?? {}).filter(([name, config]) => config.indicator && imputationActive(ir, name));
  const indicatorNames = new Set(indicators.map(([, config]) => config.indicator!));
  indicatorNames.forEach(name => derivedNames.add(name));
  const indicatorColumns: StudioColumn[] = indicators.map(([, config], index) => {
    const fresh = currentPreview?.value?.columns.find(column => column.name === config.indicator);
    return { name: config.indicator!, source_order: dataset.columns.length + draftDerivedColumns.length + index, physical_dtype: "float64", effective_semantic_type: "binary", inferred_semantic_type: "binary", semantic_override: null, missing_count: 0, unique_count: 2, role: "feature", inference_version: "imputation-v1", derived: true, available: Boolean(fresh) };
  });
  const engineeringNames = new Set(ir.feature_engineering?.features.map(f => f.name));
  engineeringNames.forEach(name => derivedNames.add(name));
  const engineeringColumns: StudioColumn[] = (ir.feature_engineering?.features ?? []).map((feature, index) => {
    const fresh = currentPreview?.value?.columns.find(c => c.name === feature.name);
    return { name: feature.name, source_order: dataset.columns.length + draftDerivedColumns.length + indicatorColumns.length + index, physical_dtype: engineeringCategorical(feature) ? "object" : "float64", effective_semantic_type: engineeringCategorical(feature) ? "categorical" : "continuous", inferred_semantic_type: engineeringCategorical(feature) ? "categorical" : "continuous", semantic_override: null, missing_count: fresh?.missing_count ?? 0, unique_count: 0, role: ir.features[feature.name]?.included ? "feature" : "excluded", inference_version: "feature-engineering-v1", derived: true, available: !!fresh && !engineeringFitted(feature) };
  });
  const derivedColumns = draftDerivedColumns.filter(column => [...(displayed?.temporal?.features ?? []), ...(displayed?.derived?.features ?? [])].some(feature => feature.name === column.name));
  const columns = [...sourceColumns, ...engineeringColumns.filter(c => displayed?.feature_engineering?.features.some(f => f.name === c.name)), ...derivedColumns, ...indicatorColumns.filter(column => Object.entries(displayed?.imputation?.columns ?? {}).some(([name, config]) => displayed && imputationActive(displayed, name) && config.indicator === column.name))];
  const allColumns = [...sourceColumns, ...draftDerivedColumns, ...indicatorColumns, ...engineeringColumns];
  const activeColumn = columns.find(column => column.name === selected) ?? sourceColumns[0];
  const filtered = columns.filter(column => (!(sourceOnly || originalSource) || !column.derived) && column.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const currentOffset = Math.min(offset, Math.max(0, Math.floor((filtered.length - 1) / 30) * 30));
  const page = filtered.slice(currentOffset, currentOffset + 30);
  const locked = busy || conflict || snapshot.stale || readOnly;
  const cleaned = !originalSource && displayed?.cleaning ? currentPreview?.value?.cleaning : undefined;
  const rowCount = Math.min(20, !originalSource && displayed?.cleaning ? cleaned?.rows.length ?? 0 : dataset.preview.length, dataset.preview_limit);
  const savedErrors = preparationErrors(snapshot.issues);
  const draftState = { ...snapshot, ir, columns: allColumns };
  const actionsFor = (column: StudioColumn) => columnActions(column, column.name === ir.target?.column || indicatorNames.has(column.name), ir.features[column.name]?.included ?? false, !column.derived).filter(action => !engineeringNames.has(column.name) || ["profile", "impute", "scale", "encode", "participation"].includes(action.id));
  const menuColumn = allColumns.find(column => column.name === menu?.column);
  const editorColumn = allColumns.find(column => column.name === editor?.column) ?? (editor?.kind === "advanced" ? undefined : activeColumn);
  const editorFeature = editorColumn ? ir.features[editorColumn.name] ?? { included: false, operations: [] } : undefined;
  const knownColumns = new Set(allColumns.map(column => column.name));
  const invalidNames = Object.keys(ir.features).filter(name => !knownColumns.has(name) || name === ir.target?.column);

  function apply(next: PipelineIR) { setHistory(current => current ? changeDraft(current, next) : draftHistory(next)); setPreviewStep("latest"); setNotice(""); setError(""); }
  function openEditor(next: Editor) { setEditorDirty(false); setEditor(next); }
  function closeEditor() { if (editorDirty && !window.confirm("Discard unapplied editor changes?")) return; setEditorDirty(false); setEditor(null); }
  function runAction(column: StudioColumn, action: ColumnAction) {
    closeMenu(); setSelected(column.name);
    if (action.id.startsWith("engineering-")) { openEditor({ kind: "engineering", column: column.name, engineeringMethod: action.id === "engineering-bin" ? "boundaries" : action.id === "engineering-rare" ? "rare" : action.id === "engineering-ordinal" ? "ordinal" : "log1p" }); return; }
    if (action.id.startsWith("cleaning-")) {
      const kind = action.id === "cleaning-keep-missing" ? "missing_filter" : action.id === "cleaning-replace-missing" ? "replace" : action.id.slice(9) as CleaningStep["kind"];
      openEditor({ kind: "cleaning", column: column.name, cleaningKind: kind, keepMissing: action.id === "cleaning-keep-missing" }); return;
    }
    openEditor(action.id === "advanced-imputation" ? { kind: "advanced", column: column.name } : action.id === "derived-create" ? { kind: "derived", column: column.name } : action.id === "profile" ? { kind: "profile", column: column.name } : action.id === "participation" ? { kind: "participation", column: column.name } : action.id.startsWith("temporal-") ? { kind: "temporal", column: column.name, action: action.id } : { kind: "operation", column: column.name, family: action.id as Operation["type"] });
  }
  function openStep(step: PrepStep) {
    if (step.kind === "engineering") openEditor({ kind: "engineering", feature: step.column });
    else if (step.kind === "cleaning" || step.kind === "selection") openEditor({ kind: "cleaning", cleaningId: step.cleaningId, column: step.column });
    else if (step.kind === "advanced") openEditor({ kind: "advanced", column: step.column });
    else if (step.kind === "derived" || step.id === "derived-invalid") openEditor({ kind: "derived", feature: step.kind === "derived" ? step.column : ir!.derived?.features[0]?.name });
    else if (step.kind === "operation") openEditor({ kind: "operation", column: step.column, family: ir!.features[step.column!].operations[step.index!].type });
    else if (step.id.startsWith("legacy-operations:")) openEditor({ kind: "operation", column: step.column, family: ir!.features[step.column!].operations[0].type });
    else if (step.kind === "participation" || step.kind === "dormant" || step.id === "legacy-features") openEditor({ kind: "participation" });
    else openEditor({ kind: "temporal", column: step.kind === "parse" ? step.column : ir!.temporal?.features.find(feature => feature.name === step.column) ? references(ir!.temporal!.features.find(feature => feature.name === step.column)!.expression, "column")[0] : undefined, feature: step.kind === "temporal" ? step.column : undefined, action: step.kind === "parse" ? "temporal-extract" : "temporal-expression" });
  }
  function openMenu(column: StudioColumn, x: number, y: number, trigger: HTMLElement) {
    setSelected(column.name); menuFocus.current = trigger;
    setMenu({ column: column.name, x: Math.max(8, Math.min(x, window.innerWidth - 310)), y: Math.max(8, Math.min(y, window.innerHeight - Math.min(actionsFor(column).length * 38 + 48, window.innerHeight - 16))) });
  }
  async function save(continueToTrain = false) {
    if (locked || editorDirty) return;
    setBusy(true); setError("");
    try {
      const next = dirty ? await api.savePipeline(project.id, snapshot!.revision, ir!) : await api.pipeline(project.id);
      clearStudioSession(project.id, dataset!.id);
      setSnapshot(next); setHistory(draftHistory(next.ir)); setNotice("Preparation saved."); publish?.(undefined);
      if (continueToTrain) {
        const errors = preparationErrors(next.issues);
        if (next.stale || errors.length) { setError(errors.join(" ") || "Reset stale preparation for this Dataset first."); return; }
        router.push(`/projects/${project.id}?view=train`);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Could not save preparation."); if (err instanceof ApiError && err.status === 409) setConflict(true); }
    finally { setBusy(false); }
  }
  async function confirmChange() {
    if (!confirmation) return;
    try {
      if (confirmation.kind === "reset") {
        setBusy(true); const next = await api.resetPipeline(project.id, snapshot!.revision, dataset!.id); setSnapshot(next); setHistory(draftHistory(next.ir)); setConflict(false); setNotice("Preparation reset and saved.");
      } else if (confirmation.kind === "discard") { setHistory(draftHistory(snapshot!.ir)); setPreviewStep("latest"); setNotice("Session draft discarded."); }
      else apply(confirmation.kind === "remove" ? removeStep(ir!, confirmation.step!) : atStep(ir!, dataset!.columns, confirmation.step!.id));
      setConfirmation(null);
      if (confirmation.kind === "discard" || confirmation.kind === "reset") clearStudioSession(project.id, dataset!.id);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not update the draft."); }
    finally { setBusy(false); }
  }
  const later = confirmation?.step ? steps.slice(steps.findIndex(step => step.id === confirmation.step!.id) + 1) : [];
  const dependents = confirmation?.step?.column ? [...(ir.temporal?.features ?? []), ...(ir.derived?.features ?? [])].filter(feature => references(feature.expression, confirmation.step!.kind === "parse" ? "column" : "reference").includes(confirmation.step!.column!)).map(feature => feature.name) : [];

  return <div className="preparation-studio">
    <header className="studio-heading"><div><div className="eyebrow">Data Preparation</div><h2>{dataset.original_filename}</h2><p>{dataset.row_count.toLocaleString()} rows <span aria-hidden="true">·</span> {dataset.column_count} source columns <span aria-hidden="true">·</span> {(ir.temporal?.features.length ?? 0) + (ir.derived?.features.length ?? 0)} derived</p></div><div className="actions"><span role="status" className={`badge ${dirty ? "accent" : "subtle"}`}>{busy ? "Saving..." : dirty ? "Unsaved draft" : "Saved"}</span><Button disabled={locked || editorDirty} onClick={() => void save()}>Save preparation</Button><Button variant="primary" disabled={locked || editorDirty} onClick={() => void save(true)}>Continue to Train →</Button></div></header>
    {readOnly && <Alert tone="info">Code Mode is active. Source inspection is available; visual preparation is suspended.</Alert>}
    {error && <Alert>{error}{conflict && <Button onClick={() => { if (window.confirm("Discard this session draft and reload saved preparation?")) { leaving.current = true; clearStudioSession(project.id, dataset.id); current.current = { snapshot: null, history: null }; setHistory(draftHistory(snapshot.ir)); onReload(); } }}>Discard and reload</Button>}</Alert>}
    {notice && <p role="status" className="save-status">{notice}</p>}
    {snapshot.stale && <Alert>The recipe belongs to the previous Dataset. Inspect this source, then explicitly reset preparation.<Button disabled={busy || readOnly} onClick={() => setConfirmation({ kind: "reset" })}>Reset for current Dataset</Button></Alert>}
    {!dirty && !!savedErrors.length && <details className="studio-validation"><summary>{savedErrors.length} preparation issues to resolve</summary>{savedErrors.map((message, index) => <p className="prepare-error" key={index}>{message}</p>)}</details>}
    <div className="studio-toolbar"><label className="studio-search">Search columns<input type="search" value={search} onChange={event => { setSearch(event.target.value); setOffset(0); }} /></label><Button disabled={locked} onClick={() => { setActionSearch(""); openEditor({ kind: "add" }); }}>Add Transformation</Button><Button disabled={locked || !history.past.length} onClick={() => { setHistory(undoDraft(history)); setPreviewStep("latest"); }}>Undo</Button><Button disabled={locked || !history.future.length} onClick={() => { setHistory(redoDraft(history)); setPreviewStep("latest"); }}>Redo</Button><Button disabled={!dirty || busy || readOnly} onClick={() => setConfirmation({ kind: "discard" })}>Discard draft</Button><details className="studio-view-options"><summary>View options</summary><div className="studio-view-menu"><label className="check-label"><input type="checkbox" checked={sourceOnly} onChange={event => setSourceOnly(event.target.checked)} />Source columns only</label><label className="check-label"><input type="checkbox" checked={originalSource} onChange={event => setOriginalSource(event.target.checked)} />Original source preview</label><Button disabled={busy || readOnly || conflict} onClick={() => setConfirmation({ kind: "reset" })}>Reset preparation</Button></div></details><Button aria-expanded={!collapsed} onClick={() => setCollapsed(!collapsed)}>{collapsed ? "Show Applied Steps" : "Collapse Applied Steps"}</Button><Button disabled={dirty || busy} onClick={() => openEditor({ kind: "source" })}>Source & target</Button><Button onClick={() => openEditor({ kind: "diagnostics" })}>Dataset diagnostics</Button></div>
    <div className={`studio-layout ${collapsed ? "steps-collapsed" : ""}`}>
      <section className="studio-preview" aria-label="Data preview">
        <div className="studio-preview-heading"><strong>{previewStep === "latest" ? "Latest active draft · row-wise preview" : `Selected preview: ${chosenStep?.label ?? "Unavailable step"}`}</strong>{previewStep !== "latest" && <Button onClick={() => setPreviewStep("latest")}>Return to latest draft</Button>}</div>
        <p className="studio-preview-note">The source CSV is immutable. The table shows actual stateless transformed values when cleaning is active. Excluded columns remain visible; exclusion controls estimator input. Imputation, scaling and encoding are learned during training, not fitted to this source preview. Indicator columns show original missingness; imputation target cells still show their pre-imputation values.</p>
        {cleaned && <p>Rows before: {cleaned.source_rows}; retained: {cleaned.retained_rows}; removed: {cleaned.removed_rows}. Counts cover the source dataset.</p>}
        {stageError && <Alert>{stageError}</Alert>}{currentPreview?.error && <Alert>{currentPreview.error}</Alert>}{currentPreview?.value?.errors.map((message, index) => <Alert key={index}>{message}</Alert>)}
        {previewPending && <Loading>Calculating row-wise feature stage with the shared runtime...</Loading>}
        <div className="studio-grid-scroll" role="region" tabIndex={0} aria-label="Scrollable immutable Dataset and derived-feature preview"><table className="studio-grid"><caption className="sr-only">Bounded source rows and stateless derived features. Training-fitted values are not shown.</caption><thead><tr><th scope="col" className="studio-row-index">Row</th>{page.map(column => <th key={column.name} scope="col" className={selected === column.name ? "is-selected" : ""} onContextMenu={event => { event.preventDefault(); openMenu(column, event.clientX, event.clientY, event.currentTarget.querySelector<HTMLButtonElement>("button")!); }}><div className="studio-column-heading"><button type="button" className="studio-column-name" title={column.name} aria-pressed={selected === column.name} onClick={() => setSelected(column.name)}><span className="studio-type" aria-hidden="true">{({ continuous: "123", categorical: "ABC", binary: "01", datetime: "UTC", identifier: "#", text: "abc", unknown: "?" } as Record<string, string>)[column.effective_semantic_type]}</span><span>{column.name}</span></button><button type="button" className="studio-column-menu" aria-label={`Actions for ${column.name}`} aria-haspopup="menu" aria-expanded={menu?.column === column.name} onClick={event => { const rect = event.currentTarget.getBoundingClientRect(); openMenu(column, rect.left, rect.bottom, event.currentTarget); }}>⋯</button></div><small>{column.effective_semantic_type}{column.derived ? " · Derived" : ""}{column.name === ir.target?.column ? " · Target" : (ir.features[column.name]?.included || indicatorNames.has(column.name)) ? "" : " · Excluded"}</small>{column.available && <small>{column.missing_count} missing</small>}</th>)}</tr></thead><tbody>{fittedStage || stageError ? <tr><td colSpan={page.length + 1} className="studio-unavailable"><strong>Stage values unavailable</strong><p>This stage requires fitted training transformations or has unresolved dependencies. No full-source imputer/scaler/encoder is fitted to fabricate a preview.</p><Button onClick={() => setPreviewStep("latest")}>Show source + derived reference</Button></td></tr> : Array.from({ length: rowCount }, (_, row) => <tr key={row}><th scope="row" className="studio-row-index">{(cleaned?.row_indices[row] ?? row) + 1}</th>{page.map(column => { const value = column.derived ? currentPreview?.value?.columns.find(item => item.name === column.name)?.values[row] : cleaned ? cleaned.rows[row]?.[dataset.columns.findIndex(source => source.name === column.name)] : dataset.preview[row]?.[column.source_order]; const unavailable = (column.derived || !originalSource && Boolean(displayed?.cleaning)) && (value === undefined || previewPending); return <td key={column.name} className={`${selected === column.name ? "is-selected" : ""} ${value === null ? "is-missing" : ""}`} title={unavailable ? "Not previewed" : displayScalar(value ?? null)}>{unavailable ? "Not previewed" : value === null ? <span className="studio-null">null</span> : displayScalar(value ?? null)}</td>; })}</tr>)}</tbody></table>{!page.length && <p className="empty-state">No columns match the current view.</p>}</div>
        <div className="studio-grid-footer"><Button disabled={!currentOffset} onClick={() => setOffset(Math.max(0, currentOffset - 30))}>Previous columns</Button><span>{filtered.length ? currentOffset + 1 : 0}–{Math.min(currentOffset + 30, filtered.length)} of {filtered.length} columns</span><Button disabled={currentOffset + 30 >= filtered.length} onClick={() => setOffset(currentOffset + 30)}>Next columns</Button></div>
      </section>
      <aside className="studio-steps" aria-label="Applied Steps" hidden={collapsed}><header><h2>Applied Steps</h2><small>Reconstructed from {dirty ? "draft" : "saved"} Pipeline IR. Fixed stages; no arbitrary reordering.</small></header><ol>{steps.map((step, index) => <li key={step.id} className={previewStep === step.id ? "is-selected" : ""}><button type="button" className="studio-step-select" aria-pressed={previewStep === step.id} onClick={() => setPreviewStep(step.id)}><span className="studio-step-number">{String(index + 1).padStart(2, "0")}</span><span><strong>{step.label}</strong><small>{step.stage}</small>{!!step.outputs.length && step.kind !== "source" && <small title={step.outputs.join(", ")}>Output: {step.outputs.join(", ")}</small>}</span></button><span className={`studio-step-state ${step.invalid ? "invalid" : ""}`}>{step.invalid ? "Invalid configuration" : dirty ? "Draft · validate on save" : snapshot.issues.some(issue => issue.severity === "blocking" && (issue.column === step.column || (step.kind === "temporal" || step.kind === "derived" || step.kind === "parse" || step.kind === "advanced") && (issue.code.startsWith("temporal") || issue.code.startsWith("derived") || issue.code.startsWith("imputation")))) ? "Review validation" : step.kind === "dormant" ? "Not executed" : "Saved configuration"}</span><div className="studio-step-actions">{step.kind !== "source" && <><Button disabled={locked} onClick={() => openStep(step)}>Edit</Button><Button disabled={locked} onClick={() => setConfirmation({ kind: "remove", step })}>Remove</Button></>}<Button disabled={locked || step.kind === "legacy"} onClick={() => setConfirmation({ kind: "revert", step })}>Revert to this step</Button></div></li>)}</ol></aside>
    </div>
    <footer className="studio-status" role="status"><span>Selected: <strong>{activeColumn?.name ?? "None"}</strong> · {activeColumn?.effective_semantic_type ?? "Unknown"} · Missing: {activeColumn?.available ? activeColumn.missing_count : "Not previewed"}</span><span>{fittedStage ? "Fitted stage preview unavailable" : `Preview: ${rowCount} / ${dataset.row_count} source rows`} · {dirty ? "Unsaved changes" : "Saved"}</span></footer>
    {menu && menuColumn && <PreparationMenu key={menu.column} column={menu.column} actions={actionsFor(menuColumn).filter(action => !locked || action.id === "profile")} position={menu} onAction={action => runAction(menuColumn, action)} onClose={closeMenu} />}
    {editor && <Dialog key={`${editor.kind}:${editor.column}:${editor.family}`} title={editor.kind === "engineering" ? "Advanced feature engineering" : editor.kind === "source" ? "Source & target settings" : editor.kind === "diagnostics" ? "Dataset diagnostics" : editor.kind === "add" ? "Add Transformation" : editor.kind === "profile" ? `Column profile · ${editor.column}` : editor.kind === "advanced" ? "Advanced Imputation" : editor.kind === "derived" ? "Derived Feature Builder" : editor.kind === "temporal" ? "Datetime transformation" : editor.kind === "target" ? "Target orientation" : "Configure preparation"} className="studio-dialog" onClose={closeEditor} busy={busy}>
      {editor.kind === "source" && <><p className="muted">Source interpretation and target changes save immediately through the existing Dataset API. They are separate from transformation draft undo.</p>{ir.ir_version === "0.1" && ir.target && <Button disabled={readOnly} onClick={() => openEditor({ kind: "target" })}>Configure binary positive class</Button>}<DataView project={{ ...project, revision: snapshot.revision }} dataset={profileDataset} onSaved={source => { setEditor(null); onDatasetSaved(source); }} onReload={onReload} /></>}
      {editor.kind === "target" && ir.ir_version === "0.1" && ir.target && <><label>Positive class<select value={snapshot.target_classes.findIndex(value => JSON.stringify(value) === JSON.stringify(ir.target?.positive_class))} onChange={event => { const index = Number(event.target.value); apply({ ...ir, target: { ...ir.target!, positive_class: index < 0 ? null : snapshot.target_classes[index] } }); setEditor(null); }}><option value={-1}>Choose explicitly</option>{snapshot.target_classes.map((value, index) => <option key={index} value={index}>{String(value.value)} ({value.value_type})</option>)}</select></label><p>Selection updates the studio draft. Save before training.</p></>}
      {editor.kind === "diagnostics" && <Explore task={project.ml_objective} projectId={project.id} dataset={profileDataset} onReload={onReload} />}
      {editor.kind === "profile" && editorColumn && profileDataset && <PreparationProfile key={`${editorColumn.name}:${snapshot.revision}`} projectId={project.id} dataset={profileDataset} column={editorColumn} task={project.ml_objective} cache={profiles} derived={derivedNames.has(editorColumn.name)} available={editorColumn.available} onReload={onReload} />}
      {editor.kind === "add" && <><label>Search column or transformation<input autoFocus type="search" value={actionSearch} onChange={event => setActionSearch(event.target.value)} /></label><div className="studio-action-results">{([{ kind: "deduplicate", label: "Remove Duplicate Rows" }, { kind: "filter", label: "Filter Rows" }, { kind: "validate", label: "Data Quality Rules" }] as const).filter(action => action.label.toLocaleLowerCase().includes(actionSearch.toLocaleLowerCase())).map(action => <Button key={action.kind} disabled={locked} onClick={() => openEditor({ kind: "cleaning", cleaningKind: action.kind, column: activeColumn && !indicatorNames.has(activeColumn.name) && activeColumn.name !== ir.target?.column && (!activeColumn.derived || action.kind === "filter") ? activeColumn.name : undefined })}>{action.label}</Button>)}{"Create Derived Feature".toLocaleLowerCase().includes(actionSearch.toLocaleLowerCase()) && <Button disabled={locked} onClick={() => openEditor({ kind: "derived" })}>Create Derived Feature</Button>}{allColumns.flatMap(column => actionsFor(column).filter(action => `${column.name} ${action.label}`.toLocaleLowerCase().includes(actionSearch.toLocaleLowerCase())).map(action => ({ column, action }))).slice(0, 40).map(({ column, action }) => <Button key={`${column.name}:${action.id}`} onClick={() => runAction(column, action)}><strong>{column.name}</strong><span>{action.label}</span></Button>)}</div><p className="muted">Up to 40 matching actions. Search to narrow wide datasets. Only currently supported operations are listed.</p></>}
      {editor.kind === "engineering" && <EngineeringEditor key={`${editor.feature}:${editor.column}`} projectId={project.id} state={draftState} initialSource={editor.column} initialFeature={editor.feature} initialMethod={editor.engineeringMethod} disabled={locked} onDirtyChange={setEditorDirty} onCancel={() => { setEditorDirty(false); setEditor(null); }} onApply={candidate => { apply(candidate); setSourceOnly(false); setEditorDirty(false); setEditor(null); }} />}
      {editor.kind === "cleaning" && <CleaningEditor key={`${editor.cleaningId}:${editor.cleaningKind}:${editor.column}`} projectId={project.id} state={draftState} sourceColumns={sourceColumns} initialKind={editor.cleaningKind} initialColumn={editor.column} initialStep={editor.cleaningId} initialKeepMissing={editor.keepMissing} disabled={locked} onDirtyChange={setEditorDirty} onCancel={() => { setEditorDirty(false); setEditor(null); }} onApply={candidate => { apply(candidate); setOriginalSource(false); setSourceOnly(false); setEditorDirty(false); setEditor(null); }} />}
      {editor.kind === "operation" && editorColumn && editorFeature && editor.family && <OperationEditor key={`${editor.column}:${editor.family}`} column={editorColumn} feature={editorFeature} family={editor.family} advanced={Boolean(ir.imputation?.columns[editorColumn.name])} onApply={feature => { const base = editor.family === "impute" ? removeAdvancedImputation(ir, editorColumn.name) : ir; apply({ ...base, features: { ...base.features, [editorColumn.name]: feature } }); setEditor(null); }} onCancel={closeEditor} onDirtyChange={setEditorDirty} />}
      {editor.kind === "participation" && <ParticipationEditor features={ir.features} column={editor.column} invalidNames={invalidNames} onApply={features => { apply({ ...ir, features }); setEditor(null); }} onCancel={closeEditor} onDirtyChange={setEditorDirty} />}
      {editor.kind === "advanced" && (editorColumn ? <AdvancedImputationEditor key={editorColumn.name} projectId={project.id} state={draftState} column={editorColumn} disabled={locked} onDirtyChange={setEditorDirty} onCancel={() => { setEditorDirty(false); setEditor(null); }} onApply={candidate => { apply(candidate); setSourceOnly(false); setEditorDirty(false); setEditor(null); }} /> : <Alert>The imputation target is absent. Restore its source/derived definition or remove this retained Applied Step.</Alert>)}
      {editor.kind === "derived" && <><div className="studio-action-results"><Button disabled={locked} onClick={() => { if (!editorDirty || window.confirm("Discard unapplied expression changes?")) openEditor({ kind: "derived" }); }}>New derived feature</Button>{ir.derived?.features.map(feature => <Button key={feature.name} disabled={locked} aria-pressed={editor.feature === feature.name} onClick={() => { if (!editorDirty || window.confirm("Discard unapplied expression changes?")) openEditor({ kind: "derived", feature: feature.name }); }}>Edit {feature.name}</Button>)}</div><DerivedFeaturesEditor key={`${editor.column}:${editor.feature}`} projectId={project.id} state={draftState} disabled={locked} initialColumn={editor.column} initialFeature={editor.feature} onDirtyChange={setEditorDirty} onCancel={() => { setEditorDirty(false); setEditor(null); }} onApply={candidate => { apply(candidate); setSourceOnly(false); setEditorDirty(false); setEditor(null); }} /></>}
      {editor.kind === "temporal" && <div className="studio-editor"><TemporalFeaturesEditor key={`${editor.column}:${editor.feature}:${editor.action}`} managed projectId={project.id} state={draftState} disabled={locked} onDirtyChange={setEditorDirty} initialSource={editor.column} initialFeature={editor.feature} initialMode={editor.action === "temporal-expression" ? "expression" : "guided"} initialEncoding={editor.action === "temporal-cycle" ? "cyclical" : "raw"} initialOperation={editor.action === "temporal-age" ? "calendar_age" : editor.action === "temporal-difference" ? "date_diff" : "month"} onSave={async candidate => { apply(candidate); setSourceOnly(false); setEditorDirty(false); setEditor(null); }} /><Button onClick={closeEditor}>Cancel</Button></div>}
    </Dialog>}
    {confirmation && <Dialog title={confirmation.kind === "revert" ? "Revert preparation draft?" : confirmation.kind === "remove" ? "Remove applied step?" : confirmation.kind === "reset" ? "Reset preparation?" : "Discard draft changes?"} busy={busy} onClose={() => setConfirmation(null)}>
      {confirmation.kind === "revert" ? <><p>Keep the source, target, model and split context. Remove these later configuration steps from the draft; Save is required to persist the change.</p><ul>{later.map(step => <li key={step.id}>{step.label}</li>)}</ul>{(confirmation.step?.kind === "source" || later.some(step => step.kind === "participation")) && <p>All original non-target feature candidates will be included with no preprocessing. Review identifiers and unsupported types before training.</p>}</> : confirmation.kind === "remove" ? <><p>Remove {confirmation.step?.label}. Unrelated configuration stays intact.</p>{confirmation.step?.kind === "participation" && <p>Removing this selection restores non-target candidates as included. Review unsupported raw types before training.</p>}{!!dependents.length && <Alert tone="info">Dependent features are retained and must be repaired: {dependents.join(", ")}. They are not automatically deleted.</Alert>}</> : confirmation.kind === "reset" ? <p>This saves a reset for the current Dataset and clears preparation, temporal/generalized features, advanced imputation, model and split. The managed source and historical Runs remain unchanged.</p> : <p>Discard all unsaved transformation edits and session undo/redo history. Saved preparation remains intact.</p>}
      <div className="actions"><Button variant="danger" disabled={busy} onClick={() => void confirmChange()}>{confirmation.kind === "remove" ? "Remove step" : confirmation.kind === "revert" ? "Revert draft" : confirmation.kind === "reset" ? "Reset and save" : "Discard changes"}</Button><Button disabled={busy} onClick={() => setConfirmation(null)}>Cancel</Button></div>
    </Dialog>}
  </div>;
}
