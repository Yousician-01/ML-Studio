"use client";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState, type PointerEvent } from "react";
import { api } from "@/lib/api/projects";
import type { CodePreview } from "@/lib/api/code";
import type { PipelineIR } from "@/lib/api/pipelines";
import { PreviewRequests, currentPreview, type ViewerPreference } from "@/lib/live-code";
import { useLivePipeline } from "./live-pipeline";
import { useCodeMode } from "./code-mode-state";
import { CodeModeConfirmation } from "./code-mode-actions";
import { Alert, Button, Dialog, Loading } from "./ui";
import { Icon } from "./icons";
import { CodeSessions } from "./code-sessions";
import { CodeExecution } from "./code-execution";

const PythonEditor = dynamic(() => import("./python-editor"), { ssr: false });
export function LiveCodeViewer({ projectId, preference, onPreference, onEdit, suspended = false }: {
  projectId: string; preference: ViewerPreference; onPreference: (value: ViewerPreference) => void; onEdit: () => void;
  suspended?: boolean;
}) {
  const live = useLivePipeline()!;
  const mode = useCodeMode();
  const [result, setResult] = useState<{ key: string; value: CodePreview } | null>(null);
  const [error, setError] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [existing, setExisting] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [position, setPosition] = useState({ x: 24, y: 84 });
  const [entry, setEntry] = useState<{ preview: CodePreview; ir?: PipelineIR; key: string } | null>(null);
  const panel = useRef<HTMLElement>(null);
  const requests = useRef(new PreviewRequests());
  const inputKey = JSON.stringify([projectId, live.input, live.epoch]);
  const open = preference.presentation !== "closed";
  const preview = currentPreview(result?.value ?? null, inputKey, result?.key ?? "");
  const matched = result?.key === inputKey ? result.value : null;
  useEffect(() => {
    function history() { setHistoryOpen(true); }
    window.addEventListener("mlstudio:show-code-history", history);
    return () => window.removeEventListener("mlstudio:show-code-history", history);
  }, []);
  useEffect(() => {
    const request = requests.current;
    request.cancel();
    if (!open || live.input === null) return;
    const timer = setTimeout(() => {
      void request.run(async signal => {
        const value = live.input ? await api.previewCode(projectId, live.input.revision, live.input.ir, signal) : await api.code(projectId, signal);
        const project = await api.project(projectId, signal);
        if (value.project_id !== projectId || project.revision !== value.revision || project.active_dataset_id !== value.dataset_id) throw new Error("Project changed during generation. Refresh the workspace.");
        return value;
      }, value => { setError(""); setResult({ key: inputKey, value }); }, caught => { setResult(null); setError(caught instanceof Error ? caught.message : "Preview unavailable."); });
    }, 350);
    return () => { clearTimeout(timer); request.cancel(); };
  }, [inputKey, open, projectId, live.input]);
  useEffect(() => {
    const refresh = live.revalidate;
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [live.revalidate]);
  useEffect(() => {
    function contain() {
      const bounds = panel.current?.getBoundingClientRect();
      setPosition(p => ({ x: Math.max(0, Math.min(p.x, window.innerWidth - Math.min(bounds?.width ?? 480, window.innerWidth))), y: Math.max(0, Math.min(p.y, window.innerHeight - Math.min(bounds?.height ?? 480, window.innerHeight))) }));
    }
    window.addEventListener("resize", contain);
    return () => window.removeEventListener("resize", contain);
  }, []);
  function gesture(event: PointerEvent<HTMLElement>, resize: boolean) {
    if (event.button !== 0) return;
    event.preventDefault();
    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);
    const start = { width: preference.width };
    const x = event.clientX, y = event.clientY, original = { ...position };
    const move = (next: globalThis.PointerEvent) => {
      if (resize) onPreference({ ...preference, width: Math.min(65, Math.max(35, start.width + (x - next.clientX) / window.innerWidth * 100)) });
      else {
        const rect = panel.current!.getBoundingClientRect();
        setPosition({ x: Math.max(0, Math.min(window.innerWidth - rect.width, original.x + next.clientX - x)), y: Math.max(0, Math.min(window.innerHeight - rect.height, original.y + next.clientY - y)) });
      }
    };
    const stop = () => { target.removeEventListener("pointermove", move); target.removeEventListener("pointerup", stop); target.removeEventListener("pointercancel", stop); };
    target.addEventListener("pointermove", move); target.addEventListener("pointerup", stop); target.addEventListener("pointercancel", stop);
  }
  function resizeFloating(horizontal: number, vertical: number) {
    const element = panel.current;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    element.style.width = `${Math.min(window.innerWidth - position.x, Math.max(320, rect.width + horizontal))}px`;
    element.style.height = `${Math.min(window.innerHeight - position.y, Math.max(300, rect.height + vertical))}px`;
  }
  async function edit() {
    if (mode.draft) { onEdit(); return; }
    if (!preview) return;
    setEntry({ preview, ir: live.input?.ir, key: inputKey });
    setChecking(true); setError("");
    try {
      const sessions = await api.codeSessions(projectId);
      setExisting(sessions.find(s => s.status === "archived")?.id ?? null);
      setConfirming(true);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Saved drafts unavailable; no new draft was created."); }
    finally { setChecking(false); }
  }
  function present(presentation: ViewerPreference["presentation"]) {
    if (presentation !== "floating" && panel.current) {
      panel.current.style.removeProperty("width"); panel.current.style.removeProperty("height");
    }
    onPreference({ ...preference, presentation });
  }
  return <aside ref={panel} hidden={!open} className={`live-code-panel live-code-${preference.presentation}`} aria-label="Live Python viewer"
    style={preference.presentation === "floating" ? { left: position.x, top: position.y, maxWidth: `calc(100vw - ${position.x}px)`, maxHeight: `calc(100dvh - ${position.y}px)` } : undefined}>
    <div role="separator" aria-label="Resize code panel" aria-orientation="vertical" aria-valuemin={35} aria-valuemax={65} aria-valuenow={preference.width} tabIndex={0} className="live-code-divider" onPointerDown={event => gesture(event, true)} onKeyDown={event => { if (["ArrowLeft", "ArrowRight"].includes(event.key)) { event.preventDefault(); onPreference({ ...preference, width: Math.min(65, Math.max(35, preference.width + (event.key === "ArrowLeft" ? 2 : -2))) }); } }} />
    <header className="live-code-header">
      <button className="live-code-drag" title="Drag floating panel; arrow keys move it" aria-label="Move floating code viewer" disabled={preference.presentation !== "floating"} onPointerDown={event => gesture(event, false)} onKeyDown={event => { if (!event.key.startsWith("Arrow")) return; event.preventDefault(); const rect = panel.current!.getBoundingClientRect(); setPosition(p => ({ x: Math.max(0, Math.min(window.innerWidth - rect.width, p.x + (event.key === "ArrowRight" ? 20 : event.key === "ArrowLeft" ? -20 : 0))), y: Math.max(0, Math.min(window.innerHeight - rect.height, p.y + (event.key === "ArrowDown" ? 20 : event.key === "ArrowUp" ? -20 : 0))) })); }}><Icon name="code" />Live Python</button>
      <div className="actions">{preference.presentation === "floating" && <Button className="live-layout-toggle" aria-label="Resize floating code viewer" title="Use arrow keys to resize the floating viewer" onClick={() => resizeFloating(24, 24)} onKeyDown={event => { if (!event.key.startsWith("Arrow")) return; event.preventDefault(); resizeFloating(event.key === "ArrowRight" ? 24 : event.key === "ArrowLeft" ? -24 : 0, event.key === "ArrowDown" ? 24 : event.key === "ArrowUp" ? -24 : 0); }}><Icon name="prepare" /></Button>}<Button className="live-layout-toggle" onClick={() => present(preference.presentation === "floating" ? "docked" : "floating")}>{preference.presentation === "floating" ? "Dock" : "Float"}</Button><Button title="Close code viewer" aria-label="Close code viewer" onClick={() => present("closed")}><Icon name="close" /></Button></div>
    </header>
    <p className="muted live-code-caption">Current visual pipeline · read-only{live.input ? " · unsaved configuration" : ""}</p>
    <div className="live-code-actions actions"><Button disabled={!preview} onClick={() => { if (preview?.source) void navigator.clipboard.writeText(preview.source).then(() => setCopyStatus("Python copied."), () => setCopyStatus("Clipboard unavailable. Select and copy Python.")); }}>Copy Code</Button><Button variant="primary" disabled={checking || mode.busy || !mode.ready || Boolean(mode.recovery) || (!mode.draft && !preview)} onClick={() => void edit()}>{mode.draft ? "Continue editing code" : "Edit Code"}</Button></div>
    <div role="status" className="live-code-caption">{copyStatus}</div>
    {error ? <Alert>{error}<Button onClick={() => { setError(""); live.revalidate(); }}>Retry preview</Button></Alert> : live.input === null ? <Alert tone="info">Code preview is waiting for a valid pipeline configuration.</Alert> : !matched ? <Loading>Updating generated Python…</Loading> : !matched.ready ? <Alert tone="info">Code preview is waiting for a valid pipeline configuration.<ul>{matched.issues.map((issue, index) => <li key={index}>{issue.message}</li>)}</ul></Alert> : null}
    <div className="live-code-editor" hidden={!preview}><PythonEditor value={result?.value.source ?? ""} readOnly onChange={() => {}} height="100%" /></div>
    <details className="live-code-history" open={historyOpen} onToggle={event => setHistoryOpen(event.currentTarget.open)}><summary>Saved Code and execution history</summary>{historyOpen && !suspended && <><CodeExecution projectId={projectId} /><CodeSessions projectId={projectId} onResume={mode.draft ? undefined : id => { void mode.resume(id).then(ok => { if (ok) onEdit(); }); }} /></>}</details>
    {confirming && (existing ? <Dialog title="Preserve existing Code draft" busy={mode.busy} onClose={() => setConfirming(false)}><p>A saved draft may contain independent Python. Starting fresh will retain that draft and its snapshots. Manual Python never changes the visual pipeline.</p><Button disabled={mode.busy} onClick={() => { void mode.resume(existing).then(ok => { if (ok) { setConfirming(false); onEdit(); } }); }}>Continue editing the existing draft</Button><Button disabled={mode.busy || !entry || entry.key !== inputKey} onClick={() => { if (entry && entry.key === inputKey) void mode.enter(entry.preview, entry.ir).then(ok => { if (ok) { setConfirming(false); onEdit(); } }); }}>Start a new draft from the current visual pipeline</Button><Button disabled={mode.busy} onClick={() => setConfirming(false)}>Cancel</Button>{mode.error && <Alert>{mode.error}</Alert>}</Dialog> : <CodeModeConfirmation busy={mode.busy || !entry || entry.key !== inputKey} error={mode.error} onClose={() => setConfirming(false)} onConfirm={() => { if (entry && entry.key === inputKey) void mode.enter(entry.preview, entry.ir).then(ok => { if (ok) { setConfirming(false); onEdit(); } }); }} />)}
  </aside>;
}
