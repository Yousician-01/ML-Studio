export type CodeDraft = {
  id: string; project_id: string; origin_revision: number; origin_ir: Record<string, unknown>;
  baseline_source: string; baseline_sha256: string; plan_sha256: string;
  source: string; status: "active" | "archived" | "discarded";
  created_at: string; updated_at: string; revision: number; modified: boolean;
};
export type CodeSnapshot = { id: string; draft_id: string; created_at: string; source_sha256: string; source: string };
export type ReportingProposal = { status: "ready" | "present" | "manual"; revision: number; proposed_source: string | null; diff: string; example: string; message: string };
export function sourceState(draft: Pick<CodeDraft, "source" | "baseline_source">, source: string) {
  return { modified: source !== draft.baseline_source, dirty: source !== draft.source };
}
