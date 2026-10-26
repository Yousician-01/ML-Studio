// Unsaved editor input only. Saved Project/Pipeline state remains backend-owned.
export type TrainDraft = { revision: number; section: "model" | "split"; values: Record<string, string> };
const drafts = new Map<string, TrainDraft>();
const key = (id: string) => `mlstudio:train-draft:${id}`;
export function readDraft(id: string): TrainDraft | null {
  if (drafts.has(id)) return drafts.get(id)!;
  try {
    const raw = sessionStorage.getItem(key(id));
    const draft = raw ? JSON.parse(raw) : null;
    if (draft && Number.isSafeInteger(draft.revision) && ["model", "split"].includes(draft.section) && draft.values && Object.values(draft.values).every(v => typeof v === "string")) {
      drafts.set(id, draft); return draft;
    }
  } catch { /* Memory drafts and unload protection still work if storage is disabled. */ }
  return null;
}
export function writeDraft(id: string, draft: TrainDraft) {
  drafts.set(id, draft);
  try { sessionStorage.setItem(key(id), JSON.stringify(draft)); } catch { /* Not authoritative. */ }
}
export function clearDraft(id: string) {
  drafts.delete(id);
  try { sessionStorage.removeItem(key(id)); } catch { /* Not authoritative. */ }
}
export function canLeaveDraft(dirty: boolean, saving: boolean, confirm: () => boolean) {
  return !saving && (!dirty || confirm());
}
let guard: (() => boolean) | null = null;
export const confirmTrainLeave = () => !guard || guard();
export function registerTrainGuard(next: () => boolean) {
  guard = next;
  return () => { if (guard === next) guard = null; };
}
