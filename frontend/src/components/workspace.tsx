"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Project, type Dataset } from "@/lib/api/projects";
import { confirmTrainLeave } from "@/lib/train-drafts";
import { taskLabel } from "@/lib/api/task-policy";
import { ProjectForm } from "./project-form";
import { DataView } from "./data-view";
import { Explore } from "./explore";
import { Prepare } from "./prepare";
import { Train } from "./train";
import { CodeView } from "./code-view";
import { CodeModeProvider, useCodeMode } from "./code-mode-state";
import { CodeModeEditor } from "./code-mode-editor";
import { CodeSessions } from "./code-sessions";
import { CodeExecution } from "./code-execution";
import { VisualReentryWarning } from "./code-mode-actions";
import { Evaluate } from "./evaluate";
import { Runs } from "./runs";
import { DeleteProject } from "./delete-project";
import { Alert, Button, Dialog, Loading } from "./ui";

export function Workspace({ projectId }: { projectId: string }) {
  return <CodeModeProvider key={projectId} projectId={projectId}><WorkspaceContent projectId={projectId} /></CodeModeProvider>;
}

function WorkspaceContent({ projectId }: { projectId: string }) {
  const mode = useCodeMode();
  const router = useRouter();
  const search = useSearchParams();
  const view = search.get("view") === "evaluate" ? "evaluate" : search.get("view") === "runs" ? "runs" : search.get("view") === "code" ? "code" : search.get("view") === "train" ? "train" : search.get("view") === "prepare" ? "prepare" : search.get("view") === "explore" ? "explore" : "data";
  const [project, setProject] = useState<Project | null>(null);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  function reload() {
    if (!confirmTrainLeave()) return;
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
          <div className="eyebrow">{taskLabel(project?.ml_objective)}</div>
          <h1>{project?.name ?? "Project workspace"}</h1>
          <p className="project-problem">{project?.problem_statement}</p>
        </div>
        {project && (
          <div className="actions">
            <Button disabled={loading} onClick={reload}>
              Refresh
            </Button>
            <Button onClick={() => { if (confirmTrainLeave()) setSettingsOpen(true); }}>
              Project settings
            </Button>
          </div>
        )}
      </div>
      <nav className="benches" aria-label="Project workspace">
        {["data", "explore", "prepare", "train"].map((name) => (
          <Link
            key={name}
            href={`/projects/${projectId}?view=${name}`}
            aria-current={view === name ? "page" : undefined}
            onNavigate={() => {
              if (view !== name) setLoading(true);
            }}
          >
            {name === "data" ? "Data" : name === "explore" ? "Explore" : name === "prepare" ? "Prepare" : "Train"}
          </Link>
        ))}
        <Link href={`/projects/${projectId}?view=evaluate`} aria-current={view === "evaluate" ? "page" : undefined} onNavigate={() => { if (view !== "evaluate") setLoading(true); }}>Evaluate</Link>
        <Link href={`/projects/${projectId}?view=runs`} aria-current={view === "runs" ? "page" : undefined} onNavigate={() => { if (view !== "runs") setLoading(true); }}>Runs</Link>
        <Link href={`/projects/${projectId}?view=code`} aria-current={view === "code" ? "page" : undefined}
          onNavigate={() => { if (view !== "code") setLoading(true); }}>Code</Link>
      </nav>
      {mode.error && <Alert>{mode.error}<Button disabled={mode.busy} onClick={() => void mode.reopen()}>Reopen saved Code</Button></Alert>}
      {mode.notice && <Alert tone="info">{mode.notice}</Alert>}
      {mode.recovery && <Alert tone="info">Unsaved text from an earlier Code revision is retained below. It has not been rebased onto the saved draft. Copy it before explicitly discarding this recovery buffer to continue.
        <details><summary>Inspect recovered unsaved Python</summary><pre className="code-source" tabIndex={0}><code>{mode.recovery.source}</code></pre></details>
        <Button onClick={mode.dropRecovery}>Use saved state and discard recovered text</Button>
      </Alert>}
      <div hidden={view !== "code" || loading}><CodeModeEditor /></div>
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
        (!mode.ready ? <Loading>Checking saved Code Mode session…</Loading> : mode.draft && ["data", "prepare", "train"].includes(view) ? (
          <VisualReentryWarning modified={mode.modified} dirty={mode.dirty} busy={mode.busy || Boolean(mode.recovery)}
            onContinue={() => router.push(`/projects/${projectId}?view=code`)}
            onSnapshot={() => { void mode.exit("save_snapshot").then(ok => { if (ok) reload(); }); }}
            onDiscard={() => { void mode.exit("discard").then(ok => { if (ok) reload(); }); }} />
        ) : view === "data" ? (
          <DataView
            key={`${dataset?.id ?? "empty"}:${attempt}`}
            project={project}
            dataset={dataset}
            onSaved={saved}
            onReload={reload}
          />
        ) : view === "evaluate" ? (
          <Evaluate key={`${project.id}:${attempt}`} projectId={projectId} runId={search.get("run")} compareId={search.get("compare")} latest={search.get("selection") === "latest"} />
        ) : view === "runs" ? (
          <Runs key={`${project.id}:${attempt}`} projectId={projectId} runId={search.get("run")} />
        ) : view === "code" ? (
          <>{!mode.draft && <CodeView key={`${project.id}:${attempt}`} projectId={projectId} />}<CodeExecution projectId={projectId} /><CodeSessions key={`${project.id}:${mode.draft?.revision}:${attempt}`} projectId={projectId} /></>
        ) : view === "train" ? (
          <Train key={`${project.active_dataset_id}:${attempt}`} projectId={projectId} datasetId={project.active_dataset_id} onReload={reload} />
        ) : view === "prepare" ? (
          <Prepare key={`${project.active_dataset_id}:${attempt}`} projectId={projectId} datasetId={project.active_dataset_id} onReload={reload} />
        ) : (
          <Explore
            task={project.ml_objective}
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
