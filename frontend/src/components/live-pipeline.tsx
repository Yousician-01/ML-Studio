"use client";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import type { PipelineIR } from "@/lib/api/pipelines";
export type PreviewInput = { revision: number; ir: PipelineIR } | null | undefined;
const Context = createContext<{ input: PreviewInput; epoch: number; publish: (input: PreviewInput) => void; refresh: () => void; revalidate: () => void } | null>(null);
export function LivePipelineProvider({ children }: { children: ReactNode }) {
  const [input, publish] = useState<PreviewInput>(undefined);
  const [epoch, setEpoch] = useState(0);
  const refresh = useCallback(() => { publish(undefined); setEpoch(n => n + 1); }, []);
  const revalidate = useCallback(() => setEpoch(n => n + 1), []);
  return <Context.Provider value={{ input, epoch, publish, refresh, revalidate }}>{children}</Context.Provider>;
}
export function useLivePipeline() { return useContext(Context); }
