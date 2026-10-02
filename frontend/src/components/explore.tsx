"use client";

import { useEffect, useState } from "react";
import { api, type Dataset } from "@/lib/api/projects";
import type { ColumnProfile, Profile } from "@/lib/api/profiles";
import { displayScalar } from "@/lib/api/scalars";
import { Alert, Button, EmptyState, Loading, Panel } from "./ui";
import { Bars, Boxplot, Heatmap, Histogram, compactNumber, percentage } from "./explore-charts";

function ColumnDetail({ column }: { column: ColumnProfile }) {
  const [plot, setPlot] = useState("histogram");
  const stats = column.numeric;
  return <article className="eda-column-detail">
    <div className="section-heading"><div><div className="eyebrow">Source distribution</div><h3 className="wrap">{column.name}</h3></div><span className="badge accent">{column.semantic_type}</span></div>
    <dl className="eda-facts">
      <div><dt>Observed</dt><dd>{column.non_missing_count.toLocaleString()}</dd></div>
      <div><dt>Missing</dt><dd>{column.missing_count.toLocaleString()} <small>({percentage(column.missing_percentage)})</small></dd></div>
      <div><dt>Distinct</dt><dd>{column.distinct_count.toLocaleString()} <small>({percentage(column.uniqueness_percentage)} unique)</small></dd></div>
    </dl>
    {column.constant && <p className="observation-note">Constant: one distinct non-missing value.</p>}
    {column.near_constant && <p className="observation-note">Near constant: the dominant value occurs {column.dominant_count.toLocaleString()} times ({percentage(column.dominant_percentage)} of non-missing observations; threshold ≥95%).</p>}
    {column.identifier && <p className="observation-note">Identifier is the effective semantic interpretation. Source values and feature participation are unchanged.</p>}
    {column.high_cardinality && <p className="observation-note">High cardinality: ≥20 distinct values and ≥50% uniqueness among non-missing values. This is an observation, not a suitability judgement.</p>}
    {column.unavailable_reason && <p className="muted">{column.unavailable_reason}</p>}
    {stats && <>
      {!stats.unavailable_reason && <>
        <div className="eda-tabs" aria-label="Numerical chart"><Button aria-pressed={plot === "histogram"} onClick={() => setPlot("histogram")}>Histogram</Button><Button aria-pressed={plot === "boxplot"} onClick={() => setPlot("boxplot")}>Boxplot</Button></div>
        {plot === "histogram" ? <Histogram stats={stats} name={column.name} /> : <Boxplot stats={stats} name={column.name} />}
      </>}
      {stats.unavailable_reason && <Alert tone="info">{stats.unavailable_reason}</Alert>}
      <dl className="eda-facts numeric-facts">
        {[["Mean", compactNumber(stats.mean)], ["Sample std. dev.", compactNumber(stats.standard_deviation)], ["Minimum", displayScalar(stats.minimum)], ["Q1", compactNumber(stats.q1)], ["Median", compactNumber(stats.median)], ["Q3", compactNumber(stats.q3)], ["Maximum", displayScalar(stats.maximum)], ["Skewness", compactNumber(stats.skewness)]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
      </dl>
      {stats.skewness_unavailable_reason && <p className="muted">{stats.skewness_unavailable_reason}</p>}
      <div className="observation-note"><strong>IQR outliers: {stats.outlier_count === null ? "Unavailable" : `${stats.outlier_count.toLocaleString()} (${percentage(stats.outlier_percentage ?? 0)})`}</strong><p className="muted">Outside fences [{stats.lower_fence === null ? "unavailable" : String(stats.lower_fence)}, {stats.upper_fence === null ? "unavailable" : String(stats.upper_fence)}]. Percentages use non-missing observations. Values are not removed or labelled errors.</p></div>
      <details><summary>Exact statistics and calculation notes</summary><dl className="eda-facts">
        {[["Mean", stats.mean], ["Sample standard deviation", stats.standard_deviation], ["Q1", stats.q1], ["Median", stats.median], ["Q3", stats.q3], ["Adjusted Fisher-Pearson skewness", stats.skewness]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value === null ? "Unavailable" : String(value)}</dd></div>)}
      </dl><p className="muted">Quartiles use linear interpolation. Fences are Q1 − 1.5 × IQR and Q3 + 1.5 × IQR. Skewness uses adjusted Fisher-Pearson G1 for at least three varying observations; no subjective skew categories are applied.</p></details>
    </>}
    {!!column.frequencies?.length && <>
      <Bars label="Category frequency · % of non-missing observations" data={[
        ...column.frequencies.map(f => ({ label: displayScalar(f.value, true), count: f.count, percentage: f.percentage, note: f.label_truncated ? "Label shortened to 120 characters" : undefined })),
        ...(column.other_count ? [{ label: "Other values combined", count: column.other_count, percentage: 100 * column.other_count / column.non_missing_count, note: "Aggregate of omitted categories; not a source label" }] : []),
      ]} />
      <p className="muted">Top 10 categories. Equal-count ties follow first source occurrence. Missing observations are separate.</p>
    </>}
    <details className="eda-schema"><summary>Column interpretation and facts</summary><dl className="eda-facts">
      <div><dt>Physical dtype</dt><dd>{column.physical_dtype}</dd></div><div><dt>Detected</dt><dd>{column.inferred_semantic_type}</dd></div>
      <div><dt>Override</dt><dd>{column.semantic_override ?? "None"}</dd></div><div><dt>Effective</dt><dd>{column.semantic_type}</dd></div><div><dt>Role</dt><dd>{column.role}</dd></div>
      <div><dt>Dominant frequency</dt><dd>{column.dominant_count} / {column.non_missing_count} ({percentage(column.dominant_percentage)})</dd></div>
    </dl><p className="muted">Change semantic interpretation in Data. Explore does not edit your preparation.</p></details>
  </article>;
}

export function Explore({ projectId, dataset, onReload }: {
  projectId: string; dataset: Pick<Dataset, "id" | "revision"> | null; onReload: () => void;
}) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [draftQuery, setDraftQuery] = useState("");
  const [filters, setFilters] = useState({ query: "", kind: "all", observation: "all" });
  const id = dataset?.id, revision = dataset?.revision;
  useEffect(() => {
    if (!id || revision === undefined) return;
    const controller = new AbortController();
    api.profile(projectId, { id, revision }, offset, controller.signal, filters).then(value => {
      if (!controller.signal.aborted) { setProfile(value); setLoading(false); setError(""); }
    }).catch((err: unknown) => {
      if (!controller.signal.aborted) { setError(err instanceof Error ? err.message : "Explore unavailable."); setLoading(false); }
    });
    return () => controller.abort();
  }, [projectId, id, revision, offset, filters]);
  function filter(change: Partial<typeof filters>) {
    setFilters(current => ({ ...current, ...change })); setOffset(0); setSelected(0); setLoading(true);
  }
  if (!dataset) return <Panel title="Explore"><EmptyState title="Add a source Dataset first">Upload a CSV in Data to inspect distributions and quality observations.</EmptyState></Panel>;
  if (error) return <Panel title="Explore could not load"><Alert>{error}</Alert><Button onClick={onReload}>Reload current Dataset</Button></Panel>;
  if (!profile) return <Panel title="Explore"><Loading>Profiling source observations…</Loading></Panel>;
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
          <p className="positive-class">Positive class: <strong>{profile.target.positive_class ? `${String(profile.target.positive_class.value)} (${profile.target.positive_class.value_type})` : "Not configured in Prepare"}</strong></p>
        </> : <EmptyState title="No target selected">Other source analysis remains available. Select exactly two non-missing classes in Data.</EmptyState>}
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
          {column ? <ColumnDetail key={column.name} column={column} /> : <EmptyState title="No matching columns">Change the search or filters to inspect other columns.</EmptyState>}
        </div>
        <div className="actions eda-pagination"><Button disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset - 20)); setSelected(0); setLoading(true); }}>Previous columns</Button><Button disabled={offset + profile.column_limit >= profile.filtered_column_count} onClick={() => { setOffset(offset + 20); setSelected(0); setLoading(true); }}>Next columns</Button></div>
        <details><summary>Schema table for this page</summary><div className="table-scroll"><table><thead><tr>{["Column", "Physical", "Detected", "Override", "Effective", "Role", "Distinct", "Missing %"].map(t => <th key={t}>{t}</th>)}</tr></thead><tbody>{profile.columns.map(c => <tr key={c.name}><th>{c.name}</th><td>{c.physical_dtype}</td><td>{c.inferred_semantic_type}</td><td>{c.semantic_override ?? "None"}</td><td>{c.semantic_type}</td><td>{c.role}</td><td>{c.distinct_count}</td><td>{percentage(c.missing_percentage)}</td></tr>)}</tbody></table></div></details>
      </>}
    </section>
    <section id="source-relationships" className="panel"><h2>Relationships</h2><p className="muted">Pearson correlation · first {profile.correlation.columns.length} of {profile.correlation.eligible_count} continuous numeric feature candidates (maximum {profile.correlation.column_limit}). Target and excluded features are omitted. Each pair uses its non-missing observations.</p><Heatmap correlation={profile.correlation} /></section>
  </div>;
}
