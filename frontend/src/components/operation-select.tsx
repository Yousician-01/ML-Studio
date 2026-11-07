"use client";

import type { FeatureIntent, Operation } from "@/lib/api/pipelines";
import { setOperation } from "@/lib/preparation";

export function OperationSelect({ name, feature, family, numeric, disabled, onChange }: {
  name: string; feature: FeatureIntent; family: Operation["type"]; numeric: boolean; disabled?: boolean; onChange: (feature: FeatureIntent) => void;
}) {
  const operation = feature.operations.find(operation => operation.type === family);
  const value = operation ? operation.type === "impute" ? operation.strategy : operation.method : "";
  const choices = family === "impute" ? [...(numeric ? ["mean", "median"] : []), "most_frequent"] : family === "scale" ? ["standard", "min_max", "robust"] : ["one_hot"];
  return <select aria-label={`${family === "impute" ? "Missing values" : family === "scale" ? "Scaling" : "Encoding"} for ${name}`} disabled={disabled} value={value} onChange={event => onChange(setOperation(feature, family, event.target.value))}>
    <option value="">None</option>{choices.map(choice => <option key={choice} value={choice}>{({ mean: "Mean", median: "Median", most_frequent: "Most frequent", standard: "Standard", min_max: "MinMax", robust: "Robust", one_hot: "One-hot" } as Record<string, string>)[choice]}</option>)}
    {value && !choices.includes(value) && <option value={value}>{value} (incompatible)</option>}
  </select>;
}
