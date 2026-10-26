"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Dataset } from "@/lib/api/projects";
import type { RegressionProfile, TargetRelationship } from "@/lib/api/profiles";
import { displayScalar } from "@/lib/api/scalars";
import { Histogram, compactNumber } from "./explore-charts";
import { Alert, Button, EmptyState, Loading, Panel } from "./ui";

export function TargetScatter({ relationship: r }: { relationship: TargetRelationship }) {
  if (r.scatter_unavailable_reason || !r.points.length) return <Alert tone="info">Scatter unavailable: {r.scatter_unavailable_reason || "No complete pairs."}</Alert>;
  const xs = r.points.map(p => p.x), ys = r.points.map(p => p.y);
  const left = Math.min(...xs), right = Math.max(...xs), low = Math.min(...ys), high = Math.max(...ys);
  const x = (v: number) => left === right ? 309 : 60 + (v - left) / (right - left) * 498;
  const y = (v: number) => low === high ? 115 : 192 - (v - low) / (high - low) * 150;
  return <figure className="eda-plot">
    <figcaption>Target versus feature · {r.points.length} of {r.paired_rows} complete source pairs</figcaption>
    <svg viewBox="0 0 610 260" role="img" aria-label={`Target versus feature: ${r.target} versus ${r.feature}. ${r.points.length} actual source pairs.`}>
      <line x1="60" x2="558" y1="192" y2="192" className="eda-grid-line" />
      <line x1="60" x2="60" y1="42" y2="192" className="eda-grid-line" />
      {r.points.map((p, i) => <circle key={i} cx={x(p.x)} cy={y(p.y)} r="3" fill="var(--accent)" opacity="0.65"><title>{`${r.feature}: ${p.x}; ${r.target}: ${p.y}`}</title></circle>)}
      <text x="60" y="216">{compactNumber(left)}</text><text x="558" y="216" textAnchor="end">{compactNumber(right)}</text>
      <text x="52" y="47" textAnchor="end">{compactNumber(high)}</text><text x="52" y="192" textAnchor="end">{compactNumber(low)}</text>
      <text x="309" y="240" textAnchor="middle">Feature source value (x)</text><text x="60" y="22">Target source value (y)</text>
    </svg>
    <p className="muted">At most {r.point_limit} complete pairs, evenly spaced in source order. This deterministic preview is not a random sample or evidence of causation. Correlation uses all complete pairs, not just plotted points.</p>
    <details><summary>Source pair values</summary><div className="table-scroll"><table><caption className="sr-only">Bounded source pairs: {r.feature} and {r.target}</caption><thead><tr><th scope="col">{r.feature}</th><th scope="col">{r.target}</th></tr></thead><tbody>{r.points.map((p, i) => <tr key={i}><td>{String(p.x)}</td><td>{String(p.y)}</td></tr>)}</tbody></table></div></details>
  </figure>;
}

export function RegressionProfileView({ profile: p, projectId, onFeature, onPage, pending = false, pagePending = false, selectedFeature }: {
  profile: RegressionProfile; projectId: string; onFeature: (name: string) => void; onPage: (offset: number) => void; pending?: boolean; pagePending?: boolean; selectedFeature?: string;
}) {
  const t = p.target, r = p.relationship;
  return <div className="explore-view visual-explore">
    <div className="section-heading"><div><div className="eyebrow">Full source · {p.original_filename}</div><h2>Regression Explore</h2><p className="muted">Observed source evidence, before any preparation or training split.</p></div><span className="badge subtle">Revision {p.revision}</span></div>
    <Panel title="Source & target summary" description="Verified managed source; no rows are transformed or removed.">
      <dl className="eda-facts"><div><dt>Source rows</dt><dd>{p.row_count.toLocaleString()}</dd></div><div><dt>Columns</dt><dd>{p.column_count}</dd></div><div><dt>Observed target rows</dt><dd>{t?.observed_count.toLocaleString() ?? "No target"}</dd></div><div><dt>Missing target rows</dt><dd>{t?.missing_count.toLocaleString() ?? "No target"}</dd></div></dl>
      {t && <p className="wrap">Target: <strong>{t.name}</strong> · physical {t.physical_dtype} · semantic {t.semantic_type}</p>}
      <p className="muted">Source integrity: {p.source_integrity}. Missing target values are excluded from target summaries and pair calculations, never treated as zero.</p>
      <details><summary>Dataset identity</summary><p className="wrap">{p.dataset_id}<br /><code>{p.fingerprint}</code></p></details>
    </Panel>
    {!t ? <Panel title="Select a numeric target"><EmptyState title="Select a numeric target in Data">A numeric target is needed for target summaries and feature relationships. <Link href={`/projects/${projectId}?view=data`}>Open Data</Link></EmptyState></Panel> : <>
      <Panel title="Target descriptive statistics" description="Non-missing source targets only; constant and two-valued numeric targets are valid.">
        {t.constant && <Alert tone="info">Constant target: one distinct observed value. This does not invalidate regression configuration.</Alert>}
        <dl className="eda-facts">{[["Minimum", displayScalar(t.numeric.minimum)], ["Maximum", displayScalar(t.numeric.maximum)], ["Mean", compactNumber(t.numeric.mean)], ["Median", compactNumber(t.numeric.median)], ["Standard deviation", compactNumber(t.numeric.standard_deviation)], ["Q1", compactNumber(t.numeric.q1)], ["Q3", compactNumber(t.numeric.q3)], ["Distinct observed values", t.distinct_count]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
        <p className="muted">Sample standard deviation uses ddof=1 and is unavailable with fewer than two observations. Quartiles use linear interpolation.</p>
        {t.numeric.unavailable_reason && <Alert tone="info">{t.numeric.unavailable_reason}</Alert>}
        <Histogram key={`${p.dataset_id}:${p.revision}`} stats={t.numeric} name={t.name} />
      </Panel>
      <Panel title="Numeric feature relationships" description="Source relationships are descriptive, not statistical significance or causation.">
        {p.feature_options.length ? <label>Numeric feature<select disabled={pagePending} value={selectedFeature || r?.feature || ""} onChange={event => onFeature(event.target.value)} aria-label="Numeric feature" aria-busy={pending}>{p.feature_options.map(f => <option key={f.name} value={f.name}>{f.name} · {f.physical_dtype} · {f.semantic_type} · {f.role}</option>)}</select></label> : <p>No numeric features on this page. Numeric non-Boolean columns with continuous, binary or unknown semantics are eligible; review semantics in Data.</p>}
        <div className="actions"><Button disabled={pending || p.feature_offset === 0} onClick={() => onPage(Math.max(0, p.feature_offset - p.feature_limit))}>Previous features</Button><span>{p.feature_options.length ? p.feature_offset + 1 : 0}–{p.feature_offset + p.feature_options.length} of {p.numeric_feature_count}</span><Button disabled={pending || p.feature_offset + p.feature_options.length >= p.numeric_feature_count} onClick={() => onPage(p.feature_offset + p.feature_limit)}>Next features</Button></div>
        {pending ? <Loading>Loading selected feature relationship…</Loading> : r && <><p className="wrap">{r.feature} → {r.target}</p><dl className="eda-facts"><div><dt>Pearson correlation</dt><dd>{compactNumber(r.pearson)}</dd></div><div><dt>Complete pairs</dt><dd>{r.paired_rows}</dd></div><div><dt>Missing pairs</dt><dd>{r.missing_pair_rows}</dd></div></dl><p className="muted">{r.missing_feature_rows} missing feature values · {r.missing_target_rows} missing target values. Missing-pair count is their union across all {p.row_count} source rows.</p>{r.correlation_unavailable_reason && <Alert tone="info">{r.correlation_unavailable_reason}</Alert>}<TargetScatter relationship={r} /></>}
      </Panel>
    </>}
  </div>;
}

export function RegressionExplore({ projectId, dataset, onReload }: {
  projectId: string; dataset: Pick<Dataset, "id" | "revision"> | null; onReload: () => void;
}) {
  const [profile, setProfile] = useState<RegressionProfile | null>(null);
  const [feature, setFeature] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const id = dataset?.id, revision = dataset?.revision;
  useEffect(() => {
    if (!id || revision === undefined) return;
    const controller = new AbortController();
    api.profile(projectId, { id, revision }, offset, controller.signal, undefined, feature || undefined).then(next => {
      if (controller.signal.aborted) return;
      if (next.task !== "regression") throw new Error("Profile task does not match this Project. Reload the workspace.");
      setProfile(next); setError("");
    }).catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Regression profile unavailable."); });
    return () => controller.abort();
  }, [projectId, id, revision, feature, offset]);
  if (!dataset) return <Panel title="Regression Explore"><EmptyState title="No Dataset">Upload a CSV in <Link href={`/projects/${projectId}?view=data`}>Data</Link> to explore regression source evidence.</EmptyState></Panel>;
  if (error) return <Panel title="Regression Explore unavailable"><Alert>{error} Invalid targets must be corrected in Data. No stale evidence is shown.</Alert><Button onClick={onReload}>Reload current Dataset</Button></Panel>;
  if (!profile || profile.dataset_id !== id || profile.revision !== revision) return <Panel title="Regression Explore"><Loading>Profiling verified regression source…</Loading></Panel>;
  const pending = profile.feature_offset !== offset || Boolean(feature && profile.relationship?.feature !== feature);
  return <RegressionProfileView profile={profile} projectId={projectId} pending={pending} pagePending={profile.feature_offset !== offset} selectedFeature={feature} onFeature={name => { setFeature(name); setError(""); }} onPage={next => { setOffset(next); setFeature(""); setError(""); }} />;
}
