"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Project, type Dataset } from "@/lib/api/projects";
import { ProjectForm } from "./project-form";
import { DataView } from "./data-view";
import { Explore } from "./explore";
import { Prepare } from "./prepare";
import { DeleteProject } from "./delete-project";
import { Alert, Button, Dialog, Loading } from "./ui";

export function Workspace({ projectId }: { projectId: string }) {
  const router = useRouter();
  const search = useSearchParams();
  const view = search.get("view") === "prepare" ? "prepare" : search.get("view") === "explore" ? "explore" : "data";
  const [project, setProject] = useState<Project | null>(null);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  function reload() {
    setLoading(true);
    setError("");
    setAttempt((v) => v + 1);
  }
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const current = await api.project(projectId, controller.signal);
        const source =
          view === "data" && current.active_dataset_id
            ? await api.dataset(projectId, controller.signal)
            : null;
        if (!controller.signal.aborted) {
          setProject(current);
          setDataset(source);
          setError("");
          setLoading(false);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setDataset(null);
          setError(
            error instanceof Error ? error.message : "Workspace unavailable.",
          );
          setLoading(false);
        }
      }
    }
    void load();
    return () => controller.abort();
  }, [projectId, view, attempt]);
  useEffect(() => {
    // Revalidate on return from another tab; no polling or background profile computation.
    function focus() {
      // Data may be returning from the native file picker; preserve its selection.
      if (view === "explore" && !settingsOpen && !deleting) {
        setLoading(true);
        setError("");
        setAttempt((v) => v + 1);
      }
    }
    window.addEventListener("focus", focus);
    return () => window.removeEventListener("focus", focus);
  }, [view, settingsOpen, deleting]);
  function saved(source: Dataset) {
    setDataset(source);
    setProject((current) =>
      current
        ? {
            ...current,
            active_dataset_id: source.id,
            target_column: source.target_column,
            revision: source.revision,
          }
        : current,
    );
  }
  return (
    <main className="workspace">
      <div className="breadcrumb">
        <Link href="/">Projects</Link>
        <span aria-hidden="true">/</span>
        <span>{project?.name ?? "Workspace"}</span>
      </div>
      <div className="page-heading">
        <div>
          <div className="eyebrow">Binary classification</div>
          <h1>{project?.name ?? "Project workspace"}</h1>
          <p className="project-problem">{project?.problem_statement}</p>
        </div>
        {project && (
          <div className="actions">
            <Button disabled={loading} onClick={reload}>
              Refresh
            </Button>
            <Button onClick={() => setSettingsOpen(true)}>
              Project settings
            </Button>
          </div>
        )}
      </div>
      <nav className="benches" aria-label="Project workspace">
        {["data", "explore", "prepare"].map((name) => (
          <Link
            key={name}
            href={`/projects/${projectId}?view=${name}`}
            aria-current={view === name ? "page" : undefined}
            onNavigate={() => {
              if (view !== name) setLoading(true);
            }}
          >
            {name === "data" ? "Data" : name === "explore" ? "Explore" : "Prepare"}
          </Link>
        ))}
        {["Train", "Evaluate", "Runs", "Code"].map((name) => (
          <button key={name} disabled>
            {name}
            <span>Upcoming</span>
          </button>
        ))}
      </nav>
      {error ? (
        <Alert>
          {error}
          <Button onClick={reload}>Reload workspace</Button>
          <Link href="/">Return to Projects</Link>
        </Alert>
      ) : loading ? (
        <Loading>Loading current Project and Dataset…</Loading>
      ) : (
        project &&
        (view === "data" ? (
          <DataView
            key={`${dataset?.id ?? "empty"}:${attempt}`}
            project={project}
            dataset={dataset}
            onSaved={saved}
            onReload={reload}
          />
        ) : view === "prepare" ? (
          <Prepare key={`${project.active_dataset_id}:${attempt}`} projectId={projectId} datasetId={project.active_dataset_id} onReload={reload} />
        ) : (
          <Explore
            key={`${project.active_dataset_id}:${project.revision}:${attempt}`}
            projectId={projectId}
            dataset={
              project.active_dataset_id
                ? { id: project.active_dataset_id, revision: project.revision }
                : null
            }
            onReload={reload}
          />
        ))
      )}
      {settingsOpen && project && (
        <Dialog title="Project settings" onClose={() => setSettingsOpen(false)}>
          <ProjectForm
            initial={project}
            submitLabel="Save Project"
            onSave={async (input) => {
              setProject(await api.updateProject(projectId, input));
              setSettingsOpen(false);
              reload();
            }}
          />
          <div className="danger-zone">
            <h3>Delete this Project</h3>
            <p className="muted">
              Permanently delete this Project and all its managed data.
            </p>
            <Button
              variant="danger"
              onClick={() => {
                setSettingsOpen(false);
                setDeleting(true);
              }}
            >
              Delete Project
            </Button>
          </div>
        </Dialog>
      )}
      {deleting && project && (
        <DeleteProject
          project={project}
          onClose={() => setDeleting(false)}
          onDeleted={() => router.push("/")}
        />
      )}
    </main>
  );
}
