import type { CodePreview } from "./api/code";
import type { PipelineIR, ModelIntent, WorkingPipeline, ParameterSchema } from "./api/pipelines";
import { parseParameters, editedSplit } from "./api/task-policy";

export function previewConfiguration(state: WorkingPipeline, kind: "model" | "split", values: Record<string, string>): PipelineIR | null {
  try {
    const descriptor = state.model_catalogue.find(d => d.id === state.ir.model?.type);
    const schemas: Record<string, ParameterSchema> = kind === "model" ? descriptor?.parameter_schema.properties ?? {} : Object.fromEntries(Object.keys(state.ir.split ?? {}).map(k => [k, { anyOf: [{ type: k === "stratify" ? "boolean" : k === "random_seed" ? "integer" : "number" }, { type: "null" }] }]));
    const parsed = parseParameters(values, schemas);
    return kind === "model" ? { ...state.ir, model: { ...state.ir.model!, parameters: parsed } as ModelIntent } : { ...state.ir, split: editedSplit(state.ir.split!, parsed) };
  } catch { return null; }
}

// Cancellation plus identity protects against transports that resolve after abort.
export class PreviewRequests {
  private sequence = 0;
  private controller: AbortController | null = null;
  cancel() { this.sequence++; this.controller?.abort(); }
  async run(load: (signal: AbortSignal) => Promise<CodePreview>, accept: (value: CodePreview) => void, fail: (error: unknown) => void) {
    this.cancel();
    const sequence = this.sequence;
    const controller = this.controller = new AbortController();
    try {
      const value = await load(controller.signal);
      if (!controller.signal.aborted && sequence === this.sequence) accept(value);
    } catch (error) {
      if (!controller.signal.aborted && sequence === this.sequence) fail(error);
    }
  }
}

export function currentPreview(value: CodePreview | null, key: string, resultKey: string) {
  return key === resultKey && value?.ready && value.source ? value : null;
}

export type ViewerPreference = { presentation: "closed" | "docked" | "floating"; width: number };
export function viewerPreference(value: unknown): ViewerPreference {
  const input = value as Partial<ViewerPreference> | null;
  return { presentation: input && ["closed", "docked", "floating"].includes(input.presentation ?? "") ? input.presentation! : "closed",
    width: typeof input?.width === "number" && Number.isFinite(input.width) ? Math.min(65, Math.max(35, input.width)) : 45 };
}
