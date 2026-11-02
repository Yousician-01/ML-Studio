"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Project } from "@/lib/api/projects";
import { taskLabel } from "@/lib/api/task-policy";
import { ProjectForm } from "./project-form";
import { DeleteProject } from "./delete-project";
import { Alert, Button, Dialog, EmptyState, Loading } from "./ui";
import { AppShell } from "./app-shell";
import { Icon } from "./icons";

export function Projects() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<Project | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api
      .projects(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setProjects(value);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(error.message);
      });
    return () => controller.abort();
  }, [attempt]);
  return (
    <AppShell><main id="main-content" tabIndex={-1}>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>Projects</h1>
          <p className="muted">
            A home for your data, pipelines and reproducible experiments.
          </p>
        </div>
        <Button variant="primary" onClick={() => setCreating(true)}>
          <Icon name="plus" />New Project
        </Button>
      </div>
      <section className="projects-intro" aria-label="Getting started"><Icon name="prepare" /><div><h2>From a dataset to a reproducible experiment</h2><p>Start with a prediction problem. Keep the data, decisions and exact code together.</p></div><div className="intro-flow" aria-hidden="true"><span>Data</span><Icon name="arrow" /><span>Prepare</span><Icon name="arrow" /><span>Train</span><Icon name="arrow" /><span>Evaluate</span></div></section>
      {error && (
        <Alert>
          {error}
          <Button
            onClick={() => {
              setError("");
              setAttempt((v) => v + 1);
            }}
          >
            Retry
          </Button>
        </Alert>
      )}
      {projects === null ? (
        !error && <Loading>Loading Projects…</Loading>
      ) : projects.length === 0 ? (
        <section className="panel">
          <EmptyState title="Start with a prediction problem">
            <p>Create a Project, bring a CSV, and explore the source.</p>
            <Button variant="primary" onClick={() => setCreating(true)}>
              <Icon name="plus" />Create your first Project
            </Button>
            <ol className="onboarding-steps"><li><span>01</span>Upload CSV</li><li><span>02</span>Set your target</li><li><span>03</span>Build & train</li><li><span>04</span>Evaluate & inspect code</li></ol>
          </EmptyState>
        </section>
      ) : (
        <section className="project-surface" aria-label="Projects">
          <div className="collection-heading"><h2>Your projects</h2><span>{projects.length}</span></div>
          <ul className="project-list">
            {projects.map((project) => (
              <li key={project.id}>
                <div className="project-card-top"><span className="project-monogram" aria-hidden="true">{project.name.slice(0, 1).toUpperCase()}</span><span className="badge">{taskLabel(project.ml_objective)}</span></div>
                <div className="project-context">
                  <Link
                    className="project-name"
                    href={`/projects/${project.id}`}
                  >
                    {project.name}
                  </Link>
                  <p>{project.problem_statement}</p>
                  {project.description && (
                    <small className="muted">{project.description}</small>
                  )}
                  <div>
                    <span className="badge subtle">
                      {project.active_dataset_id
                        ? "Dataset attached"
                        : "No Dataset"}
                    </span>
                  </div>
                </div>
                <div className="project-actions">
                  <time dateTime={project.updated_at}>
                    Updated {new Date(project.updated_at).toLocaleDateString()}
                  </time>
                  <div className="actions">
                    <Link
                      className="button button-secondary"
                      href={`/projects/${project.id}`}
                    >
                      Open Project<Icon name="arrow" width="14" height="14" />
                    </Link>
                    <Button
                      variant="danger"
                      aria-label={`Delete ${project.name}`}
                      onClick={() => setDeleting(project)}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
      {creating && (
        <Dialog title="Create Project" onClose={() => setCreating(false)}>
          <ProjectForm
            submitLabel="Create Project"
            onSave={async (input) => {
              const project = await api.createProject(input);
              router.push(`/projects/${project.id}`);
            }}
          />
        </Dialog>
      )}
      {deleting && (
        <DeleteProject
          project={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            setProjects(
              (items) =>
                items?.filter((item) => item.id !== deleting.id) ?? null,
            );
            setDeleting(null);
          }}
        />
      )}
    </main></AppShell>
  );
}
