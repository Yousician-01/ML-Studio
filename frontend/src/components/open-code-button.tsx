"use client";
import type { ReactNode } from "react";
import { Button } from "./ui";
export function OpenCodeButton({ history = false, children }: { history?: boolean; children: ReactNode }) {
  return <Button onClick={() => window.dispatchEvent(new Event(history ? "mlstudio:show-code-history" : "mlstudio:show-code"))}>{children}</Button>;
}
