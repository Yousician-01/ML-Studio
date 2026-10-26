"use client";
import { useEffect } from "react";
import { canLeaveDraft, registerTrainGuard, readDraft } from "@/lib/train-drafts";

export function TrainDraftGuard({ dirty, saving, projectId }: { projectId: string; dirty: boolean; saving: boolean }) {
  useEffect(() => {
    const leave = () => canLeaveDraft(dirty && Boolean(readDraft(projectId)), saving, () => window.confirm("Leave Train with unsaved edits? Your draft will be retained in this tab. Choose Cancel to keep editing."));
    const unregister = registerTrainGuard(leave);
    function unload(event: BeforeUnloadEvent) {
      if (dirty || saving) { event.preventDefault(); event.returnValue = ""; }
    }
    function click(event: MouseEvent) {
      const anchor = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!anchor || event.defaultPrevented || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("#")) return;
      const url = new URL(href, window.location.href);
      if (url.href === window.location.href) return;
      if (!leave()) { event.preventDefault(); event.stopImmediatePropagation(); }
    }
    // Browser traverse cancellation is platform-dependent. Draft retention also
    // protects input when the browser does not expose a cancelable navigation.
    function traverse(event: Event) {
      if ((event as Event & { navigationType?: string }).navigationType === "traverse" && event.cancelable && !leave()) event.preventDefault();
    }
    const navigation = (window as Window & { navigation?: EventTarget }).navigation;
    document.addEventListener("click", click, true);
    window.addEventListener("beforeunload", unload);
    navigation?.addEventListener("navigate", traverse);
    return () => { unregister(); document.removeEventListener("click", click, true); window.removeEventListener("beforeunload", unload); navigation?.removeEventListener("navigate", traverse); };
  }, [dirty, saving, projectId]);
  return null;
}
