"use client";

import { useState } from "react";
import type { ColumnProfile, Profile } from "@/lib/api/profiles";
import { correlatedPairs, preparationActions, type OnPrepare, type PreparationAction } from "@/lib/preparation-handoff";
import { Alert, Button } from "./ui";

export type EvidenceScope = { projectId: string; datasetId: string; revision: number };
const labels: Record<PreparationAction, string> = { outliers: "Treat Outliers", "outlier-indicator": "Add Outlier Indicator", variance: "Review Feature Selection", exclude: "Exclude Feature", missing: "Handle Missing Values", numeric: "Transform Numeric", rare: "Group Rare Categories" };
export function EdaPreparationActions({ column, scope, onPrepare }: { column: ColumnProfile; scope?: EvidenceScope; onPrepare?: OnPrepare }) {
  if (!scope || !onPrepare || column.role === "target") return null;
  return <div className="actions" aria-label={`Prepare ${column.name}`}>{preparationActions(column).map(action => <Button key={action} onClick={() => onPrepare({ ...scope, feature: column.name, action, ...((action === "outliers" || action === "outlier-indicator") ? { multiplier: column.numeric?.iqr_multiplier ?? 1.5 } : {}) })}>{labels[action]}</Button>)}</div>;
}

export function CorrelationDiagnostics({ correlation }: { correlation: Profile["correlation"] }) {
  const [threshold, setThreshold] = useState(.9);
  const valid = Number.isFinite(threshold) && threshold >= 0 && threshold <= 1;
  const pairs = correlatedPairs(correlation, threshold).sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  return <div className="observation-note"><label>Strong-correlation threshold |r|<input type="number" min={0} max={1} step={.05} value={Number.isFinite(threshold) ? threshold : ""} onChange={e => setThreshold(e.target.value === "" ? NaN : Number(e.target.value))} /></label>
    {!valid ? <Alert>Choose a threshold between 0 and 1.</Alert> : <><p>{pairs.length} source feature pairs meet |r| ≥ {threshold}. Showing up to 24 pairs from the existing bounded matrix.</p><ul>{pairs.slice(0, 24).map(pair => <li key={JSON.stringify([pair.left, pair.right])}>{pair.left} / {pair.right}: r={pair.value.toPrecision(4)}, {pair.count} complete source pairs</li>)}</ul></>}
    <p>Exploratory full-source evidence only. Correlation does not establish redundancy in every model. No feature is automatically removed.</p>
  </div>;
}
