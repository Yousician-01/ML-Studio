"use client";

import { useState } from "react";
import { api, ApiError, type Project } from "@/lib/api/projects";
import { Alert, Button, Dialog } from "./ui";

export function DeleteProject({
  project,
  onClose,
  onDeleted,
}: {
  project: Project;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [current, setCurrent] = useState(project);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  async function remove() {
    setBusy(true);
    setError("");
    try {
      await api.deleteProject(current.id, current.revision);
      onDeleted();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Deletion failed.");
      setStale(error instanceof ApiError && error.status === 409);
    } finally {
      setBusy(false);
    }
  }
  async function refresh() {
    setBusy(true);
    try {
      setCurrent(await api.project(project.id));
      setStale(false);
      setConfirmed(false);
      setError("");
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Could not refresh Project.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="Delete Project permanently?" onClose={onClose} busy={busy}>
      <p>
        <strong>{current.name}</strong> and all its managed Datasets, including
        replaced sources, will be permanently deleted. This cannot be undone.
      </p>
      <p className="muted">Original files outside ML Studio are unaffected.</p>
      <label className="check-label">
        <input
          type="checkbox"
          checked={confirmed}
          disabled={busy}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        I understand that this Project and its managed data will be permanently
        deleted.
      </label>
      {error && (
        <Alert>
          {error}
          {stale && (
            <Button onClick={refresh} disabled={busy}>
              Reload Project details
            </Button>
          )}
        </Alert>
      )}
      <div className="actions">
        <Button disabled={busy} onClick={onClose}>
          Cancel
        </Button>
        <Button
          variant="danger"
          disabled={!confirmed || busy || stale}
          onClick={remove}
        >
          {busy ? "Deleting…" : "Delete permanently"}
        </Button>
      </div>
    </Dialog>
  );
}
