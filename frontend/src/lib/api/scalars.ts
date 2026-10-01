import type { Scalar } from "./projects";

export function displayScalar(value: Scalar, quoteStrings = false): string {
  if (value === null) return "—";
  if (typeof value === "object") return value.value;
  if (quoteStrings && typeof value === "string") return JSON.stringify(value);
  return String(value);
}
