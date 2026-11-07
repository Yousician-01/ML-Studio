"use client";

import { useEffect, useRef } from "react";
import type { ColumnAction } from "@/lib/preparation";

export function PreparationMenu({ column, actions, position, onAction, onClose }: {
  column: string; actions: ColumnAction[]; position: { x: number; y: number }; onAction: (action: ColumnAction) => void; onClose: () => void;
}) {
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    menu.current?.querySelector<HTMLButtonElement>("[role=menuitem]")?.focus();
    const outside = (event: PointerEvent) => { if (!menu.current?.contains(event.target as Node)) onClose(); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [onClose]);
  return <div ref={menu} role="menu" aria-label={`Actions for ${column}`} className="studio-context-menu" style={{ left: position.x, top: position.y }} onKeyDown={event => {
    const items = Array.from(menu.current?.querySelectorAll<HTMLButtonElement>("[role=menuitem]") ?? []);
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      items[event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
    }
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onClose(); }
    if (event.key === "Tab") onClose();
  }}><div className="studio-menu-label">{column}</div>{actions.map(action => <button key={action.id} type="button" role="menuitem" onClick={() => onAction(action)}>{action.label}</button>)}</div>;
}
