"use client";

import { useEffect, useState } from "react";
import { api, type Dataset, type ProjectTask } from "@/lib/api/projects";
import type { Profile } from "@/lib/api/profiles";
import { ColumnDetail } from "./column-detail";
import { CorrelationDiagnostics } from "./eda-preparation-actions";
import type { OnPrepare } from "@/lib/preparation-handoff";
import { RegressionExplore } from "./regression-explore";
import { displayScalar } from "@/lib/api/scalars";
import { Alert, Button, EmptyState, Loading, Panel } from "./ui";
import { Bars, Heatmap, percentage } from "./explore-charts";

export { ColumnDetail } from "./column-detail";

export function Explore({ projectId, dataset, onReload, onPrepare, task = "binary_classification" }: {
  onPrepare?: OnPrepare; task?: ProjectTask; projectId: string; dataset: Pick<Dataset, "id" | "revision"> | null; onReload: () => void;
}) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState("");
  const [multiplier, setMultiplier] = useState(1.5);
  const [loading, setLoading] = useState(true);
  const [draftQuery, setDraftQuery] = useState("");
  const [filters, setFilters] = useState({ query: "", kind: "all", observation: "all" });
  const id = dataset?.id, revision = dataset?.revision;
  useEffect(() => {
    if (!id || revision === undefined || task === "regression") return;
    const controller = new AbortController();
    api.profile(projectId, { id, revision }, offset, controller.signal, filters, undefined, multiplier).then(value => {
      if (!controller.signal.aborted) { if (value.task !== task) throw new Error("Profile task changed. Reload the workspace."); setProfile(value); setLoading(false); setError(""); }
    }).catch((err: unknown) => {
      if (!controller.signal.aborted) { setError(err instanceof Error ? err.message : "Explore unavailable."); setLoading(false); }
    });
    return () => controller.abort();
  }, [projectId, id, revision, offset, filters, task, multiplier]);
  function filter(change: Partial<typeof filters>) {
    setFilters(current => ({ ...current, ...change })); setOffset(0); setSelected(0); setLoading(true);
  }
  if (task === "regression") return <RegressionExplore projectId={projectId} dataset={dataset} onReload={onReload} onPrepare={onPrepare} />;
  if (!dataset) return <Panel title="Explore"><EmptyState title="Add a source Dataset first">Upload a CSV in Data to inspect distributions and quality observations.</EmptyState></Panel>;
  if (error) return <Panel title="Explore could not load"><Alert>{error}</Alert><Button onClick={onReload}>Reload current Dataset</Button></Panel>;
  if (!profile || profile.dataset_id !== id || profile.revision !== revision) return <Panel title="Explore"><Loading>Profiling source observations…</Loading></Panel>;
  const column = profile.columns[selected], q = profile.quality;
  const qualityFilters = [
    ["Constant", q.constant_count, "constant"], ["Near constant", q.near_constant_count, "near_constant"],
    ["All missing", q.all_missing_count, "all_missing"], ["Identifier", q.identifier_count, "identifier"],
    ["High cardinality", q.high_cardinality_count, "high_cardinality"],
  ] as const;
  return <div className="explore-view visual-explore">
    <div className="section-heading"><div><div className="eyebrow">Full source · {profile.original_filename}</div><h2>Explore your data</h2><p className="muted">Distributions, relationships, and quality evidence. No transformations or row removal.</p></div><span className="badge subtle">Revision {profile.revision}</span></div>
    <nav className="explore-sections" aria-label="Explore sections"><a href="#source-overview">Overview</a><a href="#source-quality">Data quality</a><a href="#source-columns">Columns & distributions</a><a href="#source-relationships">Relationships</a></nav>
    <section id="source-overview" className="eda-overview panel">
      <dl className="eda-overview-facts">
        {[["Rows", profile.row_count.toLocaleString()], ["Columns", profile.column_count], ["Feature candidates", profile.feature_count], ["Complete cells", percentage(100 - profile.missing_percentage)], ["Duplicate rows", `${profile.duplicate_rows.toLocaleString()} · ${percentage(profile.duplicate_percentage)}`]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
      </dl>
      <div className="eda-composition" aria-label="Semantic composition">{Object.entries(profile.semantic_counts).map(([type, count], i) => <span key={type} style={{ flex: count, opacity: .35 + i % 4 * .18 }} title={`${type}: ${count} columns`} />)}</div>
      <div className="eda-tabs">{Object.entries(profile.semantic_counts).map(([type, count]) => <button key={type} onClick={() => { filter({ kind: type, observation: "all", query: "" }); setDraftQuery(""); document.getElementById("source-columns")?.scrollIntoView(); }}>{type} <strong>{count}</strong></button>)}</div>
    </section>
    <div className="eda-summary-grid">
      <Panel title="Target distribution" description={profile.target?.column ?? "Select a target in Data"}>
        {profile.target ? <>
          <Bars label="Class proportions" data={profile.target.classes.map(f => ({ label: displayScalar(f.value, true), count: f.count, percentage: f.percentage }))} percentScale />
          <p className="muted">{profile.target.non_missing_count.toLocaleString()} non-missing targets · {profile.target.missing_count.toLocaleString()} missing. Percentages exclude missing targets.</p>
          {task === "binary_classification" && <p className="positive-class">Positive class: <strong>{profile.target.positive_class ? `${String(profile.target.positive_class.value)} (${profile.target.positive_class.value_type})` : "Not configured in Prepare"}</strong></p>}
        </> : <EmptyState title="No target selected">Other source analysis remains available. Select {task === "multiclass_classification" ? "3–50 classes without missing labels" : "exactly two non-missing classes"} in Data.</EmptyState>}
      </Panel>
      <Panel title="Data quality" description="Factual observations across all source columns.">
        <div id="source-quality" className="quality-indicators">{qualityFilters.map(([label, count, observation]) => <button key={label} aria-pressed={filters.observation === observation} onClick={() => { filter({ observation, kind: "all", query: "" }); setDraftQuery(""); document.getElementById("source-columns")?.scrollIntoView(); }}><strong>{count}</strong><span>{label}</span></button>)}</div>
        <p className="muted">Duplicates: {profile.duplicate_rows} rows ({percentage(profile.duplicate_percentage)}), excluding the first occurrence. Near constant: ≥{q.near_constant_threshold}% dominance among non-missing values, with more than one distinct value.</p>
      </Panel>
    </div>
    <Panel title="Missingness" description={`${profile.missing_cells.toLocaleString()} missing cells (${percentage(profile.missing_percentage)}) across ${q.missing_column_count} columns.`}>
      {q.missing_columns.length ? <Bars label={`Most missing columns · up to ${q.missing_column_limit}, ranked by count`} data={q.missing_columns.map(c => ({ label: c.name, count: c.count, percentage: c.percentage }))} percentScale /> : <p className="muted">No missing values were observed.</p>}
      {q.missing_column_count > q.missing_column_limit && <Button onClick={() => { filter({ observation: "missing", kind: "all", query: "" }); setDraftQuery(""); document.getElementById("source-columns")?.scrollIntoView(); }}>Browse all columns with missing values</Button>}
    </Panel>
    <section id="source-columns" className="panel">
      <div className="section-heading"><div><h2>Columns & distributions</h2><p className="muted">Browse source evidence by effective semantic type. Select a column to inspect its distribution.</p></div></div>
      <form className="eda-filters" onSubmit={event => { event.preventDefault(); filter({ query: draftQuery }); }}>
        <label>Search columns<input type="search" value={draftQuery} maxLength={200} onChange={e => setDraftQuery(e.target.value)} placeholder="Column name" /></label>
        <Button type="submit" disabled={loading}>Search</Button>
        <label>Semantic view<select value={filters.kind} onChange={e => filter({ kind: e.target.value })}>
          {[["all", "All types"], ["numerical", "Numerical distributions"], ["categorical", "Categorical / binary"], ["continuous", "Continuous"], ["binary", "Binary"], ["datetime", "Datetime"], ["identifier", "Identifier"], ["text", "Text"], ["unknown", "Unknown"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label>Observation<select value={filters.observation} onChange={e => filter({ observation: e.target.value })}>{[["all", "All observations"], ["missing", "Has missing values"], ["constant", "Constant"], ["near_constant", "Near constant"], ["all_missing", "All missing"], ["identifier", "Identifier"], ["high_cardinality", "High cardinality"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </form>
      {loading ? <Loading>Updating source view…</Loading> : <>
        <p className="muted">{profile.filtered_column_count} matching columns · {profile.column_offset + (profile.columns.length ? 1 : 0)}–{profile.column_offset + profile.columns.length} shown</p>
        <div className="eda-investigation">
          <div className="eda-column-list" aria-label="Columns">{profile.columns.map((c, index) => <button key={c.name} aria-pressed={selected === index} onClick={() => setSelected(index)}>
            <strong title={c.name}>{c.name}</strong><span>{c.semantic_type} · {c.distinct_count} distinct</span><small>{percentage(c.missing_percentage)} missing{c.semantic_override ? " · Manual override" : ""}{c.constant ? " · Constant" : c.near_constant ? " · Near constant" : ""}</small>
          </button>)}</div>
          {column ? <ColumnDetail key={column.name} column={column} scope={{ projectId, datasetId: profile.dataset_id, revision: profile.revision }} onPrepare={onPrepare} onMultiplier={value => { if (value !== multiplier) { setLoading(true); setMultiplier(value); } }} /> : <EmptyState title="No matching columns">Change the search or filters to inspect other columns.</EmptyState>}
        </div>
        <div className="actions eda-pagination"><Button disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset - 20)); setSelected(0); setLoading(true); }}>Previous columns</Button><Button disabled={offset + profile.column_limit >= profile.filtered_column_count} onClick={() => { setOffset(offset + 20); setSelected(0); setLoading(true); }}>Next columns</Button></div>
        <details><summary>Schema table for this page</summary><div className="table-scroll" tabIndex={0} role="region" aria-label="Scrollable data table"><table><thead><tr>{["Column", "Physical", "Detected", "Override", "Effective", "Role", "Distinct", "Missing %"].map(t => <th key={t}>{t}</th>)}</tr></thead><tbody>{profile.columns.map(c => <tr key={c.name}><th>{c.name}</th><td>{c.physical_dtype}</td><td>{c.inferred_semantic_type}</td><td>{c.semantic_override ?? "None"}</td><td>{c.semantic_type}</td><td>{c.role}</td><td>{c.distinct_count}</td><td>{percentage(c.missing_percentage)}</td></tr>)}</tbody></table></div></details>
      </>}
    </section>
    <section id="source-relationships" className="panel"><h2>Relationships</h2><p className="muted">Pearson correlation · first {profile.correlation.columns.length} of {profile.correlation.eligible_count} continuous numeric feature candidates (maximum {profile.correlation.column_limit}). Target and excluded features are omitted. Each pair uses its non-missing observations.</p><Heatmap correlation={profile.correlation} /><CorrelationDiagnostics correlation={profile.correlation} /></section>
  </div>;
}
