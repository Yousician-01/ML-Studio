import type { CodeDraft } from "./code-drafts";
import type { BinaryResult, RegressionResult } from "./runs";
export type CodeEvaluationResult = ({ task: "binary_classification" } & Pick<BinaryResult, "metrics" | "confusion_matrix" | "roc_auc_unavailable_reason"> | { task: "regression" } & Pick<RegressionResult, "metrics" | "r2_unavailable_reason">) & { population: { test: number } };
export type CodeEvaluation = {
  status: "pending" | "execution_incomplete" | "not_reported" | "invalid" | "available" | "unavailable_or_corrupt";
  report: null | { schema_version: "mlstudio-code-report-v1"; evaluation: CodeEvaluationResult | null; metrics: Record<string, number>; outputs: Record<string, unknown> };
};
export type CodeRun = {
  id: string; project_id: string; draft_id: string; snapshot_id: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  source: string | null; source_sha256: string; source_integrity: "verified" | "unavailable_or_corrupt";
  entrypoint: string; artifact_directory: string; configuration: Record<string, unknown>;
  created_at: string; started_at: string | null; finished_at: string | null;
  duration_seconds: number | null; exit_code: number | null; error: string | null;
};
export type CodeRunStarted = CodeRun & { draft: CodeDraft | null };
export type CodeRunPage = { items: CodeRun[]; total: number; active: CodeRun | null; enabled: boolean };
export type CodeLogs = { stdout: string; stderr: string; stdout_truncated: boolean; stderr_truncated: boolean; stdout_tail_only?: boolean; stderr_tail_only?: boolean };
export const codeRunActive = (run: CodeRun | null) => run?.status === "PENDING" || run?.status === "RUNNING";
