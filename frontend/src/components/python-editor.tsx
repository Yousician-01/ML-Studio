"use client";

import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/editor/editor.api.js";
import "monaco-editor/editor/browser/coreCommands.js";
import "monaco-editor/languages/definitions/python/register.js";

// Version-pinned npm assets copied by prepare-editor.mjs. Never fetch a CDN.
loader.config({ monaco });
self.MonacoEnvironment = {
  getWorker: () => new Worker("/monaco/assets/editor.worker.js", { type: "module" }),
};

export default function PythonEditor({ value, readOnly, onChange }: { value: string; readOnly: boolean; onChange: (value: string) => void }) {
  return <Editor height="65vh" language="python" value={value}
    loading={<p role="status">Loading local Python editor…</p>}
    onChange={next => onChange(next ?? "")}
    options={{ readOnly, automaticLayout: true, lineNumbers: "on", minimap: { enabled: false }, fontSize: 14, scrollBeyondLastLine: false, ariaLabel: "Editable Python source", tabSize: 4 }} />;
}
