"use client";

import { useState } from "react";
import type { NumericProfile, Profile } from "@/lib/api/profiles";

export const compactNumber = (value: number | null) => value === null ? "Unavailable" :
  new Intl.NumberFormat(undefined, { maximumSignificantDigits: 5 }).format(value);
export const percentage = (value: number) => `${value.toFixed(1)}%`;

export type BarDatum = { label: string; count: number; percentage: number; note?: string };

export function Bars({ data, label, percentScale = false }: {
  data: BarDatum[]; label: string; percentScale?: boolean;
}) {
  const max = percentScale ? 100 : Math.max(1, ...data.map(item => item.count));
  return <figure className="eda-bars" aria-label={label}>
    <figcaption className="chart-caption">{label}</figcaption>
    {data.map((item, index) => <div className="eda-bar-row" key={index} tabIndex={0}
      aria-label={`${item.label}: ${item.count} observations, ${item.percentage}%. ${item.note ?? ""}`}>
      <div className="eda-bar-label"><span title={item.label}>{item.label}</span><small>{item.note}</small></div>
      <div className="eda-bar-track" aria-hidden="true"><span style={{ width: `${100 * (percentScale ? item.percentage : item.count) / max}%` }} /></div>
      <div className="eda-bar-value"><strong>{item.count.toLocaleString()}</strong><small>{percentage(item.percentage)}</small></div>
    </div>)}
  </figure>;
}

export function Histogram({ stats, name }: { stats: NumericProfile; name: string }) {
  const [selected, setSelected] = useState<number | null>(null);
  const bins = stats.histogram;
  if (!bins.length) return null;
  const low = bins[0].lower, high = bins[bins.length - 1].upper;
  const max = Math.max(1, ...bins.map(bin => bin.count));
  const x = (v: number) => high === low ? 44 : 44 + 530 * (v - low) / (high - low);
  const bin = selected === null ? null : bins[selected];
  const binText = (index: number) => {
    const item = bins[index];
    return `${name}: ${item.lower} ≤ value ${index === bins.length - 1 ? "≤" : "<"} ${item.upper}; ${item.count} observations`;
  };
  return <figure className="eda-plot">
    <figcaption>Distribution <span className="muted">· {stats.count.toLocaleString()} non-missing observations</span></figcaption>
    <svg viewBox="0 0 610 240" role="group" aria-label={`Histogram of ${name}`}>
      {[0, .5, 1].map(t => <g key={t} aria-hidden="true">
        <line x1="44" x2="574" y1={194 - t * 160} y2={194 - t * 160} className="eda-grid-line" />
        <text x="36" y={198 - t * 160} textAnchor="end">{compactNumber(max * t)}</text>
      </g>)}
      {bins.map((b, i) => <rect key={i} x={x(b.lower) + 1} y={194 - 160 * b.count / max}
        width={high === low ? 528 : Math.max(1, x(b.upper) - x(b.lower) - 2)}
        height={160 * b.count / max} className={`eda-bin ${selected === i ? "active" : ""}`}
        tabIndex={0} role="button" aria-label={binText(i)} aria-pressed={selected === i}
        onMouseEnter={() => setSelected(i)} onFocus={() => setSelected(i)} onClick={() => setSelected(i)}
        onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelected(i); } }}>
        <title>{binText(i)}</title>
      </rect>)}
      <text x="44" y="218">{compactNumber(low)}</text>
      <text x="574" y="218" textAnchor="end">{compactNumber(high)}</text>
      <text x="309" y="238" textAnchor="middle">Source value</text>
    </svg>
    <div className="chart-readout" role="status">{bin && selected !== null ? binText(selected) : "Hover or focus a bin for its exact range and count."}</div>
    <details><summary>Histogram values and definition</summary>
      <p className="muted">At most 10 equal-width bins. Repeated floating-point edges collapse; constant values use one bin. Missing values are excluded. Only the last bin includes its upper edge.</p>
      <div className="table-scroll"><table><thead><tr><th>Lower</th><th>Upper</th><th>Count</th></tr></thead><tbody>
        {bins.map((b, i) => <tr key={i}><td>{String(b.lower)}</td><td>{String(b.upper)}</td><td>{b.count}</td></tr>)}
      </tbody></table></div>
    </details>
  </figure>;
}

export function Boxplot({ stats, name }: { stats: NumericProfile; name: string }) {
  const [focused, setFocused] = useState<string>("");
  const { lower_whisker: low, upper_whisker: high, q1, median, q3 } = stats;
  if (low === null || high === null || q1 === null || q3 === null || median === null) return null;
  const x = (v: number) => low === high ? 310 : 44 + (v - low) / (high - low) * 530;
  const points: [string, number][] = [["Lower whisker", low], ["Q1", q1], ["Median", median], ["Q3", q3], ["Upper whisker", high]];
  return <figure className="eda-plot">
    <figcaption>Boxplot <span className="muted">· linear quartiles and 1.5 × IQR</span></figcaption>
    <svg viewBox="0 0 610 180" role="group" aria-label={`Boxplot of ${name}`}>
      <line x1={x(low)} x2={x(high)} y1="70" y2="70" className="eda-whisker" />
      <rect x={x(q1)} y="45" width={Math.max(1, x(q3) - x(q1))} height="50" className="eda-box" />
      {points.map(([label, value]) => <g key={label} tabIndex={0} role="img" aria-label={`${label}: ${value}`}
        onMouseEnter={() => setFocused(`${label}: ${value}`)} onFocus={() => setFocused(`${label}: ${value}`)}>
        <rect x={x(value) - 7} y="30" width="14" height="80" fill="transparent" />
        <line x1={x(value)} x2={x(value)} y1={label === "Median" ? 43 : 55} y2={label === "Median" ? 97 : 85} className="eda-whisker" />
        <title>{label}: {value}</title>
      </g>)}
      <text x="44" y="145">{compactNumber(low)}</text><text x="574" y="145" textAnchor="end">{compactNumber(high)}</text>
    </svg>
    <div className="chart-readout" role="status">{focused || "Hover or focus a marker for its exact value. Outlier points are not sent or drawn."}</div>
    <details><summary>Boxplot values and definition</summary><dl className="eda-facts">
      {points.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{String(value)}</dd></div>)}
    </dl><p className="muted">Whiskers enclose observations within the fences and extend at least to the interpolated quartiles. Outliers are counted against fences, not displayed as invented points.</p></details>
  </figure>;
}

export function Heatmap({ correlation }: { correlation: Profile["correlation"] }) {
  const [selected, setSelected] = useState<[number, number] | null>(null);
  const { columns, values, pair_counts: counts } = correlation;
  const describe = (i: number, j: number) => `${columns[i]} × ${columns[j]}: Pearson r ${values[i][j] === null ? "unavailable (constant, insufficient, or precision-limited data)" : String(values[i][j])}; ${counts[i][j]} paired observations`;
  const color = (value: number | null) => value === null ? "var(--surface-subtle)" :
    `color-mix(in srgb, ${value < 0 ? "#b7755b" : "#535bab"} ${Math.abs(value) * 100}%, #f3f4f8)`;
  if (correlation.unavailable_reason) return <p className="muted">{correlation.unavailable_reason}</p>;
  return <div className="eda-heatmap">
    <div className="correlation-scale" aria-label="Correlation scale"><span>−1 · negative</span><span>0 · no linear association</span><span>+1 · positive</span></div>
    <div className="table-scroll"><div className="heatmap-grid" style={{ gridTemplateColumns: `180px repeat(${columns.length}, minmax(48px, 1fr))` }} role="group" aria-label="Pearson correlation heatmap">
      <span />{columns.map((name, i) => <span className="heatmap-heading" title={name} key={name}>{i + 1}</span>)}
      {columns.map((name, i) => <div className="heatmap-row" key={name}>
        <span className="heatmap-name" title={name}>{i + 1}. {name}</span>
        {values[i].map((value, j) => <button key={j} style={{ background: color(value), color: value !== null && Math.abs(value) > .65 ? "white" : "#242938" }}
          className="heatmap-cell" aria-label={describe(i, j)} aria-pressed={selected?.[0] === i && selected?.[1] === j}
          onMouseEnter={() => setSelected([i, j])} onFocus={() => setSelected([i, j])} onClick={() => setSelected([i, j])}>
          {value === null ? "—" : value.toFixed(2)}
        </button>)}
      </div>)}
    </div></div>
    <div className="chart-readout" role="status">{selected ? describe(...selected) : "Select or focus a cell for its exact coefficient and paired count."}</div>
    <p className="muted">Diagonal cells compare a feature with itself. Correlation describes linear association, not causation.</p>
    <details><summary>Correlation values as a table</summary><div className="table-scroll"><table><thead><tr><th>Feature</th>{columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>
      {columns.map((c, i) => <tr key={c}><th>{c}</th>{values[i].map((v, j) => <td key={j}>{v === null ? "Unavailable" : String(v)}<small>n={counts[i][j]}</small></td>)}</tr>)}
    </tbody></table></div></details>
  </div>;
}
