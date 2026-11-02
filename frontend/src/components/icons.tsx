import type { SVGProps } from "react";

const paths = {
  projects: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  data: "M4 6c0-4 16-4 16 0s-16 4-16 0Zm0 0v6c0 4 16 4 16 0V6M4 12v6c0 4 16 4 16 0v-6",
  explore: "m21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0ZM6 10h8M10 6v8",
  prepare: "M4 7h16M4 17h16M8 4v6M16 14v6",
  train: "m9 5 10 7-10 7V5ZM3 5v14",
  evaluate: "M4 20V10M10 20V4M16 20v-8M22 20H2",
  runs: "M3 12a9 9 0 1 0 3-6M3 3v5h5M12 7v5l3 2",
  code: "m8 6-6 6 6 6m8-12 6 6-6 6M14 3l-4 18",
  arrow: "M4 12h16m-6-6 6 6-6 6",
  plus: "M12 5v14M5 12h14",
  upload: "M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5",
  check: "m5 12 4 4L19 6",
  close: "m6 6 12 12M6 18 18 6",
  info: "M12 11v6M12 7h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  warning: "m12 3 10 18H2L12 3ZM12 9v5m0 3h.01",
  settings: "M4 7h16M4 17h16M8 4v6M16 14v6",
  menu: "M4 6h16M4 12h16M4 18h16",
  local: "M3 4h18v13H3zM8 21h8m-4-4v4",
} as const;

export type IconName = keyof typeof paths;
export function Icon({ name, ...props }: SVGProps<SVGSVGElement> & { name: IconName }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...props}><path d={paths[name]} /></svg>;
}
