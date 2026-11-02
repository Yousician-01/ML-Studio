"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useSyncExternalStore, useCallback, type CSSProperties } from "react";
import { api, type Project, type Dataset } from "@/lib/api/projects";
import { confirmTrainLeave } from "@/lib/train-drafts";
import { taskLabel } from "@/lib/api/task-policy";
import { ProjectForm } from "./project-form";
import { DataView } from "./data-view";
import { Explore } from "./explore";
import { Prepare } from "./prepare";
import { Train } from "./train";
import { LiveCodeViewer } from "./live-code-viewer";
import { LivePipelineProvider, useLivePipeline } from "./live-pipeline";
import { viewerPreference, type ViewerPreference } from "@/lib/live-code";
import { CodeModeProvider, useCodeMode } from "./code-mode-state";
import { CodeModeEditor } from "./code-mode-editor";
import { CodeSessions } from "./code-sessions";
import { CodeExecution } from "./code-execution";
import { VisualReentryWarning } from "./code-mode-actions";
import { Evaluate } from "./evaluate";
import { Runs } from "./runs";
import { DeleteProject } from "./delete-project";
import { Alert, Button, Dialog, Loading } from "./ui";
import { AppShell, WorkflowRail } from "./app-shell";
import { Icon } from "./icons";

export function Workspace({ projectId }: { projectId: string }) {
  return <CodeModeProvider key={projectId} projectId={projectId}><LivePipelineProvider><WorkspaceContent projectId={projectId} /></LivePipelineProvider></CodeModeProvider>;
}

function WorkspaceContent({ projectId }: { projectId: string }) {
  const mode = useCodeMode();
  const router = useRouter();
  const search = useSearchParams();
  const view = search.get("view") === "evaluate" ? "evaluate" : search.get("view") === "runs" ? "runs" : search.get("view") === "code" ? "code" : search.get("view") === "train" ? "train" : search.get("view") === "prepare" ? "prepare" : search.get("view") === "explore" ? "explore" : "data";
  const live = useLivePipeline()!;
  const [returnQuery, setReturnQuery] = useState(search.get("return_to") ?? "view=data");
  const returnSearch = new URLSearchParams(returnQuery);
  const returnBench = ["data", "explore", "prepare", "train", "runs", "evaluate"].includes(returnSearch.get("view") ?? "") ? returnSearch.get("view")! : "data";
  const benchSearch = view === "code" ? returnSearch : search;
  const bench = view === "code" ? returnBench : view;
  const fullScreen = view === "code" && Boolean(mode.draft);
  const [returning, setReturning] = useState(false);
  const [memoryPreference, setPreference] = useState<ViewerPreference | null>(null);
  const rawPreference = useSyncExternalStore(useCallback(notify => {
    window.addEventListener("storage", notify);
    return () => window.removeEventListener("storage", notify);
  }, []), useCallback(() => { try { return localStorage.getItem(`mlstudio:code-viewer:${projectId}`); } catch { return null; } }, [projectId]), () => null);
  let storedPreference: ViewerPreference;
  try { storedPreference = viewerPreference(JSON.parse(rawPreference ?? "null")); } catch { storedPreference = viewerPreference(null); }
  const chosenPreference = memoryPreference ?? storedPreference;
  const preference = view === "code" && mode.ready && !mode.draft && chosenPreference.presentation === "closed" ? { ...chosenPreference, presentation: "docked" as const } : chosenPreference;
  function prefer(value: ViewerPreference) {
    setPreference(value);
    try { localStorage.setItem(`mlstudio:code-viewer:${projectId}`, JSON.stringify(value)); } catch { /* session-only UI */ }
    if (view === "code" && !mode.draft && value.presentation === "closed") router.replace(`/projects/${projectId}?view=${returnBench}`);
  }
  const storedPresentation = storedPreference.presentation, storedWidth = storedPreference.width;
  useEffect(() => {
    function show() { setPreference(current => {
      const prior = current ?? { presentation: storedPresentation, width: storedWidth };
      return { ...prior, presentation: prior.presentation === "closed" ? "docked" : prior.presentation };
    }); }
    window.addEventListener("mlstudio:show-code", show); window.addEventListener("mlstudio:show-code-history", show);
    return () => { window.removeEventListener("mlstudio:show-code", show); window.removeEventListener("mlstudio:show-code-history", show); };
  }, [storedPresentation, storedWidth]);
  function editCode() {
    const query = view === "code" ? returnQuery : search.toString();
    setReturnQuery(query);
    const next = new URLSearchParams(query); next.set("view", "code"); next.set("return_to", query);
    router.push(`/projects/${projectId}?${next}`);
  }
  async function returnVisual(action: "discard" | "save_snapshot") {
    if (await mode.exit(action)) {
      setReturning(false); live.refresh();
      window.dispatchEvent(new Event("mlstudio:visual-refresh"));
      router.push(`/projects/${projectId}?${returnQuery || "view=data"}`);
    }
  }
  const [project, setProject] = useState<Project | null>(null);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  function reload() {
    if (!confirmTrainLeave()) return;
    live.refresh();
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
          bench === "data" && current.active_dataset_id
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
  }, [projectId, bench, attempt, view]);
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
    live.refresh();
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
    <AppShell project={project ?? { id: projectId, name: "Project workspace" }} view={view} onNavigate={name => { if (view !== name && !fullScreen) setLoading(true); }} toolbar={<Button title="Show Code" aria-label="Show Code" aria-pressed={preference.presentation !== "closed"} onClick={() => prefer({ ...preference, presentation: preference.presentation === "closed" ? "docked" : "closed" })}><Icon name="code" /><span>Code</span></Button>}>
    <div className={`code-companion-layout ${preference.presentation === "docked" && !fullScreen ? "has-code-dock" : ""}`} style={{ "--live-code-width": `${preference.width}%` } as CSSProperties}>
    <main className="workspace" id={fullScreen ? "visual-main-content" : "main-content"} tabIndex={-1} hidden={fullScreen}>
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
              <Icon name="runs" />Refresh
            </Button>
            <Button onClick={() => { if (confirmTrainLeave()) setSettingsOpen(true); }}>
              <Icon name="settings" />Project settings
            </Button>
          </div>
        )}
      </div>
      <WorkflowRail view={view} hasDataset={Boolean(project?.active_dataset_id)} codeMode={!fullScreen && Boolean(mode.draft)} />
      {mode.error && <Alert>{mode.error}<Button disabled={mode.busy} onClick={() => void mode.reopen()}>Reopen saved Code</Button></Alert>}
      {mode.notice && <Alert tone="info">{mode.notice}</Alert>}
      {mode.recovery && <Alert tone="info">Unsaved text from an earlier Code revision is retained below. It has not been rebased onto the saved draft. Copy it before explicitly discarding this recovery buffer to continue.
        <details><summary>Inspect recovered unsaved Python</summary><pre className="code-source" tabIndex={0}><code>{mode.recovery.source}</code></pre></details>
        <Button onClick={mode.dropRecovery}>Use saved state and discard recovered text</Button>
      </Alert>}

      {mode.draft && !fullScreen && ["data", "prepare", "train"].includes(bench) && <VisualReentryWarning modified={mode.modified} dirty={mode.dirty} busy={mode.busy || Boolean(mode.recovery)} onContinue={editCode} onSnapshot={() => void returnVisual("save_snapshot")} onDiscard={() => void returnVisual("discard")} />}
      <fieldset className="visual-bench-boundary" disabled={Boolean(mode.draft) && ["data", "prepare", "train", "explore"].includes(bench)}>
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
        (!mode.ready ? <Loading>Checking saved Code Mode session…</Loading> : bench === "data" ? (
          <DataView
            key={`${dataset?.id ?? "empty"}:${attempt}`}
            project={project}
            dataset={dataset}
            onSaved={saved}
            onReload={reload}
          />
        ) : bench === "evaluate" ? (
          <Evaluate key={`${project.id}:${attempt}`} projectId={projectId} runId={benchSearch.get("run")} compareId={benchSearch.get("compare")} latest={benchSearch.get("selection") === "latest"} source={benchSearch.get("source")} codeRunId={benchSearch.get("code_run")} codeMode={!fullScreen && Boolean(mode.draft)} />
        ) : bench === "runs" ? (
          <Runs key={`${project.id}:${attempt}`} projectId={projectId} runId={benchSearch.get("run")} />
        ) : bench === "train" ? (
          <Train key={`${project.active_dataset_id}:${attempt}`} projectId={projectId} datasetId={project.active_dataset_id} onReload={reload} />
        ) : bench === "prepare" ? (
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
      </fieldset>
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
    <div className="live-viewer-slot" hidden={fullScreen}><LiveCodeViewer suspended={fullScreen} projectId={projectId} preference={fullScreen ? { ...preference, presentation: "closed" } : preference} onPreference={prefer} onEdit={editCode} /></div>
    </div>
    <section hidden={!fullScreen} id={fullScreen ? "main-content" : undefined} role={fullScreen ? "main" : undefined} tabIndex={-1} className="full-code-workspace" aria-label="Full-screen Code Mode">
      <div className="actions"><Link href="/">Projects</Link><Link href={`/projects/${projectId}?view=evaluate&source=code`}>Evaluate Code Runs</Link></div>
      <CodeModeEditor onReturn={() => setReturning(true)} />
      {fullScreen && <><CodeExecution projectId={projectId} /><CodeSessions projectId={projectId} /></>}
    </section>
    {returning && <Dialog title="Return to Visual Mode" busy={mode.busy} onClose={() => setReturning(false)}>
      <p>{mode.dirty ? "Unsaved Python edits are present. " : ""}Save a snapshot to preserve this draft for later continuation. The visual pipeline and all recorded Runs stay unchanged.</p>
      <Button disabled={mode.busy || Boolean(mode.recovery)} onClick={() => void returnVisual("save_snapshot")}>Save snapshot and return to Visual Mode</Button>
      <Button variant="danger" disabled={mode.busy || Boolean(mode.recovery)} onClick={() => void returnVisual("discard")}>Discard manual changes and return</Button>
      <Button disabled={mode.busy} onClick={() => setReturning(false)}>Continue editing code</Button>
      {mode.error && <Alert>{mode.error}</Alert>}
    </Dialog>}
    </AppShell>
  );
}
