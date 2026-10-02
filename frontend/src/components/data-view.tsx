"use client";

import { useState } from "react";
import {
  api,
  semanticTypes,
  type Dataset,
  type DatasetChange,
  type Project,
  type SemanticType,
} from "@/lib/api/projects";
import { displayScalar } from "@/lib/api/scalars";
import { Alert, Button, EmptyState, Loading, Panel, Stats } from "./ui";

export function DataView({
  project,
  dataset,
  onSaved,
  onReload,
}: {
  project: Project;
  dataset: Dataset | null;
  onSaved: (dataset: Dataset) => void;
  onReload: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [uploadKey, setUploadKey] = useState(0);
  const [errors, setErrors] = useState<Record<string, string>>(
    Object.create(null),
  );
  const [notice, setNotice] = useState("");
  const [candidate, setCandidate] = useState(dataset?.target_column ?? "");
  function errorAt(key: string) {
    return errors[key] ? (
      <Alert id={`error-${key}`}>
        {errors[key]}{" "}
        <Button disabled={busy} onClick={onReload}>
          Reload source
        </Button>
      </Alert>
    ) : null;
  }
  async function save(
    change: Omit<DatasetChange, "dataset_id" | "revision">,
    key: string,
  ) {
    if (!dataset) return;
    setBusy(true);
    setErrors((value) => ({ ...value, [key]: "" }));
    setNotice("");
    try {
      onSaved(
        await api.configureDataset(project.id, {
          ...change,
          dataset_id: dataset.id,
          revision: dataset.revision,
        }),
      );
      setNotice("Configuration saved.");
    } catch (error) {
      setErrors((value) => ({
        ...value,
        [key]: error instanceof Error ? error.message : "Could not save.",
      }));
    } finally {
      setBusy(false);
    }
  }
  async function upload() {
    if (!file) return;
    setBusy(true);
    setErrors((value) => ({ ...value, upload: "" }));
    setNotice("");
    try {
      const source = await api.uploadDataset(
        project.id,
        file,
        dataset?.id ?? project.active_dataset_id,
      );
      onSaved(source);
      setCandidate("");
      setFile(null);
      setConfirmed(false);
      setUploadKey((v) => v + 1);
      setNotice("Source uploaded. Review its columns and select a target.");
    } catch (error) {
      setErrors((value) => ({
        ...value,
        upload: error instanceof Error ? error.message : "Upload failed.",
      }));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="data-view">
      <div className="section-heading">
        <div>
          <h2>Data</h2>
          <p className="muted">
            Original source and column interpretation. Changes save immediately.
          </p>
        </div>
        {notice && (
          <span className="save-status" role="status">
            {notice}
          </span>
        )}
      </div>
      {!dataset && (
        <EmptyState title="No Dataset attached">
          <p>Upload one UTF-8 CSV with a header and at least one data row.</p>
        </EmptyState>
      )}
      <Panel
        title={dataset ? "Source Dataset" : "Upload CSV"}
        description={dataset?.original_filename}
      >
        {dataset && (
          <>
            <Stats
              values={[
                { label: "Rows", value: dataset.row_count.toLocaleString() },
                { label: "Columns", value: dataset.column_count },
                {
                  label: "Missing cells",
                  value: dataset.missing_cells.toLocaleString(),
                },
                {
                  label: "Duplicate rows",
                  value: dataset.duplicate_rows.toLocaleString(),
                },
              ]}
            />
            <details>
              <summary>Source identity</summary>
              <p className="mono wrap">{dataset.fingerprint}</p>
              <p className="muted">
                {dataset.size_bytes.toLocaleString()} bytes ·{" "}
                {new Date(dataset.created_at).toLocaleString()}
              </p>
            </details>
          </>
        )}
        <details className="upload-details" open={!dataset}>
          <summary>
            {dataset ? "Replace source Dataset" : "Choose a CSV file"}
          </summary>
          {dataset && (
            <p className="muted">
              Replacement creates a new Dataset and resets target and semantic
              overrides. Previous managed sources are retained.
            </p>
          )}
          <fieldset disabled={busy}>
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
            {file && <p className="muted wrap">Selected: {file.name}</p>}
            {dataset && (
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                Replace the active Dataset and reset its configuration
              </label>
            )}
            {errorAt("upload")}
            <Button
              variant="primary"
              disabled={!file || busy || Boolean(dataset && !confirmed)}
              onClick={upload}
            >
              {busy ? "Working…" : dataset ? "Replace Dataset" : "Upload CSV"}
            </Button>
          </fieldset>
        </details>
      </Panel>
      {dataset && (
        <>
          <Panel
            title="Target variable"
            description="Choose the outcome you want to predict. All columns remain visible for inspection."
          >
            <div className="target-layout">
              <div>
                <label htmlFor="target-column">Target column</label>
                <select
                  id="target-column"
                  disabled={busy}
                  value={candidate}
                  aria-invalid={Boolean(errors.target)}
                  aria-describedby="target-help target-feedback"
                  onChange={(event) => {
                    setCandidate(event.target.value);
                    void save(
                      { target_column: event.target.value || null },
                      "target",
                    );
                  }}
                >
                  <option value="">No target selected</option>
                  {dataset.columns.map((column) => (
                    <option key={column.name} value={column.name}>
                      {column.name} · {column.effective_semantic_type} ·{" "}
                      {column.unique_count} distinct values
                      {column.unique_count === 2
                        ? " · binary candidate"
                        : " · not a binary target"}
                    </option>
                  ))}
                </select>
                <p id="target-help" className="muted">
                  Binary classification requires exactly two distinct
                  non-missing values. Missing values do not create a class.
                </p>
                <div id="target-feedback">
                  {errors.target && (
                    <Alert>
                      <strong>
                        {candidate || "Target"} could not be saved.
                      </strong>
                      <p>{errors.target}</p>
                      <Button disabled={busy} onClick={onReload}>
                        Reload source
                      </Button>
                    </Alert>
                  )}
                </div>
              </div>
              <div className="target-status">
                <span className="eyebrow">Saved target</span>
                <strong>{dataset.target_column ?? "Not selected"}</strong>
                {dataset.target_classes.length > 0 && (
                  <div className="class-labels">
                    {dataset.target_classes.map((value, i) => (
                      <code className="class-value" key={i}>
                        {displayScalar(value, true)}
                      </code>
                    ))}
                  </div>
                )}
                <p className="muted">
                  Choose the positive class in Prepare. Missing target rows are
                  eligible for exclusion during execution.
                </p>
              </div>
            </div>
            <p className="muted">
              Former targets remain excluded until explicitly enabled in Prepare.
            </p>
          </Panel>
          <Panel
            title="Columns"
            description="Physical dtype describes parsing. Effective semantic type reflects your override, if present."
          >
            <p className="muted">Semantic edits preserve source values and target classes. Existing preparation choices stay saved and are revalidated in Prepare.</p>
            {dataset.columns.some(column => column.inference_version !== "semantic-v2") && (
              <Alert tone="info">
                This Dataset uses earlier detection rules. Refresh detected types to apply improved identifier recognition. Manual overrides and preparation choices remain saved; compatibility may change.
                <Button disabled={busy} onClick={() => void save({ refresh_inference: true }, "inference")}>Refresh detected types</Button>
                {errorAt("inference")}
              </Alert>
            )}
            {busy && <Loading>Saving…</Loading>}
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
                      "Semantic override",
                      "Effective",
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
                      <td className="mono">{column.physical_dtype}</td>
                      <td>{column.missing_count.toLocaleString()}<small className="semantic-note">{(100 * column.missing_count / dataset.row_count).toFixed(1)}%</small></td>
                      <td>{column.unique_count}</td>
                      <td>{column.inferred_semantic_type}</td>
                      <td>
                        <select
                          aria-label={`Semantic type for ${column.name}`}
                          aria-invalid={Boolean(
                            errors[`column-${column.source_order}`],
                          )}
                          disabled={busy}
                          value={column.semantic_override ?? ""}
                          onChange={(event) =>
                            void save(
                              {
                                semantic_overrides: {
                                  [column.name]: (event.target.value ||
                                    null) as SemanticType | null,
                                },
                              },
                              `column-${column.source_order}`,
                            )
                          }
                        >
                          <option value="">Use detected ({column.inferred_semantic_type})</option>
                          {semanticTypes.map((type) => (
                            <option key={type} value={type}>
                              {type}
                            </option>
                          ))}
                        </select>
                        {column.semantic_override !== null ? (
                          <div className="semantic-override">
                            <span className="badge accent">Manual override</span>
                            <Button disabled={busy} aria-label={`Reset ${column.name} to detected type`} onClick={() => void save({ semantic_overrides: { [column.name]: null } }, `column-${column.source_order}`)}>Reset to detected type</Button>
                          </div>
                        ) : <small className="semantic-note">Using detected type</small>}
                        {errorAt(`column-${column.source_order}`)}
                      </td>
                      <td>{column.effective_semantic_type}</td>
                      <td>
                        <span
                          className={`badge ${column.role === "target" ? "accent" : "subtle"}`}
                        >
                          {column.role}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel
            title="Source preview"
            description={`First ${Math.min(dataset.row_count, dataset.preview_limit)} parsed source rows. No transformations applied. — denotes a missing value.`}
          >
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    {dataset.columns.map((column) => (
                      <th key={column.name}>{column.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {dataset.preview.map((row, index) => (
                    <tr key={index}>
                      {row.map((value, col) => (
                        <td key={col}>{displayScalar(value)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
