import type { Column } from "@/lib/api/projects";
import type { PipelineIR } from "@/lib/api/pipelines";
import { appliedSteps } from "@/lib/preparation";
import { featureLineage } from "@/lib/lineage";

export function FeatureLineage({ ir, columns, column }: { ir: PipelineIR; columns: Column[]; column: Column }) {
  const lineage = featureLineage(appliedSteps(ir, columns.filter(c => !["temporal-v1", "derived-v1", "imputation-v1", "feature-engineering-v1", "outlier-treatment-v1"].includes(c.inference_version))), column.name);
  const step = lineage.producer;
  return <div className="studio-editor"><h3>{column.name}</h3><dl className="eda-facts"><div><dt>Origin / producer</dt><dd>{step?.label ?? "Original source column"}</dd></div><div><dt>Execution stage</dt><dd>{step?.stage ?? "Raw source; current interpretation may include cleaning"}</dd></div><div><dt>Semantic / physical type</dt><dd>{column.effective_semantic_type} / {column.physical_dtype}</dd></div><div><dt>Model participation</dt><dd>{ir.target?.column === column.name ? "Supervised target; not a predictor" : ir.features[column.name]?.included ? "Included" : "Excluded / intermediate"}</dd></div><div><dt>Fitted or stateless</dt><dd>{step?.stage.includes("Train-fitted") || step?.kind === "advanced" ? "Requires training-fitted state" : "Stateless source/row-wise value"}</dd></div></dl><p>Direct inputs: {lineage.direct.join(", ") || "None (raw source)"}</p><p>Transitive inputs: {lineage.ancestors.join(", ") || "None"}</p><p>Used by: {lineage.dependents.join("; ") || "No downstream transformation"}</p><p>Structural checks prevent target/stage misuse. They cannot determine whether a source contains future or post-outcome information.</p></div>;
}
