"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  api,
  type Project,
  type Dataset,
  type DatasetChange,
  semanticTypes,
  type SemanticType,
} from "@/lib/api/projects";
import { ProjectForm } from "@/components/project-form";
import { displayScalar } from "@/lib/api/scalars";

export function Workspace({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [uploadKey, setUploadKey] = useState(0);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const current = await api.project(projectId, controller.signal);
        if (controller.signal.aborted) return;
        setProject(current);
        const source = current.active_dataset_id
          ? await api.dataset(projectId, controller.signal)
          : null;
        if (!controller.signal.aborted) setDataset(source);
      } catch (error) {
        if (!controller.signal.aborted) {
          setDataset(null);
          setError(
            error instanceof Error
              ? error.message
              : "Could not load workspace.",
          );
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [projectId, attempt]);

  async function save(change: Omit<DatasetChange, "dataset_id" | "revision">) {
    if (!dataset || !project) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const updated = await api.configureDataset(projectId, {
        ...change,
        dataset_id: dataset.id,
        revision: dataset.revision,
      });
      setDataset(updated);
      setProject(await api.project(projectId));
      setNotice("Dataset configuration saved.");
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Could not save Dataset configuration.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function upload() {
    if (!file || !project) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const source = await api.uploadDataset(
        projectId,
        file,
        project.active_dataset_id,
      );
      setDataset(source);
      setProject(await api.project(projectId));
      setFile(null);
      setConfirmed(false);
      setUploadKey((value) => value + 1);
      setNotice("CSV ingested. Review the columns and select a target.");
    } catch (error) {
      setError(error instanceof Error ? error.message : "CSV upload failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="workspace">
      <Link href="/">← Projects</Link>
      {project && (
        <>
          <div className="workspace-heading">
            <div>
              <p className="eyebrow">Binary Classification</p>
              <h1>{project.name}</h1>
            </div>
          </div>
          <p className="intro">{project.problem_statement}</p>
          {project.description && (
            <p className="muted">{project.description}</p>
          )}
          <details className="project-details">
            <summary>Project context and settings</summary>
            <ProjectForm
              key={project.id}
              initial={project}
              submitLabel="Save Project"
              onSave={async (input) => {
                setProject(await api.updateProject(projectId, input));
                setNotice("Project saved.");
              }}
            />
          </details>
          <nav className="benches" aria-label="Project workspace">
            <span aria-current="page">Data</span>
            {["Explore", "Prepare", "Train", "Evaluate", "Runs", "Code"].map(
              (name) => (
                <button
                  key={name}
                  disabled
                  title="Upcoming — not implemented in Phase 1"
                >
                  {name}
                  <small>Upcoming</small>
                </button>
              ),
            )}
          </nav>
        </>
      )}
      {error && (
        <div className="error" role="alert">
          <p>{error}</p>
          <button
            disabled={busy}
            onClick={() => {
              setError("");
              setLoading(true);
              setAttempt((v) => v + 1);
            }}
          >
            Reload workspace
          </button>
        </div>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {loading ? (
        <p role="status">Loading Project and Dataset…</p>
      ) : (
        project && (
          <>
            <section className="panel">
              <h2>
                {project.active_dataset_id
                  ? "Replace source Dataset"
                  : "Add your source data"}
              </h2>
              <p className="muted">
                {project.active_dataset_id
                  ? "Replacement creates a new Dataset and resets the current target and semantic overrides. The previous source is retained."
                  : "No Dataset is attached. Upload a UTF-8 CSV with a header and at least one data row."}
              </p>
              <fieldset disabled={busy} className="upload">
                <label>
                  CSV file
                  <input
                    key={uploadKey}
                    type="file"
                    accept=".csv,text/csv"
                    onChange={(event) => {
                      setFile(event.target.files?.[0] ?? null);
                      setConfirmed(false);
                    }}
                  />
                </label>
                {project.active_dataset_id && (
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={confirmed}
                      onChange={(event) => setConfirmed(event.target.checked)}
                    />
                    Replace the active Dataset and reset its configuration
                  </label>
                )}
                <button
                  className="primary"
                  onClick={upload}
                  disabled={
                    !file || Boolean(project.active_dataset_id && !confirmed)
                  }
                >
                  {busy
                    ? "Working…"
                    : project.active_dataset_id
                      ? "Replace Dataset"
                      : "Upload CSV"}
                </button>
              </fieldset>
              {busy && (
                <p role="status">
                  Saving and validating… Please keep this page open.
                </p>
              )}
            </section>
            {dataset && (
              <>
                <section className="panel">
                  <div className="section-heading">
                    <h2>Source Dataset</h2>
                    <span className="badge">{dataset.original_filename}</span>
                  </div>
                  <dl className="facts">
                    <div>
                      <dt>Rows</dt>
                      <dd>{dataset.row_count.toLocaleString()}</dd>
                    </div>
                    <div>
                      <dt>Columns</dt>
                      <dd>{dataset.column_count}</dd>
                    </div>
                    <div>
                      <dt>Missing cells</dt>
                      <dd>{dataset.missing_cells.toLocaleString()}</dd>
                    </div>
                    <div>
                      <dt>Duplicate rows</dt>
                      <dd>{dataset.duplicate_rows.toLocaleString()}</dd>
                    </div>
                  </dl>
                  <details>
                    <summary>Source identity</summary>
                    <p className="fingerprint">{dataset.fingerprint}</p>
                    <p className="muted">
                      {dataset.size_bytes.toLocaleString()} bytes · Uploaded{" "}
                      {new Date(dataset.created_at).toLocaleString()}
                    </p>
                  </details>
                </section>
                <section className="panel">
                  <h2>Prediction target</h2>
                  <p className="muted">
                    Select the outcome described in your problem statement.
                    Exactly two distinct non-missing values are required.
                  </p>
                  <label>
                    Target column
                    <select
                      disabled={busy}
                      value={dataset.target_column ?? ""}
                      onChange={(event) =>
                        void save({ target_column: event.target.value || null })
                      }
                    >
                      <option value="">No target selected</option>
                      {dataset.columns.map((column) => (
                        <option key={column.name} value={column.name}>
                          {column.name} ({column.unique_count} non-missing
                          classes)
                        </option>
                      ))}
                    </select>
                  </label>
                  {dataset.target_column && (
                    <>
                      <p>
                        Observed classes:{" "}
                        {dataset.target_classes.map((value, index) => (
                          <code className="class-value" key={index}>
                            {displayScalar(value, true)}
                          </code>
                        ))}
                      </p>
                      <p className="muted">
                        Missing targets are eligible for exclusion during later
                        execution. Positive-class selection comes with Pipeline
                        configuration.
                      </p>
                    </>
                  )}
                  <p className="muted">
                    After a target change, the former target stays excluded.
                    Feature configuration comes later in Prepare.
                  </p>
                </section>
                <section className="panel">
                  <h2>Columns</h2>
                  <p className="muted">
                    Physical dtype describes parsing; semantic type describes
                    meaning. Overrides save immediately and leave source values
                    unchanged.
                  </p>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          {[
                            "Column",
                            "Physical dtype",
                            "Missing",
                            "Distinct",
                            "Inferred",
                            "Effective",
                            "Override",
                            "Role",
                          ].map((title) => (
                            <th key={title} scope="col">
                              {title}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {dataset.columns.map((column) => (
                          <tr key={column.name}>
                            <th scope="row">{column.name}</th>
                            <td>
                              <code>{column.physical_dtype}</code>
                            </td>
                            <td>{column.missing_count}</td>
                            <td>{column.unique_count}</td>
                            <td>{column.inferred_semantic_type}</td>
                            <td>{column.effective_semantic_type}</td>
                            <td>
                              <select
                                aria-label={`Semantic type for ${column.name}`}
                                disabled={busy}
                                value={column.semantic_override ?? ""}
                                onChange={(event) =>
                                  void save({
                                    semantic_overrides: {
                                      [column.name]: (event.target.value ||
                                        null) as SemanticType | null,
                                    },
                                  })
                                }
                              >
                                <option value="">Use inferred</option>
                                {semanticTypes.map((type) => (
                                  <option key={type} value={type}>
                                    {type}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td>
                              <span className="badge">{column.role}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
                <section className="panel">
                  <h2>Source preview</h2>
                  <p className="muted">
                    First {Math.min(dataset.row_count, dataset.preview_limit)}{" "}
                    source rows, parsed from the original CSV. No training
                    transformations have been applied. — indicates a missing
                    value.
                  </p>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          {dataset.columns.map((column) => (
                            <th key={column.name} scope="col">
                              {column.name}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {dataset.preview.map((row, index) => (
                          <tr key={index}>
                            {row.map((value, column) => (
                              <td key={column}>{displayScalar(value)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              </>
            )}
          </>
        )
      )}
    </main>
  );
}
