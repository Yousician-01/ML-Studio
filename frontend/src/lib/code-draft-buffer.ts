// Unsaved tab recovery only. The backend draft remains authoritative saved state.
import type { CodeDraft } from "./api/code-drafts";
export type CodeBuffer = { draftId: string; revision: number; source: string };
const buffers = new Map<string, CodeBuffer>();
const key = (id: string) => `mlstudio:code-buffer:${id}`;
export function readCodeBuffer(id: string): CodeBuffer | null {
  if (buffers.has(id)) return buffers.get(id)!;
  try {
    const value = JSON.parse(sessionStorage.getItem(key(id)) ?? "null");
    if (value && typeof value.draftId === "string" && Number.isSafeInteger(value.revision) && value.revision > 0 && typeof value.source === "string") { buffers.set(id, value); return value; }
  } catch { /* Storage can be disabled; in-memory SPA recovery still works. */ }
  return null;
}
export function writeCodeBuffer(id: string, value: CodeBuffer): boolean {
  buffers.set(id, value);
  try { sessionStorage.setItem(key(id), JSON.stringify(value)); return true; } catch { return false; }
}
export function clearCodeBuffer(id: string) {
  buffers.delete(id);
  try { sessionStorage.removeItem(key(id)); } catch { /* No durable browser storage. */ }
}
export function resolveCodeBuffer(buffer: CodeBuffer | null, draft: Pick<CodeDraft, "id" | "revision" | "source"> | null) {
  if (buffer && draft && buffer.draftId === draft.id && buffer.revision === draft.revision) return { source: buffer.source, conflict: null };
  return { source: draft?.source ?? "", conflict: buffer };
}
