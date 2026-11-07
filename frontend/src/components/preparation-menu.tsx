"use client";

import { useEffect, useRef, useState } from "react";
import type { ColumnAction } from "@/lib/preparation";

const missingActions = new Set<ColumnAction["id"]>([
  "impute", "advanced-imputation", "cleaning-missing_filter", "cleaning-keep-missing",
  "cleaning-normalize", "cleaning-replace-missing", "cleaning-datetime_fill",
]);

export function PreparationMenu({ column, actions, position, onAction, onClose }: {
  column: string; actions: ColumnAction[]; position: { x: number; y: number }; onAction: (action: ColumnAction) => void; onClose: () => void;
}) {
  const menu = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const returning = useRef(false);
  const [missingOpen, setMissingOpen] = useState(false);
  const missing = actions.filter(action => missingActions.has(action.id));
  function back() { returning.current = true; setMissingOpen(false); }
  useEffect(() => {
    const outside = (event: PointerEvent) => { if (!menu.current?.contains(event.target as Node)) onClose(); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [onClose]);
  useEffect(() => {
    if (returning.current) { trigger.current?.focus(); returning.current = false; }
    else menu.current?.querySelector<HTMLButtonElement>(missingOpen ? "[data-missing-action]" : "[role=menuitem]")?.focus();
  }, [missingOpen]);
  let grouped = false;
  return <div ref={menu} role="menu" aria-label={missingOpen ? `Missing values for ${column}` : `Actions for ${column}`} className="studio-context-menu" style={{ left: position.x, top: position.y }} onKeyDown={event => {
    if (event.key === "Escape" || event.key === "ArrowLeft" && missingOpen) {
      event.preventDefault(); event.stopPropagation();
      if (missingOpen) back(); else onClose();
      return;
    }
    const items = Array.from(menu.current?.querySelectorAll<HTMLButtonElement>("[role=menuitem]") ?? []);
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      items[event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
    }
    if (event.key === "Tab") onClose();
  }}><div className="studio-menu-label">{missingOpen ? `${column} / Missing values` : column}</div>
    {missingOpen ? <>
      <button type="button" role="menuitem" className="studio-menu-back" onClick={back}>Back to column actions</button>
      {missing.map(action => <button key={action.id} type="button" role="menuitem" data-missing-action onClick={() => onAction(action)}>{action.label}</button>)}
    </> : actions.map(action => {
      if (!missingActions.has(action.id)) return <button key={action.id} type="button" role="menuitem" onClick={() => onAction(action)}>{action.label}</button>;
      if (grouped) return null;
      grouped = true;
      return <button ref={trigger} key="missing-values" type="button" role="menuitem" className="studio-menu-submenu" aria-haspopup="menu" aria-expanded={false} onClick={() => setMissingOpen(true)} onKeyDown={event => {
        if (event.key === "ArrowRight") { event.preventDefault(); event.stopPropagation(); setMissingOpen(true); }
      }}>Handle Missing Values</button>;
    })}
  </div>;
}
