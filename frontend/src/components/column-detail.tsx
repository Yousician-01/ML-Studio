"use client";
import { useState } from "react";
import type { ColumnProfile } from "@/lib/api/profiles";
import type { OnPrepare } from "@/lib/preparation-handoff";
import { displayScalar } from "@/lib/api/scalars";
import { Alert, Button } from "./ui";
import { Bars, Boxplot, Histogram, compactNumber, percentage } from "./explore-charts";
import { EdaPreparationActions, type EvidenceScope } from "./eda-preparation-actions";

export function ColumnDetail({ column, scope, onPrepare, onMultiplier }: { column: ColumnProfile; scope?: EvidenceScope; onPrepare?: OnPrepare; onMultiplier?: (value: number) => void }) {
  const [plot, setPlot] = useState("histogram");
  const [varianceThreshold, setVarianceThreshold] = useState(.01);
  const [missingThreshold, setMissingThreshold] = useState(20);
  const stats = column.numeric;
  return <article className="eda-column-detail">
    <div className="section-heading"><div><div className="eyebrow">Source distribution</div><h3 className="wrap">{column.name}</h3></div><span className="badge accent">{column.semantic_type}</span></div>
    <EdaPreparationActions column={column} scope={scope} onPrepare={onPrepare} />
    <p className="muted">Exploratory statistics - original source dataset; not fitted training evidence.</p>
    <label>High missingness threshold (%)<input type="number" min={0} max={100} value={missingThreshold} onChange={e => setMissingThreshold(Number(e.target.value))} /></label>
    {missingThreshold >= 0 && missingThreshold <= 100 && column.missing_percentage >= missingThreshold && column.missing_count > 0 && <p className="observation-note">Missingness meets the selected exploratory threshold. Review imputation or feature participation; no treatment is applied automatically.</p>}
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
      {onMultiplier && <label>Exploratory IQR multiplier<input key={stats.iqr_multiplier ?? 1.5} type="number" min={.1} max={10} step={.1} defaultValue={stats.iqr_multiplier ?? 1.5} onBlur={e => { const value = Number(e.target.value); if (e.target.value && Number.isFinite(value) && value >= .1 && value <= 10) onMultiplier(value); else e.currentTarget.reportValidity(); }} /></label>}
      {column.semantic_type === "continuous" && <><label>Exploratory low-variance threshold<input type="number" min={0} step="any" value={varianceThreshold} onChange={e => setVarianceThreshold(Number(e.target.value))} /></label><p>Source population variance (ddof=0): {compactNumber(stats.variance ?? null)}. {stats.variance !== undefined && stats.variance !== null && varianceThreshold >= 0 && stats.variance <= varianceThreshold ? "At or below your threshold; review feature selection." : ""} {stats.count < 2 ? "Insufficient observations for a reliable variance review." : ""} Training selection uses the configured branch scale, which can differ.</p></>}

      {!stats.unavailable_reason && <>
        <div className="eda-tabs" aria-label="Numerical chart"><Button aria-pressed={plot === "histogram"} onClick={() => setPlot("histogram")}>Histogram</Button><Button aria-pressed={plot === "boxplot"} onClick={() => setPlot("boxplot")}>Boxplot</Button></div>
        {plot === "histogram" ? <Histogram stats={stats} name={column.name} /> : <Boxplot stats={stats} name={column.name} />}
      </>}
      {stats.unavailable_reason && <Alert tone="info">{stats.unavailable_reason}</Alert>}
      <dl className="eda-facts numeric-facts">
        {[["Mean", compactNumber(stats.mean)], ["Sample std. dev.", compactNumber(stats.standard_deviation)], ["Minimum", displayScalar(stats.minimum)], ["Q1", compactNumber(stats.q1)], ["Median", compactNumber(stats.median)], ["Q3", compactNumber(stats.q3)], ["Maximum", displayScalar(stats.maximum)], ["Skewness", compactNumber(stats.skewness)]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
      </dl>
      {stats.skewness_unavailable_reason && <p className="muted">{stats.skewness_unavailable_reason}</p>}
      <div className="observation-note"><strong>IQR outliers (multiplier {stats.iqr_multiplier ?? 1.5}): {stats.outlier_count === null ? "Unavailable" : `${stats.outlier_count.toLocaleString()} (${percentage(stats.outlier_percentage ?? 0)})`}</strong><p className="muted">Outside fences [{stats.lower_fence === null ? "unavailable" : String(stats.lower_fence)}, {stats.upper_fence === null ? "unavailable" : String(stats.upper_fence)}]. Percentages use non-missing observations. Below: {stats.below_fence_count ?? "unavailable"}; above: {stats.above_fence_count ?? "unavailable"}; IQR: {compactNumber(stats.iqr ?? null)}. Values are not removed or labelled errors. Training will fit its own fences.</p></div>
      <details><summary>Exact statistics and calculation notes</summary><dl className="eda-facts">
        {[["Mean", stats.mean], ["Sample standard deviation", stats.standard_deviation], ["Q1", stats.q1], ["Median", stats.median], ["Q3", stats.q3], ["Adjusted Fisher-Pearson skewness", stats.skewness]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value === null ? "Unavailable" : String(value)}</dd></div>)}
      </dl><p className="muted">Quartiles use linear interpolation. Fences are Q1 - {stats.iqr_multiplier ?? 1.5} * IQR and Q3 + {stats.iqr_multiplier ?? 1.5} * IQR. Skewness uses adjusted Fisher-Pearson G1 for at least three varying observations; no subjective skew categories are applied.</p></details>
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

