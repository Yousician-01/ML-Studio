import type { RunRequest, RunState } from "./runs";

export function active(state: RunState) { return state === "CREATED" || state === "RUNNING"; }
export function canRun(input: { ready: boolean; dirty: boolean; conflict: boolean; busy: boolean; occupied: boolean; reviewed: boolean }) {
  return input.ready && input.reviewed && !input.dirty && !input.conflict && !input.busy && !input.occupied;
}
export function requestFor(preview: { revision: number; source_sha256: string | null; plan_sha256: string | null }, requestId: string): RunRequest {
  if (!preview.source_sha256 || !preview.plan_sha256) throw new Error("Review executable Code before submitting.");
  return { request_id: requestId, expected_revision: preview.revision, expected_source_sha256: preview.source_sha256, expected_plan_sha256: preview.plan_sha256 };
}
export function restoredRequest(value: string | null): RunRequest | null {
  if (!value) return null;
  try {
    const candidate = JSON.parse(value);
    if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(candidate.request_id) && Number.isSafeInteger(candidate.expected_revision) && candidate.expected_revision > 0 &&
      /^sha256:[0-9a-f]{64}$/.test(candidate.expected_source_sha256) && /^sha256:[0-9a-f]{64}$/.test(candidate.expected_plan_sha256)) return candidate;
  } catch { /* Stored transport identity is never authoritative experiment state. */ }
  return null;
}
