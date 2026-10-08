"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/projects";
import type { CodePreview } from "@/lib/api/code";
import { Alert, Button, Loading, Panel } from "./ui";

export function CodeView({ projectId }: { projectId: string }) {
  const [preview, setPreview] = useState<CodePreview | null>(null);
  const [error, setError] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const [attempt, setAttempt] = useState(0);
  const requestNumber = useRef(0);

  useEffect(() => {
    let controller: AbortController | undefined;
    async function load() {
      controller?.abort();
      controller = new AbortController();
      const current = ++requestNumber.current;
      const signal = controller.signal;
      setPreview(null);
      setError("");
      setCopyStatus("");
      try {
        const next = await api.code(projectId, signal);
        if (signal.aborted || current !== requestNumber.current) return;
        // Verify this response still represents the persisted workspace after generation.
        const project = await api.project(projectId, signal);
        if (signal.aborted || current !== requestNumber.current) return;
        if (next.project_id !== projectId || project.revision !== next.revision ||
            project.active_dataset_id !== next.dataset_id) {
          setError("Project changed during generation. Refresh Code to inspect the current configuration.");
          return;
        }
        setPreview(next);
      } catch (caught) {
        if (!signal.aborted && current === requestNumber.current)
          setError(caught instanceof Error ? caught.message : "Code preview is unavailable.");
      }
    }
    void load();
    function focus() { void load(); }
    window.addEventListener("focus", focus);
    return () => {
      controller?.abort();
      window.removeEventListener("focus", focus);
    };
  }, [projectId, attempt]);

  async function copy() {
    if (!preview?.source) return;
    try {
      await navigator.clipboard.writeText(preview.source);
      setCopyStatus("Copied Python source.");
    } catch {
      setCopyStatus("Clipboard unavailable. Select and copy the source below.");
    }
  }

  return <div className="code-view">
    <Panel title="Code" description="Current Working Pipeline · read-only Python"
      action={<Button onClick={() => { setPreview(null); setAttempt(v => v + 1); }}>Refresh Code</Button>}>
      <p>This is the Python prepared from your saved configuration. Previewing code does not train a model or create a Run.</p>
      {error ? <Alert>{error}</Alert> : !preview ? <Loading>Validating configuration and preparing Python…</Loading> : !preview.ready ?
        <div>
          <Alert tone="info">Code is not ready. Resolve the following prerequisites; no partial executable source has been generated.</Alert>
          <ul className="code-issues">{preview.issues.map((issue, index) => <li key={index}>
            {issue.column && <strong className="wrap">{issue.column}: </strong>}{issue.message}
            {" "}<Link href={`/projects/${projectId}?view=${issue.scope === "train" ? "train" : issue.scope === "feature" || issue.code.startsWith("positive_class") || issue.code === "persisted_ir_invalid" || issue.code === "dataset_stale" ? "prepare" : "data"}`}>Review configuration</Link>
          </li>)}</ul>
        </div> : <>
          <div className="code-toolbar">
            <div><strong>{preview.filename}</strong><span className="muted"> · {preview.generator} · revision {preview.revision}</span></div>
            <Button onClick={copy}>Copy code</Button>
          </div>
          <p role="status" className="muted">{copyStatus || "Current preview. Create an immutable Run from Train to execute this saved experiment."}</p>
          {preview.issues.length > 0 && <Alert tone="info">Excluded features retain dormant configuration warnings in Prepare. They do not enter this workload.</Alert>}
          <details className="code-assumptions">
            <summary>Source and runtime assumptions</summary>
            <p>UTF-8 CSV, original missing-value interpretation, exact SHA-256 source bytes, and the resolved Python/library versions. Only missing-target rows are excluded. Preprocessing learns from training rows only.</p>
            <p>The executor supplies absolute <code>--dataset</code>, <code>--result</code>, and <code>--model</code> paths. Outputs are a structured result and the complete fitted pipeline. This preview creates neither.</p>
            <p className="wrap">{Object.entries(preview.libraries).map(([name, version]) => `${name} ${version}`).join(" · ")}</p>
            <p className="wrap">Source fingerprint: <code>{preview.source_sha256}</code></p>
          </details>
          <pre className="code-source" tabIndex={0} aria-label="Read-only generated Python"><code>{preview.source?.trimEnd().split("\n").map((line, index) =>
            <span className="code-line" key={index}><span className="code-line-number" aria-hidden="true">{index + 1}</span><span className={line.trimStart().startsWith("#") ? "code-comment" : undefined}>{line || " "}</span>{"\n"}</span>
          )}</code></pre>
        </>}
    </Panel>
  </div>;
}
