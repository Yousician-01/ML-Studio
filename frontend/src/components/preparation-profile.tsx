"use client";

import { useEffect, useState } from "react";
import { api, type Column, type Dataset, type ProjectTask } from "@/lib/api/projects";
import type { ColumnProfile } from "@/lib/api/profiles";
import { displayScalar } from "@/lib/api/scalars";
import { ColumnDetail } from "./explore";
import { RegressionExplore } from "./regression-explore";
import { Alert, Loading } from "./ui";

export function PreparationProfile({ projectId, dataset, column, task, cache, derived, onReload, available = true }: {
  projectId: string; dataset: Dataset; column: Column; task: ProjectTask; cache: Map<string, ColumnProfile>; derived: boolean; onReload: () => void; available?: boolean;
}) {
  const key = JSON.stringify([projectId, dataset.id, dataset.revision, column.name]);
  const [profile, setProfile] = useState<ColumnProfile | null>(cache.get(key) ?? null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (derived || task === "regression" || cache.has(key)) return;
    const controller = new AbortController();
    api.profile(projectId, dataset, Math.floor(column.source_order / 20) * 20, controller.signal).then(result => {
      if (controller.signal.aborted || result.task === "regression") return;
      const found = result.columns.find(value => value.name === column.name);
      if (!found) throw new Error("This column profile is unavailable on the returned source page. Use dataset diagnostics to inspect the source.");
      if (cache.size >= 20) cache.delete(cache.keys().next().value!);
      cache.set(key, found); setProfile(found);
    }).catch(err => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Column profile unavailable."); });
    return () => controller.abort();
  }, [projectId, dataset, column, task, cache, key, derived]);
  return <div>
    <dl className="eda-facts"><div><dt>Column</dt><dd>{column.name}</dd></div><div><dt>Physical dtype</dt><dd>{derived && !available ? "Not resolved" : column.physical_dtype}</dd></div><div><dt>Effective type</dt><dd>{column.effective_semantic_type}</dd></div><div><dt>Missing</dt><dd>{available ? column.missing_count : "Not previewed"}</dd></div><div><dt>Distinct source observations</dt><dd>{derived ? "Not profiled" : column.unique_count}</dd></div></dl>
    {!derived && <p className="muted">Source sample: {dataset.preview.slice(0, 8).map(row => displayScalar(row[column.source_order])).join(", ")}. Source facts do not describe fitted training data.</p>}
    {derived ? <p>Derived sample values and missing counts are available in the table preview. Source profiling does not invent distributions for derived columns.</p> : task === "regression" ? <RegressionExplore projectId={projectId} dataset={dataset} onReload={onReload} /> : error ? <Alert>{error}</Alert> : profile ? <ColumnDetail column={profile} /> : <Loading>Loading source column profile...</Loading>}
  </div>;
}
