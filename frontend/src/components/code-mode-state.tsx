"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "@/lib/api/projects";
import type { CodePreview } from "@/lib/api/code";
import { sourceState, type CodeDraft } from "@/lib/api/code-drafts";
import { codeRunActive, type CodeRun } from "@/lib/api/code-runs";
import { clearCodeBuffer, readCodeBuffer, resolveCodeBuffer, writeCodeBuffer, type CodeBuffer } from "@/lib/code-draft-buffer";

type Mode = {
  draft: CodeDraft | null; source: string; dirty: boolean; modified: boolean;
  ready: boolean; busy: boolean; error: string; notice: string;
  recovery: CodeBuffer | null; dropRecovery: () => void;
  codeRun: CodeRun | null; setCodeRun: (run: CodeRun | null) => void;
  executionEnabled: boolean; setExecutionEnabled: (enabled: boolean) => void;
  runCode: () => Promise<void>;
  edit: (source: string) => void; reopen: () => Promise<void>;
  enter: (preview: CodePreview) => Promise<boolean>;
  save: (snapshot?: boolean) => Promise<boolean>;
  exit: (action: "discard" | "save_snapshot") => Promise<boolean>;
};
const Context = createContext<Mode | null>(null);
export function useCodeMode() {
  const value = useContext(Context);
  if (!value) throw new Error("Code Mode requires the Project workspace.");
  return value;
}

export function CodeModeProvider({ projectId, children }: { projectId: string; children: ReactNode }) {
  const [draft, setDraft] = useState<CodeDraft | null>(null);
  const [source, setSource] = useState("");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [recovery, setRecovery] = useState<CodeBuffer | null>(null);
  const [codeRun, setCodeRun] = useState<CodeRun | null>(null);
  const [executionEnabled, setExecutionEnabled] = useState(false);
  const sourceRef = useRef("");
  const lock = useRef(false);
  const mounted = useRef(true);
  const flags = draft ? sourceState(draft, source) : { dirty: false, modified: false };
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    api.activeCodeDraft(projectId, controller.signal).then(next => {
      if (!controller.signal.aborted) {
        const restored = resolveCodeBuffer(readCodeBuffer(projectId), next);
        setDraft(next); setSource(restored.source); sourceRef.current = restored.source;
        setRecovery(restored.conflict); setReady(true);
        if (next && restored.source !== next.source) setNotice("Recovered unsaved Code edits from this tab. Save to persist them to the workspace.");
      }
    }).catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Code session unavailable."); });
    return () => { mounted.current = false; controller.abort(); };
  }, [projectId]);

  useEffect(() => {
    function unload(event: BeforeUnloadEvent) {
      if (flags.dirty || busy) { event.preventDefault(); event.returnValue = ""; }
    }
    function leaving(url: URL) {
      if (url.origin === window.location.origin && url.pathname === `/projects/${projectId}`) return true;
      if (busy) return false;
      return !flags.dirty || window.confirm("Leave Code with unsaved changes? Save the draft first to preserve these edits. Your last saved draft remains available. Choose Cancel to continue editing.");
    }
    function click(event: MouseEvent) {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const anchor = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (anchor && !leaving(new URL(anchor.getAttribute("href")!, window.location.href))) { event.preventDefault(); event.stopImmediatePropagation(); }
    }
    function traverse(event: Event) {
      const next = event as Event & { destination?: { url: string }; navigationType?: string };
      if (next.navigationType === "traverse" && next.destination && event.cancelable && !leaving(new URL(next.destination.url))) event.preventDefault();
    }
    const navigation = (window as Window & { navigation?: EventTarget }).navigation;
    window.addEventListener("beforeunload", unload); document.addEventListener("click", click, true); navigation?.addEventListener("navigate", traverse);
    return () => { window.removeEventListener("beforeunload", unload); document.removeEventListener("click", click, true); navigation?.removeEventListener("navigate", traverse); };
  }, [flags.dirty, busy, projectId]);

  async function mutate(action: () => Promise<void>) {
    if (lock.current) return false;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    try { await action(); return true; }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Code save failed. Keep a copy of unsaved text."); return false; }
    finally { lock.current = false; setBusy(false); }
  }
  async function reopen() {
    if ((flags.dirty || error || recovery) && !window.confirm("Reopen saved Code? Unsaved editor and recovered text will be replaced. Copy it before continuing.")) return;
    await mutate(async () => { const next = await api.activeCodeDraft(projectId); if (!mounted.current) return; clearCodeBuffer(projectId); setRecovery(null); setDraft(next); setSource(next?.source ?? ""); sourceRef.current = next?.source ?? ""; setReady(true); });
  }
  async function enter(preview: CodePreview) {
    if (!ready || draft || recovery || !preview.ready || !preview.source_sha256 || !preview.plan_sha256) return false;
    return mutate(async () => {
      const next = await api.createCodeDraft(projectId, { revision: preview.revision, source_sha256: preview.source_sha256!, plan_sha256: preview.plan_sha256! });
      if (!mounted.current) return;
      setDraft(next); setSource(next.source); sourceRef.current = next.source; setNotice("Code Mode entered. No execution has been created.");
    });
  }
  async function save(snapshot = false) {
    if (!draft || recovery) return false;
    return mutate(async () => {
      let next: CodeDraft;
      if (snapshot) {
        const saved = await api.saveCodeSnapshot(projectId, draft.id, draft.revision, sourceRef.current);
        next = saved.draft; setNotice("Code snapshot saved. This is not a Run or execution.");
      } else { next = await api.saveCodeDraft(projectId, draft.id, draft.revision, sourceRef.current); setNotice("Code draft saved."); }
      if (!mounted.current) return;
      setDraft(next);
      if (sourceRef.current === next.source) clearCodeBuffer(projectId);
      else writeCodeBuffer(projectId, { draftId: next.id, revision: next.revision, source: sourceRef.current });
    });
  }
  async function exit(action: "discard" | "save_snapshot") {
    if (!draft || recovery) return false;
    return mutate(async () => {
      const submitted = sourceRef.current;
      await api.exitCodeDraft(projectId, draft.id, draft.revision, action, submitted);
      if (!mounted.current) return;
      if (action === "save_snapshot" && sourceRef.current !== submitted) setRecovery(readCodeBuffer(projectId));
      else clearCodeBuffer(projectId);
      setDraft(null); setSource(""); sourceRef.current = "";
      setNotice(action === "save_snapshot" ? "Code snapshot saved. Visual editing restored; no execution recorded." : "Manual changes discarded. Original visual configuration restored.");
    });
  }
  function edit(next: string) {
    if (!draft || recovery) return;
    setSource(next); sourceRef.current = next;
    if (!writeCodeBuffer(projectId, { draftId: draft.id, revision: draft.revision, source: next })) setNotice("Unsaved edits are retained in memory only. Save the draft before refreshing or closing this tab.");
  }
  function dropRecovery() { clearCodeBuffer(projectId); setRecovery(null); }
  async function runCode() {
    if (!draft || recovery || !executionEnabled || codeRunActive(codeRun)) return;
    await mutate(async () => {
      const started = await api.createCodeRun(projectId, { draft_id: draft.id, revision: draft.revision, source: sourceRef.current, request_id: crypto.randomUUID() });
      if (!mounted.current) return;
      setCodeRun(started);
      if (!started.draft) throw new Error("The Run was recorded, but the draft changed. Keep unsaved text and reopen saved Code.");
      setDraft(started.draft);
      if (sourceRef.current === started.draft.source) clearCodeBuffer(projectId);
      else writeCodeBuffer(projectId, { draftId: draft.id, revision: started.draft.revision, source: sourceRef.current });
      setNotice("Code Run recorded. Output stays in Code Mode; future edits do not change this execution.");
    });
  }
  return <Context.Provider value={{ draft, source, ...flags, ready, busy, error, notice, recovery, dropRecovery, edit, reopen, enter, save, exit, codeRun, setCodeRun, executionEnabled, setExecutionEnabled, runCode }}>{children}</Context.Provider>;
}
