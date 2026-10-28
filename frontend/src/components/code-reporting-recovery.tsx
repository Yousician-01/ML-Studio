"use client";

import { useState } from "react";
import { api } from "@/lib/api/projects";
import type { ReportingProposal } from "@/lib/api/code-drafts";
import { useCodeMode } from "./code-mode-state";
import { Alert, Button, Dialog } from "./ui";

export function CodeReportingRecovery() {
  const mode = useCodeMode();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [review, setReview] = useState<{ proposal: ReportingProposal; source: string; draftId: string } | null>(null);
  async function prepare() {
    if (!mode.draft) return;
    const source = mode.source, draft = mode.draft;
    setLoading(true); setError("");
    try {
      const proposal = await api.codeReportingProposal(draft.project_id, draft.id, draft.revision, source);
      setReview({ proposal, source, draftId: draft.id });
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Reporting proposal unavailable."); }
    finally { setLoading(false); }
  }
  const unchanged = review && mode.draft?.id === review.draftId && mode.draft?.revision === review.proposal.revision && mode.source === review.source;
  async function apply() {
    if (!unchanged || !review || review.proposal.proposed_source === null || mode.busy || mode.recovery) return;
    // Existing editor buffer and revision-guarded save; baseline/history stay intact.
    mode.edit(review.proposal.proposed_source);
    if (await mode.save()) setReview(null);
  }
  return <>
    <p className="muted">Older drafts may lack evaluation reporting. Review an insertion without replacing your source. <Button disabled={loading || mode.busy || Boolean(mode.recovery)} onClick={() => void prepare()}>{loading ? "Checking reporting…" : "Enable Evaluation Reporting"}</Button></p>
    {error && <Alert>{error}</Alert>}
    {review && <Dialog title="Review evaluation reporting" busy={mode.busy} onClose={() => setReview(null)}>
      <p>{review.proposal.message}</p>
      {review.proposal.status === "ready" ? <><p>This adds reporting after predictions. Your saved baseline, visual recipe and previous Runs remain unchanged. Applying also saves the current editor text.</p><pre className="code-source" tabIndex={0} aria-label="Proposed reporting changes">{review.proposal.diff}</pre>{!unchanged && <Alert>The draft or editor changed since this proposal. Close and review a new proposal before applying.</Alert>}<div className="actions"><Button disabled={mode.busy} onClick={() => setReview(null)}>Cancel</Button><Button variant="primary" disabled={!unchanged || mode.busy || Boolean(mode.recovery)} onClick={() => void apply()}>Apply and save reporting</Button></div>{mode.error && <Alert>{mode.error}</Alert>}</> : <><p>For manual integration, place the appropriate call after generating predictions for the held-out data. Use your own variables; classification labels are negative then positive.</p><pre className="code-source" tabIndex={0}>{review.proposal.example}</pre><p>No source has been changed.</p></>}
    </Dialog>}
  </>;
}
