"use client";

import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/editor/editor.api.js";
import "monaco-editor/editor/browser/coreCommands.js";
import "monaco-editor/languages/definitions/python/register.js";
import { useEffect, useRef } from "react";

// Version-pinned npm assets copied by prepare-editor.mjs. Never fetch a CDN.
loader.config({ monaco });
self.MonacoEnvironment = {
  getWorker: () => new Worker("/monaco/assets/editor.worker.js", { type: "module" }),
};

export default function PythonEditor({ value, readOnly, onChange, height = "65vh" }: { value: string; readOnly: boolean; onChange: (value: string) => void; height?: string }) {
  const editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const old = useRef(value);
  useEffect(() => {
    const instance = editor.current;
    if (!instance || !readOnly || old.current === value) { old.current = value; return; }
    const before = old.current.split("\n"), after = value.split("\n");
    old.current = value;
    // Bounded positional decorations; no expensive full-source diff or scroll jump.
    const collection = instance.createDecorationsCollection(after.flatMap((line, i) => line !== before[i] && i < 10000 ? [{ range: new monaco.Range(i + 1, 1, i + 1, 1), options: { isWholeLine: true, className: "live-code-changed" } }] : []));
    const timer = setTimeout(() => collection.clear(), 1800);
    return () => { clearTimeout(timer); collection.clear(); };
  }, [value, readOnly]);
  return <Editor height={height} language="python" value={value}
    onMount={instance => { editor.current = instance; }}
    loading={<p role="status">Loading local Python editor…</p>}
    onChange={next => onChange(next ?? "")}
    options={{ readOnly, domReadOnly: readOnly, dragAndDrop: !readOnly, automaticLayout: true, lineNumbers: "on", minimap: { enabled: false }, fontSize: 13, lineHeight: 23, padding: { top: 16, bottom: 16 }, fontFamily: "Cascadia Code, Consolas, monospace", scrollBeyondLastLine: false, ariaLabel: readOnly ? "Read-only generated Python" : "Editable Python source", tabSize: 4 }} />;
}
