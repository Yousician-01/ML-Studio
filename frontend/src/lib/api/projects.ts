export const semanticTypes = [
  "continuous",
  "categorical",
  "binary",
  "datetime",
  "identifier",
  "text",
  "unknown",
] as const;
export type SemanticType = (typeof semanticTypes)[number];
export type LosslessInteger = { value_type: "integer"; value: string };
export type Scalar = string | number | boolean | LosslessInteger | null;
export type ProjectInput = {
  name: string;
  description: string | null;
  problem_statement: string;
  success_context?: string | null;
};
export type Project = ProjectInput & {
  id: string;
  ml_objective: "binary_classification";
  created_at: string;
  updated_at: string;
  active_dataset_id: string | null;
  target_column: string | null;
  revision: number;
};
export type Column = {
  name: string;
  source_order: number;
  physical_dtype: string;
  missing_count: number;
  unique_count: number;
  inferred_semantic_type: SemanticType;
  semantic_override: SemanticType | null;
  effective_semantic_type: SemanticType;
  role: "feature" | "target" | "excluded";
};
export type Dataset = {
  id: string;
  revision: number;
  project_id: string;
  original_filename: string;
  format: "csv";
  created_at: string;
  fingerprint: string;
  size_bytes: number;
  row_count: number;
  column_count: number;
  missing_cells: number;
  duplicate_rows: number;
  columns: Column[];
  target_column: string | null;
  target_classes: Scalar[];
  preview: Scalar[][];
  preview_limit: number;
};
export type DatasetChange = {
  dataset_id: string;
  revision: number;
  semantic_overrides?: Record<string, SemanticType | null>;
  target_column?: string | null;
};

const baseUrl = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1"
).replace(/\/$/, "");

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  const timeout = AbortSignal.timeout(options.method ? 120000 : 30000);
  try {
    response = await fetch(baseUrl + path, {
      ...options,
      cache: "no-store",
      signal: options.signal
        ? AbortSignal.any([options.signal, timeout])
        : timeout,
    });
  } catch {
    if (timeout.aborted)
      throw new Error(
        "The request timed out. Reload the workspace before retrying; a save may have completed.",
      );
    throw new Error(
      "The API could not be reached. Check that the local backend is running, then retry.",
    );
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : `Request failed (${response.status}). Check your input and retry.`,
    );
  }
  return response.json() as Promise<T>;
}
const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
const projectPath = (id: string) => `/projects/${encodeURIComponent(id)}`;

export const api = {
  projects: (signal?: AbortSignal) =>
    request<Project[]>("/projects", { signal }),
  project: (id: string, signal?: AbortSignal) =>
    request<Project>(projectPath(id), { signal }),
  createProject: (body: ProjectInput) =>
    request<Project>("/projects", json("POST", body)),
  updateProject: (id: string, body: ProjectInput) =>
    request<Project>(projectPath(id), json("PATCH", body)),
  dataset: (id: string, signal?: AbortSignal) =>
    request<Dataset>(projectPath(id) + "/dataset", { signal }),
  configureDataset: (id: string, body: DatasetChange) =>
    request<Dataset>(projectPath(id) + "/dataset", json("PATCH", body)),
  uploadDataset: (id: string, file: File, currentId: string | null) => {
    const body = new FormData();
    body.set("file", file);
    if (currentId) body.set("expected_dataset_id", currentId);
    return request<Dataset>(projectPath(id) + "/dataset", {
      method: "POST",
      body,
    });
  },
};
