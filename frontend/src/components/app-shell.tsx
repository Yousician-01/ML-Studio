"use client";

import Link from "next/link";
import { useRef, useState, type ReactNode } from "react";
import { Icon, type IconName } from "./icons";

const workflow = [
  { view: "data", label: "Data", hint: "Source & target" },
  { view: "explore", label: "Explore", hint: "Understand the source" },
  { view: "prepare", label: "Prepare", hint: "Shape your features" },
  { view: "train", label: "Train", hint: "Configure & execute" },
] as const;

export function AppShell({ project, view = "projects", onNavigate, children }: {
  project?: { id: string; name: string } | null; view?: string;
  onNavigate?: (view: string) => void; children: ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  function close() { setExpanded(false); toggle.current?.focus(); }
  function item(name: string, label: string, icon: IconName, hint?: string) {
    return <Link key={name} href={name === "projects" ? "/" : `/projects/${project!.id}?view=${name}`} aria-current={view === name ? "page" : undefined} onNavigate={() => { setExpanded(false); onNavigate?.(name); }}>
      <Icon name={icon} /><span>{label}{hint && <small>{hint}</small>}</span>{view === name && <span className="nav-current-dot" aria-hidden="true" />}
    </Link>;
  }
  const title = workflow.find(item => item.view === view)?.label ?? ({ projects: "Projects", runs: "Runs", evaluate: "Evaluate", code: "Code" } as Record<string, string>)[view] ?? "Workspace";
  return <div className="app-shell" onKeyDown={event => { if (event.key === "Escape" && expanded) close(); }}>
    <a className="skip-link" href="#main-content">Skip to workspace</a>
    <header className="app-topbar">
      <button ref={toggle} className="mobile-navigation" aria-label="Toggle workspace navigation" aria-expanded={expanded} aria-controls="app-navigation" onClick={() => setExpanded(value => !value)}><Icon name={expanded ? "close" : "menu"} /></button>
      <div className="topbar-path"><span>Workspace</span><span aria-hidden="true">/</span>{project && <><span className="topbar-project">{project.name}</span><span aria-hidden="true">/</span></>}<strong>{title}</strong></div>
      <span className="local-indicator"><span aria-hidden="true" />Local workspace</span>
    </header>
    <aside id="app-navigation" className={`app-sidebar${expanded ? " is-expanded" : ""}`}>
      <Link href="/" className="brand" aria-label="ML Studio home"><span className="brand-mark" aria-hidden="true"><svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M4 18V6l8 8 8-8v12M4 6l8 8 8-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></span><span>ML Studio<small>Machine learning, clearly.</small></span></Link>
      <div className="sidebar-section-label">Workspace</div>
      <nav className="sidebar-links" aria-label="Global workspace">{item("projects", "Projects", "projects")}</nav>
      {project && <><div className="sidebar-project"><span className="project-monogram" aria-hidden="true">{project.name.slice(0, 1).toUpperCase()}</span><span>{project.name}<small>Project workbench</small></span></div>
        <div className="sidebar-section-label">Build your experiment</div>
        <nav className="sidebar-links" aria-label="Project workflow">{workflow.map(step => item(step.view, step.label, step.view, step.hint))}</nav>
        <div className="sidebar-section-label">Evidence & development</div>
        <nav className="sidebar-links" aria-label="Project evidence">{item("runs", "Runs", "runs")}{item("evaluate", "Evaluate", "evaluate")}{item("code", "Code", "code")}</nav>
      </>}
      <div className="sidebar-note"><Icon name="local" /><div><strong>Built to run locally</strong><p>Managed data and Run history are stored on this device.</p></div></div>
      <div className="sidebar-footnote"><span className="small-brand-dot" />Visual ML. Real code.</div>
    </aside>
    <div className="app-content">{children}<footer className="app-footer"><span>ML Studio <span className="muted">/ Local-first ML workbench</span></span><span>Inspect. Configure. Reproduce.</span></footer></div>
  </div>;
}

export function WorkflowRail({ view, hasDataset, codeMode }: { view: string; hasDataset: boolean; codeMode: boolean }) {
  const steps = [{ view: "data", label: "Dataset", hint: hasDataset ? "Source attached" : "Upload a CSV" }, { view: "prepare", label: "Prepare", hint: "Feature recipe" }, { view: "train", label: "Train", hint: "Saved experiment" }, { view: "evaluate", label: "Evaluate", hint: "Historical evidence" }];
  return <section className="workflow-rail" aria-label="Experiment workflow"><div className="workflow-rail-label"><Icon name="prepare" /><strong>{codeMode ? "Code Mode active" : "Visual pipeline"}</strong><span>{codeMode ? "Visual recipe preserved" : "From source to evidence"}</span></div><ol>{steps.map((step, index) => <li key={step.view} className={view === step.view ? "is-current" : ""} aria-current={view === step.view ? "step" : undefined}><span className="workflow-number">{index + 1}</span><span><strong>{step.label}</strong><small>{step.hint}</small></span></li>)}</ol></section>;
}
