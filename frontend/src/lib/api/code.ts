import type { PipelineIssue } from "./pipelines";

export type CodePreview = {
  context: "working_pipeline";
  project_id: string;
  revision: number;
  dataset_id: string | null;
  generator: string;
  ready: boolean;
  issues: PipelineIssue[];
  source: string | null;
  source_sha256: string | null;
  plan_sha256: string | null;
  filename: string;
  libraries: Record<string, string>;
};
